# Plano de criação — Projeto `f1`

## Contexto

O projeto `f1` é um pipeline de engenharia de dados em Python 3.13 que extrai dados históricos (2023+) da **OpenF1 API** (`https://api.openf1.org/v1`, gratuita e sem autenticação) e os persiste num data lake local em camadas **bronze** (JSON bruto) e **silver** (Parquet tipado, validado e particionado).

Fontes deste plano:
- `doc_api.md` — endpoints, filtros, chaves (`meeting_key`, `session_key`, `driver_number`) e limitações da OpenF1.
- `SKILL.md` — padrões obrigatórios: layout `src/`, Poetry, camadas, Ruff + MyPy strict, pytest (cobertura ≥ 50%), MkDocs Material, logging JSON, idempotência, linhagem, Pandera + quarentena, CI.

Estado atual: `pyproject.toml` mínimo (sem deps de runtime, só `pytest`, `pytest-cov`, `ruff`), `src/f1/__init__.py` e `tests/__init__.py` vazios, `README.md` com apenas o título.

### Escopo da v0.1

| Incluído (núcleo da corrida) | Fora do escopo |
|---|---|
| `meetings`, `sessions`, `drivers`, `session_result`, `laps`, `stints`, `pit`, `weather` | `car_data`, `location`, `position`, `intervals` (telemetria/alto volume), `team_radio`, `overtakes`, `race_control`, `starting_grid`, `championship_*` (beta), dados em tempo real (pagos) |

Destino: `data/bronze/` (JSON bruto) e `data/silver/` (Parquet `zstd`), mais `data/quarantine/` para registros rejeitados.

---

## Arquitetura

```text
OpenF1 API ──► ingestion (httpx) ──► bronze (JSON bruto, por partição)
                                         │
                                         ▼
                              processing (normalização → DataFrame)
                                         │
                                         ▼
                              quality (Pandera) ──► quarantine (rejeitados)
                                         │
                                         ▼
                              storage silver (Parquet atômico, por partição)
```

Unidade de trabalho: **um meeting (fim de semana de GP)**. A pipeline de temporada itera os meetings do ano.

### Datasets, chaves e partições

| Dataset silver | Endpoint | Chave de negócio (unicidade) | Partição |
|---|---|---|---|
| `meetings` | `/meetings` | `meeting_key` | `season=` |
| `sessions` | `/sessions` | `session_key` | `season=` |
| `drivers` | `/drivers` | `session_key, driver_number` | `season=/meeting_key=` |
| `session_results` | `/session_result` | `session_key, driver_number` | `season=/meeting_key=` |
| `laps` | `/laps` | `session_key, driver_number, lap_number` | `season=/meeting_key=` |
| `stints` | `/stints` | `session_key, driver_number, stint_number` | `season=/meeting_key=` |
| `pit_stops` | `/pit` | `session_key, driver_number, lap_number` | `season=/meeting_key=` |
| `weather` | `/weather` | `session_key, date` | `season=/meeting_key=` |

- Todas as tabelas silver recebem `_run_id`, `_ingested_at` (UTC) e `_source` (endpoint).
- Campos depreciados (`country_code` em drivers, `pit_duration` em pit) **não** entram no schema silver.
- `segments_sector_*` de `/laps` podem vir nulos em corridas → colunas `nullable=True`.

---

## Estrutura alvo

```text
src/f1/
├── __init__.py
├── __main__.py                 # CLI: python -m f1 ...
├── config/settings.py          # Settings (pydantic-settings, prefixo F1_)
├── domain/
│   ├── endpoints.py            # Enum Endpoint + metadados (chave, partição)
│   ├── models.py               # Dataclasses frozen: MeetingRef, SessionRef, Partition
│   └── ports.py                # Protocols: OpenF1Source, RawStore, DatasetStore
├── ingestion/
│   ├── query.py                # Monta query string (=, >=, <=, multivalor, latest)
│   └── openf1_client.py        # Cliente httpx com retry/backoff e rate limit
├── processing/
│   ├── normalize.py            # raw list[dict] → DataFrame tipado por dataset
│   └── lineage.py              # add_lineage_columns
├── quality/
│   ├── schemas.py              # Um DataFrameSchema Pandera por dataset
│   └── validation.py           # validate() → ValidationResult + DataQualityError
├── storage/
│   ├── paths.py                # Resolução de caminhos de partição
│   ├── bronze.py               # Escrita atômica de JSON bruto
│   ├── parquet_writer.py       # write_partition atômico (overwrite por partição)
│   └── quarantine.py           # Grava rejeitados com motivo + run_id
├── pipelines/
│   ├── calendar.py             # meetings + sessions de uma temporada
│   ├── meeting.py              # datasets de sessão para um meeting
│   └── season.py               # calendário + todos os meetings do ano
└── utils/
    ├── logging.py              # JsonFormatter + configure_logging
    ├── metrics.py              # PipelineMetrics + track_pipeline
    └── dates.py                # Parsing ISO 8601 → UTC
tests/
├── conftest.py                 # Fixtures, FakeOpenF1Source, payloads de exemplo
├── fixtures/openf1/*.json      # Amostras reais pequenas por endpoint
├── unit/<espelho de src/f1>/test_*.py
└── integration/test_openf1_live.py   # @pytest.mark.integration (API real)
docs/  index.md, arquitetura.md, estrutura.md, execucao-local.md, testes.md, contribuicao.md, datasets.md
```

---

## Fases de implementação

Cada fase = uma branch + PR (`SKILL.md` §12 proíbe commit direto em `main`). Commits em Conventional Commits.

### Fase 0 — Fundação do repositório (`chore/bootstrap`)

1. `pyproject.toml`:
   - Runtime (`main`): `httpx`, `pandas`, `pyarrow`, `pandera`, `pydantic-settings` — todos com intervalos explícitos (`>=x,<y`).
   - Grupo `dev`: `ruff`, `pytest`, `pytest-cov`, `pytest-mock`, `mypy`, `pre-commit`, `pandas-stubs`.
   - Grupo `docs` (opcional, `[tool.poetry.group.docs] optional = true`): `mkdocs`, `mkdocs-material`.
   - Colar as seções `[tool.ruff]`, `[tool.mypy]` (strict, plugin `pydantic.mypy`), `[tool.pytest.ini_options]` e `[tool.coverage]` do `SKILL.md` §4–5.
   - Preencher `description`.
2. Criar `.python-version` (`3.13`), `.editorconfig`, `.gitignore` (§7.8), `.env.example`, `.pre-commit-config.yaml` (§7.7).
3. Criar todos os subpacotes com `__init__.py` e a árvore `tests/unit`, `tests/integration`.
4. `poetry lock && poetry install` — `poetry.lock` versionado no mesmo commit.

### Fase 1 — Utilitários e configuração (`feature/utils-config`)

- `utils/logging.py` e `utils/metrics.py` conforme `SKILL.md` §7.2 e §9.
- `utils/dates.py`: `parse_utc(value: str) -> datetime`.
- `config/settings.py` (`Settings` + `get_settings()` com `lru_cache`):

  | Variável | Padrão |
  |---|---|
  | `F1_ENV` | `dev` |
  | `F1_LOG_LEVEL` | `INFO` |
  | `F1_API_BASE_URL` | `https://api.openf1.org/v1` |
  | `F1_DATA_DIR` | `data` |
  | `F1_HTTP_TIMEOUT_SECONDS` | `30` |
  | `F1_HTTP_MAX_RETRIES` | `5` |
  | `F1_REQUEST_INTERVAL_SECONDS` | `0.5` (rate limit não documentado) |
  | `F1_MAX_REJECTION_RATE` | `0.05` |

### Fase 2 — Domínio (`feature/domain`)

- `domain/endpoints.py`: `Endpoint(StrEnum)` com os 8 endpoints e um `DatasetSpec` (nome silver, chave de negócio, nível de partição).
- `domain/models.py`: `MeetingRef(meeting_key, year, name)`, `SessionRef(session_key, meeting_key, session_name, session_type)`, `Partition(season, meeting_key | None)`.
- `domain/ports.py`: `OpenF1Source.fetch(endpoint, filters) -> list[dict[str, object]]`, `RawStore.write(...)`, `DatasetStore.write_partition(...)`.
- Sem nenhum import de `httpx`/`pandas` nesta camada.

### Fase 3 — Ingestão (`feature/ingestion-openf1`)

- `ingestion/query.py`: monta query string a partir de `Filter(field, op, value)`; suporta `=`, `>`, `<`, `>=`, `<=`, valores repetidos e `latest`; faz URL-encoding. (Necessário porque `httpx` `params` não expressa `speed>=315`.)
- `ingestion/openf1_client.py`: `OpenF1Client` implementa `OpenF1Source`:
  - `httpx.Client` injetável (permite `httpx.MockTransport` nos testes).
  - Retry com backoff exponencial em `429`/`5xx`/timeout, respeitando `Retry-After`; intervalo mínimo entre requisições.
  - Resposta vazia (`[]`) é válida; `404` de "sem dados" tratado como lista vazia.
  - Log estruturado por requisição (`endpoint`, `status`, `records`, `elapsed`).

### Fase 4 — Storage (`feature/storage-lake`)

- `storage/paths.py`: `data/{layer}/{dataset}/season=YYYY[/meeting_key=N]`.
- `storage/bronze.py`: grava `raw.json` por endpoint/sessão em diretório temporário e promove com rename (atômico, idempotente).
- `storage/parquet_writer.py`: `write_partition` do `SKILL.md` §8.1 (overwrite atômico, `zstd`, um arquivo por partição — evita small files).
- `storage/quarantine.py`: rejeitados em Parquet com `_reject_reason` e `_run_id`, mesma partição.

### Fase 5 — Processamento e qualidade (`feature/processing-quality`)

- `processing/normalize.py`: uma função pura por dataset (`normalize_laps(records) -> DataFrame`, ...): seleção de colunas, cast de tipos, datas → UTC, remoção de campos depreciados. Registro em `NORMALIZERS: dict[Endpoint, Callable]`.
- `processing/lineage.py`: `add_lineage_columns` (§8.4).
- `quality/schemas.py`: um `pa.DataFrameSchema` por dataset (`strict=True`, `unique=` chave de negócio, ranges — ex.: `lap_number` 1–100, `lap_duration` 0–600 s, `compound` em conjunto conhecido, `track_temperature` −10–80).
- `quality/validation.py`: `validate(df, schema, max_rejection_rate) -> ValidationResult` reaproveitando o padrão do §10.3; violação de schema interrompe, taxa > limite lança `DataQualityError`.

### Fase 6 — Pipelines e CLI (`feature/pipelines`)

- `pipelines/calendar.py`: `run_calendar(source, store, year)` → `meetings` e `sessions` (ignora `is_cancelled=true`).
- `pipelines/meeting.py`: `run_meeting(source, stores, meeting)` → para cada sessão, busca os 6 datasets de sessão, grava bronze, normaliza, valida, grava silver/quarentena. Cada dataset envolto em `track_pipeline` (`records_read/processed/rejected`, `run_id`, `destination`).
- `pipelines/season.py`: `run_season(year)` = calendário + todos os meetings já encerrados.
- `__main__.py` (argparse), composição das dependências apenas aqui:
  ```bash
  poetry run python -m f1 calendar --year 2024
  poetry run python -m f1 meeting --meeting-key 1229
  poetry run python -m f1 season --year 2024 [--datasets laps,stints]
  ```
- Reexecução com os mesmos parâmetros produz o mesmo resultado (overwrite por partição).

### Fase 7 — Testes (contínuo em cada fase)

- Unitários sem rede/disco real: `httpx.MockTransport` para o cliente, `tmp_path` para storage, `FakeOpenF1Source` + payloads de `tests/fixtures/openf1/` para pipelines.
- Casos-chave: montagem de query com operadores; retry em 429; normalização de cada dataset; schema rejeita duplicata/range; quarentena; `DataQualityError` acima de 5%; idempotência (rodar pipeline 2× → mesmo conteúdo, sem duplicatas).
- Integração (`@pytest.mark.integration`): uma sessão pequena real (ex.: `session_key` de 2023) ponta a ponta em `tmp_path`.
- Metas: projeto ≥ 50% (bloqueante); `domain`/`quality`/`processing` ≥ 80%; `ingestion`/`storage`/`pipelines` ≥ 70%.

### Fase 8 — Documentação e CI (`docs/mkdocs`, `chore/ci`)

- `mkdocs.yml` (§6.2) + páginas mínimas e `datasets.md` (dicionário de dados silver: colunas, tipos, chaves, partições).
- `README.md`: objetivo, quickstart, link para a documentação.
- `.github/workflows/ci.yml` (§11.2): install → format check → lint → mypy → pytest (`-m "not integration"`) → `mkdocs build --strict`.

---

## Riscos e decisões

- **Rate limit não documentado** → intervalo configurável + backoff; ingestão de temporada é sequencial.
- **Dados incompletos da API** (sessões sem `pit`/`weather`, laps com setores nulos) → lista vazia é válida; colunas opcionais `nullable`.
- **Small files**: partição por meeting gera ~24 arquivos/ano por dataset — aceitável; compactação fica para quando houver telemetria.
- **Telemetria (`car_data`/`location`)** fora da v0.1; a arquitetura por `Endpoint` + `DatasetSpec` permite adicioná-la depois sem refatorar.

---

## Verificação

```bash
poetry install --with docs
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy src
poetry run pytest -m "not integration"
poetry run pytest -m integration          # requer internet
poetry run mkdocs build --strict
poetry run python -m f1 meeting --meeting-key <key de 2024>
poetry run python -m f1 meeting --meeting-key <mesma key>   # idempotência
```

Conferir: `data/silver/laps/season=2024/meeting_key=<key>/part-00000.parquet` existe, contagem de linhas igual nas duas execuções, logs JSON com `pipeline_started`/`pipeline_finished` e `run_id`, rejeitados (se houver) em `data/quarantine/`.
