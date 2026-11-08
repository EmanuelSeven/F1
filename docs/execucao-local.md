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

## Dashboard

Painel Streamlit com o estado do data lake em `F1_DATA_DIR`:

```bash
poetry run streamlit run src/f1/dashboard.py
# ou
poetry run task dashboard
```

Abre em <http://localhost:8501> e mostra:

- **Métricas gerais:** arquivos na bronze, registros processados (silver), registros rejeitados (quarentena), último `run_id` e data/hora da última execução (UTC).
- **Estado das camadas:** para bronze, silver e quarentena: se existe, quantidade de arquivos, datasets e tamanho.
- **Datasets silver:** partições, registros, rejeitados e última execução de cada dataset.

Os números ficam em cache por 60 s; o botão **Recarregar dados** força uma nova leitura. Se ainda não houver dados, o painel sugere rodar a CLI primeiro.

!!! note "Sessões ao vivo"
    Se o comando falhar com `OpenF1AccessError` (HTTP 401), há uma sessão de F1 ao vivo em andamento e a OpenF1 bloqueou o acesso gratuito. Reexecute quando ela terminar.
