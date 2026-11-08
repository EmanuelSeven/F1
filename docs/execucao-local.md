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
poetry run python -m f1 calendar --year 2024

# Datasets de sessão de um meeting
poetry run python -m f1 meeting --meeting-key 1229

# Calendário + todos os meetings encerrados do ano
poetry run python -m f1 season --year 2024

# Apenas alguns datasets (nomes de endpoint ou de dataset silver)
poetry run python -m f1 season --year 2024 --datasets laps,stints
```

Reexecutar com os mesmos parâmetros sobrescreve as mesmas partições, sem duplicar registros.

## Saída

```text
data/
├── bronze/laps/season=2024/meeting_key=1229/session_key=9472.json
├── silver/laps/season=2024/meeting_key=1229/part-00000.parquet
└── quarantine/laps/season=2024/meeting_key=1229/part-00000.parquet   # se houver rejeitados
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

Abre em <http://localhost:8501> com três páginas, na barra de navegação do topo: **Temporada**, **Voltas** e **Data Lake**.

### Barra lateral (comum a todas as páginas)

No topo fica a marca **FORMULA 1 · Analytics**. A seção **Filtros** traz:

| Filtro | Efeito |
|---|---|
| **Temporada** | 2023 até o ano atual (padrão 2024). Também fica na URL (`?ano=2024`), para compartilhar o link |
| **Tipo de sessão** | Corrida, Sprint, Classificação, Treino livre (padrão: Corrida + Sprint). Aparece só nas páginas onde se aplica: hoje, a página **Voltas**. Nessas páginas, os pontos somam os tipos marcados, e os vencedores usam as corridas, se marcadas; senão, os tipos marcados (só Classificação mostra as poles). Na **Temporada** ele fica desabilitado, com uma explicação: a página considera sempre corridas e sprints. No **Data Lake** fica oculto. A escolha é preservada ao passar por páginas sem o filtro |
| **Grande Prêmio** | "Todos" ou um GP do ano. Não filtra os números: destaca a linha na tabela de vencedores e abre os detalhes daquele GP |
| **Equipe e piloto** | Restringe gráfico, tabela, KPIs e frase aos pilotos escolhidos. A lista de pilotos depende das equipes marcadas, e os dois filtros se combinam (E) |
| **Limpar filtros** | Volta tudo ao padrão, menos a temporada |

Os filtros ficam em `st.session_state`, então continuam valendo ao trocar de página.

Nas páginas que usam o filtro, marcar Classificação ou Treino livre baixa sob demanda os resultados dessas sessões, junto com os tipos já carregados.

No rodapé aparece "Dados: OpenF1 · última atualização {data}", com a data da ingestão mais recente no lake.

Um piloto que usou mais de um número no ano aparece uma única vez, com os pontos somados. Por exemplo, Oliver Bearman em 2024: #38 pela Ferrari e #50 pela Haas.

### Temporada (página principal)

1. **Cabeçalho:** "Fórmula 1 · Temporada {ano}" (o ano vem da barra lateral). A data da última atualização dos dados aparece no rodapé da barra lateral.
2. **Frase-resumo** gerada dos dados, por exemplo: "**Max Verstappen** soma **437** pontos; **7** pilotos diferentes venceram as **24** corridas." Com a **temporada em andamento** (há corridas futuras no calendário), ela vira "**{líder}** lidera com **{pts}** pontos após **{feitas}** de **{total}** corridas; **{n}** pilotos diferentes venceram."
3. **Quatro KPIs:** corridas, sprints, vencedores diferentes (só corridas) e pontos do líder (corridas + sprints). Com a temporada em andamento, o cartão *Corridas* mostra "{feitas}/{total}" e a legenda "Realizadas / previstas".
4. **Temporada:** à esquerda, *Pontos por piloto* (barras na cor da equipe; o tooltip mostra vitórias e pódios). O gráfico considera só corridas e sprints e esconde pilotos com 0 pontos; o botão "Mostrar pilotos sem pontos" (desligado por padrão) mostra todos. À direita, *Vencedores por corrida* (rodada, GP, data, vencedor e equipe). Os pontos vêm de `session_results.points`, que já traz a pontuação oficial de cada temporada (incluindo o ponto extra da volta mais rápida, que valeu até 2024).
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

### Voltas

As **5 voltas mais rápidas por circuito**.

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
