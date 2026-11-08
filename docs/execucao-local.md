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

Abre em <http://localhost:8501> com duas páginas, na barra de navegação do topo.

### Temporada (página principal)

1. **Cabeçalho:** "Fórmula 1 · temporada {ano}" e o seletor **Temporada** (2023 até o ano atual; padrão 2024).
2. **Frase-resumo** gerada dos dados, por exemplo: "**Max Verstappen** soma **437** pontos; **7** pilotos diferentes venceram as **24** corridas."
3. **Quatro KPIs:** corridas, sprints, vencedores diferentes (só corridas) e pontos do líder (corridas + sprints).
4. **Temporada:** à esquerda, *Pontos por piloto* (barras na cor da equipe; o tooltip mostra vitórias e pódios); à direita, *Vencedores por corrida* (rodada, GP, data, vencedor e equipe). Pontos vêm de `session_results.points`, que já inclui o ponto da volta mais rápida.
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

### Data Lake

Estado técnico do lake:

- **Métricas gerais:** arquivos na bronze, registros processados (silver), registros rejeitados (quarentena), último `run_id` e data/hora da última execução (UTC).
- **Estado das camadas:** para bronze, silver e quarentena, se existe, a quantidade de arquivos e datasets e o tamanho.
- **Datasets silver:** partições, registros, rejeitados e última execução de cada dataset.

Os números ficam em cache por 60 s; o botão **Recarregar dados** força uma nova leitura.

!!! note "Sessões ao vivo"
    Se o comando falhar com `OpenF1AccessError` (HTTP 401), há uma sessão de F1 ao vivo em andamento e a OpenF1 bloqueou o acesso gratuito. Reexecute quando ela terminar.
