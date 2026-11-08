# OpenF1 API — Resumo

Fonte: https://openf1.org/docs/

API open-source e **não oficial** (sem vínculo com a Fórmula 1) com dados de F1 em tempo real e históricos.

## 1. Visão geral

| Item | Detalhe |
|---|---|
| URL base | `https://api.openf1.org/v1/{endpoint}` |
| Dados históricos | A partir de **2023**, gratuitos e **sem autenticação** |
| Dados em tempo real | Exigem **assinatura paga** (com autenticação) |
| Formato padrão | JSON |
| CSV | Adicionar `csv=true` na query |

Frequência de atualização (aproximada):
- `car_data` e `location`: ~3,7 Hz
- `intervals`: a cada ~4 s (apenas corridas)
- `weather`: a cada 1 min
- `meetings` e `sessions`: diariamente à meia-noite UTC

## 2. Filtros e consultas

- Filtre por qualquer atributo (menos arrays) direto na URL: `?driver_number=1&session_key=9158`
- Operadores de comparação: `=`, `>`, `<`, `>=`, `<=` → `speed>=315`
- Múltiplos valores: repita o parâmetro → `driver_number=4&driver_number=81`
- Booleanos: `is_pit_out_lap=true`
- Datas: ISO 8601 ou qualquer formato aceito pelo `dateutil.parser` do Python
  - Intervalo: `date>=2023-09-01&date<=2023-09-30`
- Codifique espaços e caracteres especiais (`%20`, `%3E%3D`)
- **`latest`**: use em `meeting_key` ou `session_key` para pegar o evento/sessão atual ou mais recente → `session_key=latest`

## 3. Chaves principais

A maioria dos endpoints compartilha estes campos, usados para cruzar os dados:

- `meeting_key` — identifica o fim de semana do GP (ou teste)
- `session_key` — identifica a sessão (treino, quali, sprint, corrida)
- `driver_number` — número do piloto
- `date` — timestamp do registro

Fluxo típico: `meetings` → `sessions` → (`drivers`, `laps`, `car_data`, ...) filtrando por `session_key`.

## 4. Endpoints

### Calendário e sessões
| Endpoint | Descrição | Campos principais |
|---|---|---|
| `/meetings` | Fins de semana de GP ou testes | `meeting_name`, `circuit_short_name`, `country_name`, `location`, `date_start`, `date_end`, `year`, `is_cancelled`, `gmt_offset` |
| `/sessions` | Sessões de um fim de semana | `session_name`, `session_type`, `date_start`, `date_end`, `circuit_short_name`, `country_name`, `year`, `is_cancelled` |

### Pilotos e classificação
| Endpoint | Descrição | Campos principais |
|---|---|---|
| `/drivers` | Dados do piloto em uma sessão | `full_name`, `name_acronym`, `broadcast_name`, `team_name`, `team_colour`, `headshot_url` |
| `/session_result` | Resultado final da sessão | `position`, `duration`, `gap_to_leader`, `number_of_laps`, `dnf`, `dns`, `dsq` |
| `/starting_grid` | Grid de largada | `position`, `lap_duration` |
| `/championship_drivers` *(beta)* | Classificação de pilotos (só corridas) | `position_start/current`, `points_start/current` |
| `/championship_teams` *(beta)* | Classificação de equipes (só corridas) | `team_name`, `position_start/current`, `points_start/current` |

### Telemetria e posição
| Endpoint | Descrição | Campos principais |
|---|---|---|
| `/car_data` | Telemetria do carro (~3,7 Hz) | `speed`, `rpm`, `n_gear`, `throttle`, `brake`, `drs` |
| `/location` | Posição 3D aproximada do carro (~3,7 Hz) | `x`, `y`, `z`, `date` |
| `/position` | Posição do piloto ao longo da sessão | `position`, `date` |
| `/intervals` | Diferença para o carro à frente e para o líder (só corridas) | `interval`, `gap_to_leader` |

### Voltas, pneus e pit stops
| Endpoint | Descrição | Campos principais |
|---|---|---|
| `/laps` | Dados por volta | `lap_number`, `lap_duration`, `duration_sector_1..3`, `i1_speed`, `i2_speed`, `st_speed`, `is_pit_out_lap`, `segments_sector_1..3` |
| `/stints` | Períodos contínuos de pilotagem (por jogo de pneus) | `stint_number`, `compound`, `lap_start`, `lap_end`, `tyre_age_at_start` |
| `/pit` | Passagens pelo pit lane | `stop_duration`, `lane_duration`, `lap_number` |
| `/overtakes` | Ultrapassagens / trocas de posição (só corridas) | `overtaking_driver_number`, `overtaken_driver_number`, `position` |

### Corrida e ambiente
| Endpoint | Descrição | Campos principais |
|---|---|---|
| `/race_control` | Bandeiras, safety car, incidentes, status | `category`, `flag`, `message`, `scope`, `sector`, `lap_number`, `qualifying_phase` |
| `/team_radio` | Áudios selecionados de rádio piloto-equipe | `recording_url`, `date` |
| `/weather` | Condições da pista e do ar | `air_temperature`, `track_temperature`, `humidity`, `pressure`, `rainfall`, `wind_speed`, `wind_direction` |

## 5. Exemplos

```text
GET https://api.openf1.org/v1/meetings?year=2026&country_name=Singapore
GET https://api.openf1.org/v1/sessions?country_name=Belgium&session_name=Sprint%20Qualifying&year=2023
GET https://api.openf1.org/v1/drivers?driver_number=1&session_key=9158
GET https://api.openf1.org/v1/car_data?driver_number=55&session_key=9159&speed>=315
GET https://api.openf1.org/v1/laps?session_key=9161&driver_number=63&lap_number=8
GET https://api.openf1.org/v1/stints?session_key=9165&tyre_age_at_start>=3
GET https://api.openf1.org/v1/session_result?session_key=7782&position<=3
GET https://api.openf1.org/v1/weather?meeting_key=1208&track_temperature>=52
GET https://api.openf1.org/v1/sessions?year=2023&csv=true
```

Python:

```python
import requests

resp = requests.get(
    "https://api.openf1.org/v1/laps",
    params={"session_key": 9161, "driver_number": 63},
)
laps = resp.json()  # lista de dicts
```

## 6. Limitações e observações

- Dados de `segments_sector_*` em `/laps` **não estão disponíveis durante corridas**.
- `/team_radio` não cobre todas as sessões; a cobertura caiu bastante a partir de 2026.
- `/overtakes` é só para corridas e pode estar incompleto.
- Endpoints de campeonato estão em **beta** e valem só para corridas.
- Campos **depreciados** (removidos após a temporada 2026): `country_code` (drivers) e `pit_duration` (pit).
- Cores dos segmentos podem não bater com as exibidas na TV.
- Coordenadas de `/location` têm origem arbitrária e não indicam a posição lateral na pista.
- A documentação não detalha limites de requisição (rate limit) para o uso gratuito.
