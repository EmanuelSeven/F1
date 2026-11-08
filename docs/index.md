# F1 — Dashboard

O projeto `f1` extrai dados históricos (2023 em diante) da [OpenF1 API](https://openf1.org/docs/) — gratuita e sem autenticação — e os grava num data lake local em camadas:

| Camada | Formato | Conteúdo |
|---|---|---|
| `data/bronze/` | JSON | Resposta bruta da API, por endpoint e partição |
| `data/silver/` | Parquet (`zstd`) | Dados tipados, validados e com colunas de linhagem |
| `data/quarantine/` | Parquet | Registros rejeitados pela validação, com o motivo |

## Escopo da v0.1

Datasets do núcleo da corrida: `meetings`, `sessions`, `drivers`, `session_results`, `laps`, `stints`, `pit_stops`, `weather` e `starting_grid` (grade de largada). Telemetria (`car_data`, `location`, `position`, `intervals`), `team_radio`, `overtakes`, `race_control`, endpoints de campeonato (beta) e dados em tempo real (pagos) estão fora do escopo.

## Início rápido

=== "Ingestão"

    ```bash
    poetry install
    poetry run python -m f1 calendar --year 2024
    poetry run python -m f1 meeting --meeting-key 1229
    ```

=== "Dashboard"

    ```bash
    poetry run task dashboard
    ```

=== "Documentação"

    ```bash
    poetry install --with docs
    poetry run task docs
    ```

!!! warning "Sessões ao vivo"
    Durante uma sessão de F1 ao vivo a OpenF1 bloqueia **todo** o acesso gratuito (inclusive dados históricos) e responde `401`. O cliente lança `OpenF1AccessError` sem tentar de novo e sem sobrescrever partições; basta reexecutar depois que a sessão terminar.

## Por onde seguir

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Execução local](execucao-local.md)**

    Instalação, variáveis de ambiente, CLI e dashboard.

-   :material-sitemap: **[Arquitetura](arquitetura.md)**

    Camadas, fluxo de dados e decisões de projeto.

-   :material-table: **[Dicionário de dados](datasets.md)**

    Colunas, tipos, chaves e partições de cada dataset silver.

-   :material-test-tube: **[Testes](testes.md)**

    Unitários, integração e metas de cobertura.

</div>
