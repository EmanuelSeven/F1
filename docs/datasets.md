# Dicionário de dados (silver)

Gerado a partir de `f1.processing.normalize.COLUMNS` e `f1.quality.schemas.SCHEMAS`.

Todas as tabelas também recebem as colunas de linhagem:

| Coluna | Tipo | Descrição |
|---|---|---|
| `_run_id` | `string` | Identificador da execução |
| `_ingested_at` | `datetime64[ns, UTC]` | Momento da ingestão (UTC) |
| `_source` | `string` | Endpoint de origem |

A quarentena (`data/quarantine/<dataset>/...`) tem as mesmas colunas e mais `_reject_reason` (`coluna:regra` separados por `;`).

Formato: Parquet `zstd`, um arquivo `part-00000.parquet` por partição.

## `meetings`

- Endpoint: `/meetings`
- Chave de negócio (única): `meeting_key`
- Partição: `season=YYYY`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `meeting_key` | `Int64` | sim | >= 1 |
| `year` | `Int64` | sim | [2018, 2100] |
| `meeting_name` | `string` | sim | tamanho >= 1 |
| `meeting_official_name` | `string` | não | — |
| `circuit_key` | `Int64` | não | — |
| `circuit_short_name` | `string` | não | — |
| `country_code` | `string` | não | — |
| `country_name` | `string` | não | — |
| `location` | `string` | não | — |
| `gmt_offset` | `string` | não | — |
| `date_start` | `datetime64[ns, UTC]` | sim | — |
| `date_end` | `datetime64[ns, UTC]` | não | — |
| `is_cancelled` | `boolean` | não | — |

## `sessions`

- Endpoint: `/sessions`
- Chave de negócio (única): `session_key`
- Partição: `season=YYYY`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `year` | `Int64` | sim | [2018, 2100] |
| `session_name` | `string` | sim | tamanho >= 1 |
| `session_type` | `string` | sim | tamanho >= 1 |
| `date_start` | `datetime64[ns, UTC]` | sim | — |
| `date_end` | `datetime64[ns, UTC]` | não | — |
| `circuit_key` | `Int64` | não | — |
| `circuit_short_name` | `string` | não | — |
| `country_name` | `string` | não | — |
| `location` | `string` | não | — |
| `gmt_offset` | `string` | não | — |
| `is_cancelled` | `boolean` | não | — |

## `drivers`

O campo depreciado `country_code` é descartado.

- Endpoint: `/drivers`
- Chave de negócio (única): `session_key, driver_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `name_acronym` | `string` | não | tamanho 3 |
| `broadcast_name` | `string` | não | — |
| `full_name` | `string` | não | — |
| `first_name` | `string` | não | — |
| `last_name` | `string` | não | — |
| `team_name` | `string` | não | — |
| `team_colour` | `string` | não | regex `^[0-9A-Fa-f]{6}$` |
| `headshot_url` | `string` | não | — |
| `country_code` | `string` | não | tamanho 3 |

## `session_results`

Em classificação a API devolve `duration`/`gap_to_leader` como lista `[Q1, Q2, Q3]`; o silver guarda o último valor não nulo (a melhor fase alcançada). `gap_to_leader` é texto porque pode valer `"+1 LAP"`.

- Endpoint: `/session_result`
- Chave de negócio (única): `session_key, driver_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `position` | `Int64` | não | [1, 30] |
| `number_of_laps` | `Int64` | não | >= 0 |
| `points` | `Float64` | não | [0, 50] |
| `duration` | `Float64` | não | (0, 20000] |
| `gap_to_leader` | `string` | não | — |
| `dnf` | `boolean` | não | — |
| `dns` | `boolean` | não | — |
| `dsq` | `boolean` | não | — |

## `laps`

`segments_sector_*` são listas na API e ficam como texto JSON; vêm nulos em corridas.

- Endpoint: `/laps`
- Chave de negócio (única): `session_key, driver_number, lap_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `lap_number` | `Int64` | sim | [1, 100] |
| `date_start` | `datetime64[ns, UTC]` | não | — |
| `lap_duration` | `Float64` | não | (0, 600] |
| `duration_sector_1` | `Float64` | não | (0, 600] |
| `duration_sector_2` | `Float64` | não | (0, 600] |
| `duration_sector_3` | `Float64` | não | (0, 600] |
| `i1_speed` | `Int64` | não | [0, 400] |
| `i2_speed` | `Int64` | não | [0, 400] |
| `st_speed` | `Int64` | não | [0, 400] |
| `is_pit_out_lap` | `boolean` | não | — |
| `segments_sector_1` | `string` | não | — |
| `segments_sector_2` | `string` | não | — |
| `segments_sector_3` | `string` | não | — |

## `stints`

- Endpoint: `/stints`
- Chave de negócio (única): `session_key, driver_number, stint_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `stint_number` | `Int64` | sim | [1, 20] |
| `compound` | `string` | não | um de: HARD, INTERMEDIATE, MEDIUM, SOFT, TEST_UNKNOWN, UNKNOWN, WET |
| `lap_start` | `Int64` | não | >= 1 |
| `lap_end` | `Int64` | não | >= 1 |
| `tyre_age_at_start` | `Int64` | não | >= 0 |

Regra entre colunas: `lap_end_gte_lap_start`.

## `pit_stops`

O campo depreciado `pit_duration` é descartado.

- Endpoint: `/pit`
- Chave de negócio (única): `session_key, driver_number, lap_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `lap_number` | `Int64` | sim | [1, 100] |
| `date` | `datetime64[ns, UTC]` | sim | — |
| `lane_duration` | `Float64` | não | (0, 600] |
| `stop_duration` | `Float64` | não | (0, 120] |

## `weather`

- Endpoint: `/weather`
- Chave de negócio (única): `session_key, date`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `date` | `datetime64[ns, UTC]` | sim | — |
| `air_temperature` | `Float64` | não | [-10, 60] |
| `track_temperature` | `Float64` | não | [-10, 80] |
| `humidity` | `Float64` | não | [0, 100] |
| `pressure` | `Float64` | não | [800, 1100] |
| `wind_speed` | `Float64` | não | [0, 50] |
| `wind_direction` | `Int64` | não | [0, 360] |
| `rainfall` | `boolean` | não | — |

## `starting_grid`

- Endpoint: `/starting_grid`
- Chave de negócio (única): `session_key, driver_number`
- Partição: `season=YYYY/meeting_key=N`

| Coluna | Tipo | Obrigatória | Regras |
|---|---|---|---|
| `session_key` | `Int64` | sim | >= 1 |
| `meeting_key` | `Int64` | sim | >= 1 |
| `driver_number` | `Int64` | sim | [1, 99] |
| `position` | `Int64` | não | [1, 30] |
| `lap_duration` | `Float64` | não | (0, 600] |
