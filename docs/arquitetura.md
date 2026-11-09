# Arquitetura

## Fluxo de dados

```mermaid
flowchart LR
    API[(OpenF1 API)] -->|httpx| ING[ingestion]
    ING --> BRZ[/bronze<br/>JSON bruto/]
    ING --> PRC[processing<br/>normalização]
    PRC --> QLT{quality<br/>Pandera}
    QLT -->|válidos| SLV[/silver<br/>Parquet/]
    QLT -->|rejeitados| QRT[/quarentena<br/>Parquet/]
    SLV -.-> DSH[dashboard<br/>Streamlit + Plotly]
    DSH -.->|cargas sob demanda| ING
    QRT -.-> DSH
    BRZ -.-> DSH
```

A unidade de trabalho é um **meeting** (fim de semana de GP). A pipeline de temporada carrega o calendário do ano e depois cada meeting já encerrado, em sequência.

## Camadas

| Camada | Responsabilidade | Depende de |
|---|---|---|
| `domain` | `Endpoint`, `DatasetSpec`, entidades (`MeetingRef`, `SessionRef`, `Partition`, `Filter`) e contratos (`OpenF1Source`, `RawStore`, `DatasetStore`) | nada |
| `ingestion` | Query string com operadores e cliente HTTP com retry/backoff | `domain`, `config` |
| `processing` | Normalização tipada, colunas de linhagem e agregações analíticas da temporada (`standings.py`: pontos, vitórias, pódios, vencedores, KPIs; `filters.py`: aplicação dos filtros do dashboard) | `domain`, `utils` |
| `quality` | Schemas Pandera e separação válidos/rejeitados | `domain` |
| `storage` | Bronze JSON, silver Parquet e quarentena | `domain` |
| `pipelines` | Orquestração `calendar` → `meeting` → `season`, `results` (drivers + resultados de várias sessões em lote) e `factory` (composição dos stores) | todas |
| `config` / `utils` | Settings, logging JSON, métricas, datas | — |
| `dashboard` (apresentação) | `loaders.py` lê o lake; `bootstrap.py` dispara cargas sob demanda; `views/` monta as páginas (Streamlit + Plotly); `dashboard.py` é o roteador multipage | todas |

O dashboard não contém regra de negócio:

- as agregações e a aplicação dos filtros ficam em `f1.processing.standings` e `f1.processing.filters`, como funções puras;
- a leitura do lake fica em `f1.dashboard.loaders`;
- as cargas da API reaproveitam as pipelines existentes, por meio de `f1.dashboard.bootstrap`;
- as páginas de `f1.dashboard.views` só compõem a tela.

Como o arquivo `dashboard.py` e o pacote `dashboard/` compartilham o nome `f1.dashboard`, o `dashboard.py` é executado pelo caminho (`streamlit run`) e checado pelo MyPy numa etapa própria.

As implementações concretas são compostas em dois pontos de entrada: a CLI (`src/f1/__main__.py`) e o dashboard (`f1.dashboard.bootstrap`). Ambos usam `f1.pipelines.factory.build_stores`. As pipelines recebem a fonte e os stores por parâmetro, o que permite testá-las com uma fonte falsa em memória.

## Decisões

- **Idempotência por overwrite de partição.** Cada dataset de um meeting é gravado em `season=YYYY/meeting_key=N/part-00000.parquet`, num diretório de staging que só substitui a partição final depois de escrito. Reexecutar produz o mesmo conteúdo (só mudam `_run_id` e `_ingested_at`). Sem rejeitados, a partição de quarentena é removida. Gravações simultâneas na mesma partição (duas abas do dashboard, ou dashboard e CLI ao mesmo tempo) são seguras: cada uma usa um staging exclusivo, a troca é serializada por partição e o último gravador vence. Temporários órfãos de execuções interrompidas são removidos na gravação seguinte (`f1.storage.atomic`).
- **Bronze por sessão, silver por meeting.** A API é consultada por `session_key`; o bronze guarda um JSON por sessão e o silver concatena as sessões do meeting num único arquivo, o que evita arquivos pequenos (cerca de 24 por ano por dataset).
- **Validação em dois níveis.** Violações de schema (coluna ausente/extra, tipo errado) interrompem a pipeline na hora. Violações de linha (nulidade, faixa, unicidade da chave de negócio, consistência entre colunas) vão para a quarentena; acima de `F1_MAX_REJECTION_RATE` (5%) a pipeline grava a quarentena e falha com `DataQualityError`.
- **Histórico de rejeições separado da quarentena.** A quarentena é o retrato da última carga (reprocessar dá o mesmo resultado). Para acompanhar a tendência, cada carga também acrescenta ao histórico a contagem por `run_id` e regra, inclusive cargas sem rejeição e cargas abortadas; nada é sobrescrito por outra carga. **Limitação:** o histórico fica no disco, como o resto do lake; no Streamlit Community Cloud o disco é apagado a cada reinício, então lá o histórico recomeça do zero. Para guardá-lo de forma permanente, o próximo passo é levá-lo ao Supabase.
- **Cancelados.** Meetings e sessões com `is_cancelled=true` ficam no silver, mas não são processados pelas pipelines de sessão.
- **Rate limit não documentado.** Intervalo mínimo configurável entre requisições (`F1_REQUEST_INTERVAL_SECONDS`) e backoff exponencial em `429`/`5xx`/timeout, respeitando `Retry-After`.
- **Erros da API.** `404` é tratado como "sem dados" (lista vazia). `401`/`403` lançam `OpenF1AccessError` sem retry; isso acontece durante sessões ao vivo, quando a OpenF1 bloqueia o acesso gratuito.
- **Campos depreciados.** `pit_duration` (pit) não entra no silver. `country_code` (drivers) entra como opcional, só para a nacionalidade do piloto. Como ele chega vazio a partir de 2026, há um mapeamento fixo por sigla em `src/f1/processing/data/driver_nationalities.json` (`f1.processing.nationality`).
- **Resultados em lote.** `run_results` busca `drivers` e `session_result` de várias sessões numa só requisição (`session_key` repetido, até 25 por lote). A temporada inteira de corridas e sprints sai em 2 requisições, e a gravação continua no padrão do meeting: bronze por sessão, silver e quarentena por meeting.
- **Tipos de sessão.** `classify_session` (domínio) classifica cada sessão em corrida, sprint, classificação ou treino; testes de pré-temporada ficam fora das análises por não terem corrida.
- **Pit lane com bandeira vermelha.** Em `pit_stops`, `lane_duration` inclui o tempo parado no pit lane durante uma suspensão: no México 2026 foram cerca de 37 min para 19 carros. O limite de validação é 4 h, porque nenhuma permanência no pit lane dura mais que a própria corrida, e não os 600 s de uma passagem normal. Assim a suspensão não é tratada como erro, e valores absurdos (zero, negativos ou erro de unidade) continuam indo para a quarentena. O `max_rejection_rate` não mudou.
- **Grade de largada por meeting.** `starting_grid` é o único dataset buscado uma vez por meeting (`DatasetSpec.per_session=False`), e não sessão a sessão: a OpenF1 associa a grade à sessão de classificação que a definiu. Ele não entra no comando `meeting` da CLI e é carregado pelo dashboard.
- **Última corrida e cache curto.** A escolha (corrida concluída mais recente com resultados) é uma função pura (`f1.processing.last_race`). A atualização de resultados acontece no máximo a cada 10 minutos (chave de cache por janela de tempo), inclusive quando falha.
- **Voltas por união de sessões.** A partição `laps` é por meeting e é regravada inteira a cada carga. A página *Voltas* e os detalhes da corrida regravam a união das sessões que já estão no lake com as novas, para que uma carga não apague as voltas da outra.
- **Piloto, não número.** A classificação agrupa por piloto: quem trocou de número no ano (ex.: Bearman, #38 e #50 em 2024) aparece uma vez, com os pontos somados.
- **Sprints.** Na OpenF1 a sprint tem `session_type="Race"` e `session_name="Sprint"`; `SessionRef.is_race`, `is_sprint` e `awards_points` encapsulam essa regra.
- **Contador de acessos fora do disco.** O Streamlit Community Cloud apaga o disco a cada reinício, então o total fica numa tabela do Supabase, incrementada por uma função Postgres chamada pela API REST com `httpx` (sem SDK). É opcional (`F1_SUPABASE_URL`/`F1_SUPABASE_KEY`), conta uma vez por sessão do navegador e nunca derruba o dashboard: em erro, só registra um aviso e omite o total. Configuração em [Execução local](execucao-local.md#contador-de-acessos).
- **Pontos** vêm de `session_results.points` (coluna adicionada nesta versão), que já inclui o ponto da volta mais rápida; vitórias e pódios contam apenas corridas principais.

## Observabilidade

Cada dataset é envolto em `track_pipeline`, que registra em JSON os eventos `pipeline_started`, `pipeline_finished` e `pipeline_failed` com `run_id`, `destination`, `records_read`, `records_processed`, `records_rejected` e `duration_seconds`. Um único `run_id` é gerado por execução da CLI e propagado a todos os eventos. Cada requisição HTTP gera um evento `openf1_request`.
