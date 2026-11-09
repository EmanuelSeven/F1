# Execução local

## Pré-requisitos

- Python **3.13.x** (pyenv, `py` launcher do Windows, Docker `python:3.13-slim` ou Dev Container).
- [Poetry](https://python-poetry.org/) 2.x, instalado fora do projeto (instalador oficial ou `pipx install poetry`).

## Instalação

```bash
poetry env use 3.13        # ou o caminho do executável do Python 3.13
poetry install             # main + dev
poetry install --with docs # inclui MkDocs
poetry run pre-commit install
```

## Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste se precisar. Todas usam o prefixo `F1_`:

| Variável | Padrão | Descrição |
|---|---|---|
| `F1_ENV` | `dev` | Ambiente ativo |
| `F1_LOG_LEVEL` | `INFO` | Nível de log |
| `F1_API_BASE_URL` | `https://api.openf1.org/v1` | URL base da OpenF1 |
| `F1_DATA_DIR` | `data` | Raiz do data lake local |
| `F1_HTTP_TIMEOUT_SECONDS` | `30` | Timeout por requisição |
| `F1_HTTP_MAX_RETRIES` | `5` | Novas tentativas em `429`/`5xx`/timeout |
| `F1_REQUEST_INTERVAL_SECONDS` | `0.5` | Intervalo mínimo entre requisições |
| `F1_MAX_REJECTION_RATE` | `0.05` | Taxa máxima de rejeição antes de falhar |

## Comandos

```bash
# Calendário (meetings + sessions) de um ano
poetry run python -m f1 calendar --year 2026

# Datasets de sessão de um meeting
poetry run python -m f1 meeting --meeting-key 1299

# Calendário + todos os meetings encerrados do ano
poetry run python -m f1 season --year 2026

# Apenas alguns datasets (nomes de endpoint ou de dataset silver)
poetry run python -m f1 season --year 2026 --datasets laps,stints
```

Reexecutar com os mesmos parâmetros sobrescreve as mesmas partições, sem duplicar registros.

## Saída

```text
data/
├── bronze/laps/season=2026/meeting_key=1299/session_key=11412.json
├── silver/laps/season=2026/meeting_key=1299/part-00000.parquet
└── quarantine/laps/season=2026/meeting_key=1299/part-00000.parquet   # se houver rejeitados
```

```python
import pandas as pd

laps = pd.read_parquet("data/silver/laps")  # partições viram colunas season/meeting_key
```

## Documentação

O site usa **MkDocs + Material** (modo claro/escuro, busca em português, diagramas Mermaid, abas e blocos de código com botão de cópia). As dependências ficam no grupo opcional `docs`:

```bash
poetry install --with docs
poetry run task docs          # mkdocs serve → http://127.0.0.1:8000 (recarrega ao salvar)
poetry run mkdocs build --strict   # build do site em site/, falhando em avisos (igual à CI)
```

| Atalho | Executa |
|---|---|
| `poetry run task docs` | `mkdocs serve` |
| `poetry run task dashboard` | `streamlit run src/f1/dashboard.py` |
| `poetry run task test` | `pytest -m "not integration"` |
| `poetry run task lint` | `ruff format --check .` + `ruff check .` + `mypy` |
| `poetry run task format` | `ruff format .` + `ruff check . --fix` |

## Dashboard

Painel analítico Streamlit (tema escuro, `.streamlit/config.toml`) sobre o data lake em `F1_DATA_DIR`:

```bash
poetry run streamlit run src/f1/dashboard.py
# ou
poetry run task dashboard
```

Abre em <http://localhost:8501> com quatro páginas: **Última corrida** (a inicial), **Temporada**, **Voltas** e **Data Lake**. A navegação entre elas fica na barra lateral, logo abaixo da marca e acima dos filtros.

### Barra lateral (comum a todas as páginas)

No topo ficam a marca **FORMULA 1 · Analytics** e os links das páginas. A seção **Filtros** traz:

| Filtro | Efeito |
|---|---|
| **Temporada** | De 2023 até o ano atual, do mais recente para o mais antigo. Padrão: o ano mais recente com ao menos uma corrida já concluída (consulta o lake e, se faltar, a OpenF1); se não for possível consultar, o ano atual. O ano também fica na URL (ex.: `?ano=2026`), que tem prioridade sobre o padrão e serve para compartilhar o link |
| **Tipo de sessão** | Corrida, Sprint, Classificação, Treino livre (padrão: Corrida + Sprint). Aparece só nas páginas onde se aplica: hoje, a página **Voltas**. Nessas páginas, os pontos somam os tipos marcados, e os vencedores usam as corridas, se marcadas; senão, os tipos marcados (só Classificação mostra as poles). Na **Temporada** ele fica desabilitado, com uma explicação: a página considera sempre corridas e sprints. No **Data Lake** fica oculto. A escolha é preservada ao passar por páginas sem o filtro |
| **Grande Prêmio** | "Todos" ou um GP do ano. Não filtra os números: destaca a linha na tabela de vencedores e abre os detalhes daquele GP |
| **Equipe e piloto** | Restringe gráfico, tabela, KPIs e frase aos pilotos escolhidos. A lista de pilotos depende das equipes marcadas, e os dois filtros se combinam (E) |
| **Limpar filtros** | Volta tudo ao padrão, menos a temporada |

Os filtros ficam em `st.session_state`, então continuam valendo ao trocar de página.

Nas páginas que usam o filtro, marcar Classificação ou Treino livre baixa sob demanda os resultados dessas sessões, junto com os tipos já carregados.

No rodapé aparece "Dados: OpenF1 · última atualização {data}", com a data da ingestão mais recente no lake, no horário de Brasília (ex.: "08/11/2026 20:13 (Brasília)").

Um piloto que usou mais de um número no ano aparece uma única vez, com os pontos somados. Por exemplo, Oliver Bearman em 2024: #38 pela Ferrari e #50 pela Haas.

Cada página mostra só os filtros que usa. Na **Última corrida**, o seletor de temporada aparece desabilitado, com o ano da corrida exibida e uma explicação, e os demais filtros ficam ocultos. Os valores escolhidos continuam guardados ao trocar de página.

### Última corrida (página inicial)

A corrida principal mais recente **já concluída**: sessão *Race* com `date_end` no passado e resultados disponíveis. Não usa o filtro de temporada: procura no ano atual e, no início do ano, no anterior.

- **Cabeçalho:** "{GP} · {circuito}, {país}", a data e "Rodada {n} de {total} · temporada {ano}".
- **Pódio:** um cartão para 1º, 2º e 3º, com piloto, equipe (na cor da equipe), tempo do vencedor e diferença dos demais.
- **Destaques:** volta mais rápida (piloto e tempo), quem mais ganhou posições e número de abandonos.
- **Classificação:** Pos, Piloto, Equipe, Largada, Posições (▲ verde quando ganhou, ▼ vermelho quando perdeu; largada − chegada), Tempo/Diferença (com "+1 LAP" quando for o caso), Pontos e Situação (DNF/DNS/DSQ).
- **Campeonato:** top 5 de pilotos após essa corrida, com a variação de posição em relação à corrida anterior.

**Atualização.** Enquanto a última corrida não tiver resultados (ela acabou de terminar e a OpenF1 ainda não publicou), a página tenta recarregar calendário e resultados no máximo uma vez a cada **10 minutos**. Até lá, mostra a corrida anterior com o aviso "Resultados de {GP} ainda não disponíveis". O mesmo acontece se a OpenF1 estiver indisponível (`OpenF1AccessError`); falhas também ficam guardadas por 10 minutos, para não repetir a requisição a cada clique.

A **largada** vem do dataset `starting_grid`, baixado sob demanda por GP. A OpenF1 associa a grade à sessão de classificação que a definiu; por isso a página usa a grade da sessão *Qualifying*, não a da classificação sprint. Pilotos sem posição de largada (ex.: largaram do box) aparecem com "—".

### Temporada

1. **Cabeçalho:** "Fórmula 1 · Temporada {ano}" (o ano vem da barra lateral). A data da última atualização dos dados aparece no rodapé da barra lateral. O título e a frase-resumo ficam num banner, em texto branco e alinhados à esquerda, com a arte `src/f1/dashboard/assets/hero_red.svg` embutida em base64 via CSS (`background-size: cover`, `background-position: right center`). Em telas estreitas a altura diminui sem cortar o texto. Sem o arquivo, aparece o cabeçalho normal.
2. **Frase-resumo** gerada dos dados. Com a temporada encerrada: "**{líder}** soma **{pts}** pontos; **{n}** pilotos diferentes venceram as **{total}** corridas." Com a **temporada em andamento** (há corridas futuras no calendário): "**{líder}** lidera com **{pts}** pontos após **{feitas}** de **{total}** corridas; **{n}** pilotos diferentes venceram." Por exemplo, em 2026, depois da 20ª rodada: "**Kimi Antonelli** lidera com **390** pontos após **20** de **23** corridas; **6** pilotos diferentes venceram."
3. **Quatro KPIs:** corridas, sprints, vencedores diferentes (só corridas) e pontos do líder (corridas + sprints). Com a temporada em andamento, o cartão *Corridas* mostra "{feitas}/{total}" e a legenda "Realizadas / previstas".
4. **Temporada:** à esquerda, *Pontos por piloto* (barras na cor da equipe; o tooltip mostra vitórias e pódios). O gráfico considera só corridas e sprints e esconde pilotos com 0 pontos; o botão "Mostrar pilotos sem pontos" (desligado por padrão) mostra todos. À direita, *Vencedores por corrida* (rodada, GP, data, vencedor, nacionalidade e equipe). Os pontos vêm de `session_results.points`, que já traz a pontuação oficial de cada temporada (incluindo o ponto extra da volta mais rápida, que valeu até 2024).
5. **Clique em uma corrida** da tabela para ver os detalhes em abas: resultado final, tempos de volta (escolha de pilotos e opção de ocultar voltas lentas), estratégia de pneus, pit stops e clima.

**Carga automática.** Ao abrir uma temporada que ainda não está no lake, o painel roda, com o aviso *"Carregando dados da OpenF1..."*:

- a pipeline de **calendário** (`meetings` + `sessions`);
- a pipeline de **resultados** (`drivers` + `session_results`) de todas as **corridas e sprints já encerradas**. Os `session_key` vão em lote numa única requisição (2 requisições por temporada).

**Detalhes sob demanda.** `laps`, `stints`, `pit_stops` e `weather` são baixados só quando você clica numa corrida, e só da **corrida principal** daquele fim de semana.

Todas as cargas seguem o padrão bronze → silver → quarentena, respeitam `F1_REQUEST_INTERVAL_SECONDS` entre requisições e rodam uma vez por processo do Streamlit (`st.cache_resource`). As leituras do lake ficam em cache por 5 minutos (`st.cache_data`).

Mensagens de erro:

- se a OpenF1 negar o acesso (`OpenF1AccessError`, comum durante sessões ao vivo), o painel mostra um aviso e continua exibindo o que já foi baixado;
- falhas de rede e dados reprovados na validação também geram mensagens, em vez de erro na tela;
- falhas não ficam em cache, então recarregar a página tenta de novo.

!!! info "Partições de resultados"
    A carga do dashboard grava em `drivers` e `session_results` apenas as corridas e sprints de cada meeting (overwrite por partição). Para ter também treinos e classificação, rode `python -m f1 meeting --meeting-key N`, que regrava a partição com todas as sessões.

!!! note "Tradução automática do navegador"
    A interface já está em português e é marcada como não traduzível (`lang="pt-BR"`, `translate="no"`). Sem isso, o navegador traduzia siglas e nomes dos gráficos; por exemplo, "LAW" (Liam Lawson) virava "DIREITO" e aparecia cortado como "REITO".

**Nacionalidade.** A coluna mostra a bandeira e o nome do país em português (ex.: Reino Unido), como uma imagem SVG gerada pelo painel, porque o Windows não exibe emoji de bandeira.

- **País:** vem de `drivers.country_code` ou, se vier vazio, do mapeamento por sigla em `src/f1/processing/data/driver_nationalities.json`.
- **Nome:** traduzido com Babel (`pt_BR`). Para trocar um nome, edite `COUNTRY_NAME_OVERRIDES` em `src/f1/dashboard/views/flags.py` (ex.: `{"NL": "Holanda"}`).
- **Bandeira:** baixada de `flagcdn.com` uma vez e guardada em `F1_DATA_DIR/cache/flags`.
- **Sem internet:** aparece só o nome do país.

### Voltas

O ranking **Top 5** das voltas mais rápidas por circuito.

- **Título:** "Fórmula 1 · Top 5 Voltas Mais Rápidas {ano}", com o ano do filtro **Temporada**.
- **Subcabeçalho:** "Rodada {rodada} · Exibindo as 5 voltas mais rápidas em {tipos}", com a rodada do GP exibido e os tipos de sessão do filtro. No padrão, o texto fica "… em corrida e sprint".

- **Circuito:** o do filtro **Grande Prêmio**; com "Todos", o GP mais recente já disputado.
- **Sessões:** as do filtro **Tipo de sessão** (padrão: corrida e sprint). Marque **Classificação** para ver as voltas de pole, que costumam ser as mais rápidas.
- **Equipe e piloto:** restringe as voltas aos pilotos escolhidos.
- **"Uma volta por piloto":** mostra só a melhor volta de cada piloto.

A página traz a volta mais rápida em destaque, um gráfico de pontos e uma tabela com posição, piloto, equipe, tempo, diferença para a melhor volta, sessão e número da volta. O gráfico é de pontos, e não de barras, porque as diferenças são de décimos: barras partindo do zero esconderiam a diferença, e barras cortadas a exagerariam.

Os tempos de volta são baixados sob demanda, só das sessões escolhidas daquele GP. As sessões que já estavam no lake continuam lá, então a aba *Tempos de volta* da Temporada não perde dados.

Voltas de saída do box são ignoradas. A OpenF1 não marca voltas anuladas pela direção de prova (ex.: limites de pista), por isso elas podem aparecer.

### Data Lake

Estado técnico do lake:

- **Métricas gerais:** arquivos na bronze, registros processados (silver), registros rejeitados (quarentena), último `run_id` e data/hora da última execução (UTC).
- **Estado das camadas:** para bronze, silver e quarentena, se existe, a quantidade de arquivos e datasets e o tamanho.
- **Datasets silver:** partições, registros, rejeitados e última execução de cada dataset.

Os números ficam em cache por 60 s; o botão **Recarregar dados** força uma nova leitura.

!!! note "Sessões ao vivo"
    Se o comando falhar com `OpenF1AccessError` (HTTP 401), há uma sessão de F1 ao vivo em andamento e a OpenF1 bloqueou o acesso gratuito. Reexecute quando ela terminar.
