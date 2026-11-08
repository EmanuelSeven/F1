# Arquitetura

## Fluxo de dados

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

A unidade de trabalho é um **meeting** (fim de semana de GP). A pipeline de temporada carrega o calendário do ano e depois cada meeting já encerrado, em sequência.

## Camadas

| Camada | Responsabilidade | Depende de |
|---|---|---|
| `domain` | `Endpoint`, `DatasetSpec`, entidades (`MeetingRef`, `SessionRef`, `Partition`, `Filter`) e contratos (`OpenF1Source`, `RawStore`, `DatasetStore`) | nada |
| `ingestion` | Query string com operadores e cliente HTTP com retry/backoff | `domain`, `config` |
| `processing` | Normalização tipada e colunas de linhagem | `domain`, `utils` |
| `quality` | Schemas Pandera e separação válidos/rejeitados | `domain` |
| `storage` | Bronze JSON, silver Parquet e quarentena | `domain` |
| `pipelines` | Orquestração `calendar` → `meeting` → `season` | todas |
| `config` / `utils` | Settings, logging JSON, métricas, datas | — |
| `dashboard` (apresentação) | `dashboard/loaders.py` lê e agrega o lake (sem visualização); `dashboard.py` só renderiza com Streamlit | `domain`, `storage`, `config` |

O dashboard é somente leitura: não executa pipelines nem regras de negócio. `dashboard.py` não acessa arquivos; toda leitura passa por `f1.dashboard.loaders`. Como o arquivo e o pacote compartilham o nome `f1.dashboard`, o `dashboard.py` é executado pelo caminho (`streamlit run`) e checado pelo MyPy em uma etapa própria.

A composição das implementações concretas acontece apenas em `src/f1/__main__.py`. As pipelines recebem a fonte e os stores por parâmetro, o que permite testá-las com uma fonte falsa em memória.

## Decisões

- **Idempotência por overwrite de partição.** Cada dataset de um meeting é gravado em `season=YYYY/meeting_key=N/part-00000.parquet`, num diretório de staging que só substitui a partição final depois de escrito. Reexecutar produz o mesmo conteúdo (só mudam `_run_id` e `_ingested_at`). Sem rejeitados, a partição de quarentena é removida.
- **Bronze por sessão, silver por meeting.** A API é consultada por `session_key`; o bronze guarda um JSON por sessão e o silver concatena as sessões do meeting num único arquivo, o que evita arquivos pequenos (cerca de 24 por ano por dataset).
- **Validação em dois níveis.** Violações de schema (coluna ausente/extra, tipo errado) interrompem a pipeline na hora. Violações de linha (nulidade, faixa, unicidade da chave de negócio, consistência entre colunas) vão para a quarentena; acima de `F1_MAX_REJECTION_RATE` (5%) a pipeline grava a quarentena e falha com `DataQualityError`.
- **Cancelados.** Meetings e sessões com `is_cancelled=true` ficam no silver, mas não são processados pelas pipelines de sessão.
- **Rate limit não documentado.** Intervalo mínimo configurável entre requisições (`F1_REQUEST_INTERVAL_SECONDS`) e backoff exponencial em `429`/`5xx`/timeout, respeitando `Retry-After`.
- **Erros da API.** `404` é tratado como "sem dados" (lista vazia). `401`/`403` lançam `OpenF1AccessError` sem retry; isso acontece durante sessões ao vivo, quando a OpenF1 bloqueia o acesso gratuito.
- **Campos depreciados** (`country_code` em drivers, `pit_duration` em pit) não entram no silver.

## Observabilidade

Cada dataset é envolto em `track_pipeline`, que registra em JSON os eventos `pipeline_started`, `pipeline_finished` e `pipeline_failed` com `run_id`, `destination`, `records_read`, `records_processed`, `records_rejected` e `duration_seconds`. Um único `run_id` é gerado por execução da CLI e propagado a todos os eventos. Cada requisição HTTP gera um evento `openf1_request`.
