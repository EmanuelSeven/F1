# Testes

## Organização

| Tipo | Diretório | Características |
|---|---|---|
| Unitário | `tests/unit/` | Sem rede. Cliente HTTP com `httpx.MockTransport`, storage em `tmp_path`, pipelines com `FakeOpenF1Source` e fixtures de `tests/fixtures/openf1/` |
| Integração | `tests/integration/` | `@pytest.mark.integration`; consulta a OpenF1 real (meeting 1219, Singapura 2023) e grava em `tmp_path` |

O teste de integração é **pulado** quando a API responde `401` (sessão ao vivo em andamento).

## Comandos

```bash
poetry run pytest                          # tudo, com cobertura (mínimo 50%)
poetry run pytest -m "not integration"     # só unitários (usado na CI)
poetry run pytest -m integration --no-cov  # só integração (requer internet)
poetry run pytest --cov-report=html        # relatório em htmlcov/
```

`--no-cov` é necessário ao rodar só a integração, porque sozinha ela não atinge o mínimo de cobertura do projeto.

## Metas de cobertura

```bash
poetry run coverage report --include="src/f1/domain/*,src/f1/quality/*,src/f1/processing/*" --fail-under=80
poetry run coverage report --include="src/f1/ingestion/*,src/f1/storage/*,src/f1/pipelines/*" --fail-under=70
```

## Casos cobertos

- Montagem de query com operadores, multivalor e `latest`.
- Retry em `429`/`5xx`/timeout com `Retry-After`; `404` vazio; `401` sem retry; intervalo mínimo.
- Normalização de cada dataset (tipos, datas UTC, listas, campos depreciados, payload vazio).
- Schemas: duplicidade, faixas, conjunto de compostos, regra `lap_end >= lap_start`, coluna extra.
- Quarentena com motivo e `run_id`; `DataQualityError` acima de 5%; violação de schema interrompe.
- Idempotência: rodar a pipeline duas vezes gera o mesmo conteúdo, sem duplicatas.
- CLI ponta a ponta com logs JSON e um único `run_id`.
