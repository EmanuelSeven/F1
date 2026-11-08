# F1

Pipeline de engenharia de dados em Python 3.13 que extrai dados históricos (2023+) da [OpenF1 API](https://openf1.org/docs/) e os grava num data lake local: **bronze** (JSON bruto), **silver** (Parquet tipado, validado e particionado) e **quarentena** (registros rejeitados).

Datasets: `meetings`, `sessions`, `drivers`, `session_results`, `laps`, `stints`, `pit_stops`, `weather`.

## Início rápido

```bash
poetry env use 3.13
poetry install
poetry run python -m f1 calendar --year 2024
poetry run python -m f1 meeting --meeting-key 1229
poetry run python -m f1 season --year 2024 --datasets laps,stints
```

Os dados ficam em `data/silver/<dataset>/season=YYYY[/meeting_key=N]/part-00000.parquet`.

> Durante sessões de F1 ao vivo a OpenF1 bloqueia o acesso gratuito (HTTP 401). Reexecute depois que a sessão terminar.

## Dashboard

```bash
poetry run streamlit run src/f1/dashboard.py   # ou: poetry run task dashboard
```

Mostra arquivos na bronze, registros processados e rejeitados, último `run_id`, última execução e o estado de cada camada. Detalhes em [Execução local](docs/execucao-local.md#dashboard).

## Qualidade

```bash
poetry run task format   # ruff format + ruff check --fix
poetry run task lint     # ruff format --check + ruff check + mypy
poetry run task test     # pytest -m "not integration"
poetry run task docs     # mkdocs serve (requer --with docs)
poetry run task dashboard  # streamlit run src/f1/dashboard.py
```

## Documentação

```bash
poetry install --with docs
poetry run task docs
```

Páginas em [`docs/`](docs/index.md): arquitetura, estrutura, execução local, dicionário de dados, testes e contribuição.
