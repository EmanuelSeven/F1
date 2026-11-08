# Estrutura do projeto

```text
src/f1/
├── __main__.py                 # CLI e composição das dependências
├── dashboard.py                # Dashboard Streamlit (somente apresentação)
├── dashboard/loaders.py        # Leitura e agregação do lake para o dashboard
├── config/settings.py          # Settings (pydantic-settings, prefixo F1_)
├── domain/
│   ├── endpoints.py            # Endpoint, DatasetSpec, chaves e partições
│   ├── models.py               # Filter, Partition, MeetingRef, SessionRef
│   └── ports.py                # OpenF1Source, RawStore, DatasetStore
├── ingestion/
│   ├── query.py                # Query string (=, >, <, >=, <=, multivalor)
│   └── openf1_client.py        # Cliente httpx com retry e rate limit
├── processing/
│   ├── normalize.py            # Colunas declaradas por dataset + casts
│   └── lineage.py              # _run_id, _ingested_at, _source
├── quality/
│   ├── schemas.py              # Um DataFrameSchema Pandera por dataset
│   └── validation.py           # validate() → ValidationResult / DataQualityError
├── storage/
│   ├── paths.py                # {base}/{dataset}/season=Y[/meeting_key=N]
│   ├── bronze.py               # JSON bruto com escrita atômica
│   ├── parquet_writer.py       # Overwrite atômico de partição
│   └── quarantine.py           # Rejeitados (limpa a partição se vazio)
├── pipelines/
│   ├── common.py               # normaliza → valida → silver/quarentena
│   ├── calendar.py             # meetings + sessions de um ano
│   ├── meeting.py              # 6 datasets de sessão de um meeting
│   └── season.py               # calendário + meetings encerrados
└── utils/
    ├── logging.py              # JsonFormatter + configure_logging
    ├── metrics.py              # PipelineMetrics + track_pipeline
    └── dates.py                # ISO 8601 → UTC
tests/
├── conftest.py                 # load_fixture, FakeOpenF1Source
├── fixtures/openf1/*.json      # Amostras pequenas por endpoint
├── unit/                       # Espelho de src/f1, sem rede
└── integration/                # @pytest.mark.integration (API real)
```

## Como adicionar um dataset

1. Adicione o valor em `Endpoint` e o `DatasetSpec` em `domain/endpoints.py`.
2. Declare as colunas em `processing/normalize.py` (`COLUMNS`).
3. Declare o schema em `quality/schemas.py` (`SCHEMAS`). O teste `test_schema_matches_normalizer_columns` garante que os dois batem.
4. Adicione uma fixture em `tests/fixtures/openf1/<endpoint>.json`.
5. Atualize o [Dicionário de dados](datasets.md).

Se o dataset for de nível de sessão, ele passa a ser processado automaticamente pela pipeline de meeting.
