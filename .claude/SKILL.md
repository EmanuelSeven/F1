# Padrões de Engenharia — Projeto `f1`

Este documento define as regras, padrões e boas práticas **obrigatórias** para o desenvolvimento do projeto `f1`, um projeto Python orientado a engenharia de dados, construído sob padrão enterprise.

Toda contribuição — código, testes, documentação ou configuração — deve estar em conformidade com este documento. Pull Requests que violem estas regras não serão aprovados.

> **Convenção de linguagem:** os termos **DEVE**, **NÃO DEVE**, **PROIBIDO** e **RECOMENDADO** indicam o nível de obrigatoriedade de cada regra.

---

## Sumário

1. [Estrutura de diretórios](#1-estrutura-de-diretórios)
2. [Ambiente e dependências (Python 3.13 + Poetry)](#2-ambiente-e-dependências-python-313--poetry)
3. [Modularização e arquitetura](#3-modularização-e-arquitetura)
4. [Qualidade de código (Ruff + MyPy)](#4-qualidade-de-código-ruff--mypy)
5. [Testes (pytest)](#5-testes-pytest)
6. [Documentação (MkDocs Material)](#6-documentação-mkdocs-material)
7. [Boas práticas adicionais](#7-boas-práticas-adicionais)
8. [Padrões de Engenharia de Dados](#8-padrões-de-engenharia-de-dados)
9. [Observabilidade](#9-observabilidade)
10. [Qualidade de dados](#10-qualidade-de-dados)
11. [Pipeline de CI/CD](#11-pipeline-de-cicd)
12. [Padrões de Pull Request](#12-padrões-de-pull-request)
13. [Convenções de nomenclatura e imports](#13-convenções-de-nomenclatura-e-imports)
14. [Checklist final](#14-checklist-final)

---

## 1. Estrutura de diretórios

O projeto **DEVE** seguir o layout `src/`, que isola o código-fonte do pacote e garante que os testes sejam executados contra o pacote instalado, e não contra arquivos soltos na raiz.

### Estrutura de referência

```text
f1/
├── pyproject.toml          # Metadados, dependências e configuração de ferramentas
├── poetry.lock             # Versões travadas das dependências (versionado)
├── .python-version         # Versão padrão do Python do projeto (versionado)
├── .env.example            # Modelo de variáveis de ambiente (sem valores reais)
├── .editorconfig           # Padrão de encoding e formatação de arquivos
├── .gitignore
├── .pre-commit-config.yaml # Hooks de pré-commit (recomendado)
├── .github/
│   └── workflows/
│       └── ci.yml          # Pipeline de CI/CD
├── mkdocs.yml              # Configuração da documentação
├── README.md
├── src/
│   └── f1/
│       ├── __init__.py
│       ├── __main__.py     # Ponto de entrada (python -m f1)
│       ├── config/         # Configurações e leitura de variáveis de ambiente
│       ├── domain/         # Entidades, regras de negócio, contratos (sem I/O)
│       ├── ingestion/      # Extração de dados de fontes externas (APIs, arquivos, bancos)
│       ├── processing/     # Transformação, limpeza, agregação e validação de dados
│       ├── quality/        # Schemas e regras de qualidade de dados
│       ├── storage/        # Persistência (data lake, banco, arquivos de saída)
│       ├── pipelines/      # Orquestração: compõe ingestion → processing → storage
│       └── utils/          # Utilitários genéricos e transversais (logging, métricas, datas)
├── tests/
│   ├── conftest.py         # Fixtures compartilhadas
│   ├── unit/               # Testes unitários (isolados, sem I/O externo)
│   └── integration/        # Testes de integração (I/O real ou simulado)
└── docs/
    ├── index.md
    ├── arquitetura.md
    ├── estrutura.md
    ├── execucao-local.md
    ├── testes.md
    └── contribuicao.md
```

### Regras

- Todo código de produção **DEVE** residir em `src/f1/`.
- **PROIBIDO** criar módulos de código-fonte na raiz do repositório.
- Cada subpacote **DEVE** conter um `__init__.py`.
- O diretório `tests/` **DEVE** espelhar a estrutura de `src/f1/` (ex.: `src/f1/processing/laps.py` → `tests/unit/processing/test_laps.py`).

---

## 2. Ambiente e dependências (Python 3.13 + Poetry)

### 2.1 Versão do Python

- A versão oficial do projeto é **Python 3.13**. Todos os ambientes (local, CI/CD, containers, produção) **DEVEM** utilizar a mesma versão `3.13.x`.
- O `pyproject.toml` **DEVE** declarar `requires-python = ">=3.13,<3.14"`.
- O arquivo `.python-version` (conteúdo: `3.13`) **DEVE** ser versionado como referência da versão padrão.
- A ferramenta de instalação do Python é livre. O **pyenv** é **RECOMENDADO**, mas não obrigatório; são igualmente aceitos o `py` launcher do Windows, `pyenv-win`, imagens Docker oficiais (`python:3.13-slim`) e Dev Containers.

```toml
# pyproject.toml
[project]
requires-python = ">=3.13,<3.14"
```

```bash
# Opção A — pyenv / pyenv-win (recomendado)
pyenv install 3.13
pyenv local 3.13                         # gera .python-version
poetry env use $(pyenv which python)

# Opção B — Windows com py launcher
py -3.13 --version
poetry env use (py -3.13 -c "import sys; print(sys.executable)")   # PowerShell

# Opção C — Docker / Dev Container
# FROM python:3.13-slim

# Conferir a versão utilizada pela virtualenv
poetry run python --version
```

### 2.2 Poetry (uso obrigatório)

- O **Poetry** é a **única** ferramenta autorizada para gerenciar dependências e o ambiente virtual.
- O próprio Poetry **DEVE** ser instalado pelo instalador oficial ou via `pipx install poetry`, fora do ambiente do projeto.
- **PROIBIDO:** `pip install`, `pip install --user`, `pip install -r requirements.txt` ou qualquer uso direto do `pip` no projeto.
- **PROIBIDO:** criar ambientes virtuais manualmente (`python -m venv`, `virtualenv`, `conda`).
- **PROIBIDO:** manter arquivos `requirements.txt` como fonte de verdade das dependências.
- O `poetry.lock` **DEVE** ser versionado e atualizado no mesmo commit que altera dependências.

### 2.3 Comandos essenciais

```bash
# Instalar dependências principais + grupo dev a partir do poetry.lock
poetry install

# Instalar incluindo o grupo docs (documentação / CI)
poetry install --with docs

# Instalar apenas dependências de produção (build de imagem, deploy)
poetry install --only main

# Adicionar dependência de produção
poetry add pandas

# Adicionar dependência de desenvolvimento
poetry add --group dev pytest

# Adicionar dependência de documentação
poetry add --group docs mkdocs-material

# Remover dependência
poetry remove pandas

# Atualizar dependências respeitando as restrições do pyproject.toml
poetry update

# Executar comandos dentro da virtualenv
poetry run python -m f1
poetry run pytest

# Ativar a virtualenv no shell atual
poetry shell                               # requer o plugin poetry-plugin-shell no Poetry 2.x
eval $(poetry env activate)                # Linux/macOS (Poetry 2.x, nativo)
Invoke-Expression (poetry env activate)    # Windows PowerShell (Poetry 2.x, nativo)

# Inspecionar a virtualenv
poetry env info
```

### 2.4 Grupos de dependências

As dependências **DEVEM** ser separadas por finalidade, evitando a instalação de ferramentas desnecessárias em ambientes de build e produção.

| Grupo  | Finalidade                         | Pacotes obrigatórios                                              |
|--------|------------------------------------|-------------------------------------------------------------------|
| `main` | Execução da aplicação              | Somente o necessário em runtime                                   |
| `dev`  | Qualidade, testes e tipagem        | `ruff`, `pytest`, `pytest-cov`, `pytest-mock`, `mypy`, `pre-commit` |
| `docs` | Geração da documentação (opcional) | `mkdocs`, `mkdocs-material`                                       |

```bash
poetry add --group dev ruff pytest pytest-cov pytest-mock mypy pre-commit
poetry add --group docs mkdocs mkdocs-material
```

O grupo `docs` **DEVE** ser marcado como opcional, sendo instalado apenas com `--with docs`:

```toml
# pyproject.toml
[tool.poetry.group.docs]
optional = true
```

### 2.5 Versionamento semântico

O projeto **DEVE** seguir [Semantic Versioning](https://semver.org/lang/pt-BR/) no formato `MAJOR.MINOR.PATCH`:

| Tipo de mudança                                   | Incremento | Exemplo           |
|---------------------------------------------------|------------|-------------------|
| Quebra de compatibilidade (contrato, schema, API) | `MAJOR`    | `1.4.2` → `2.0.0` |
| Nova funcionalidade retrocompatível               | `MINOR`    | `1.4.2` → `1.5.0` |
| Correção de bug retrocompatível                   | `PATCH`    | `1.4.2` → `1.4.3` |

```bash
poetry version patch    # 0.1.0 → 0.1.1
poetry version minor    # 0.1.1 → 0.2.0
poetry version major    # 0.2.0 → 1.0.0
```

- Alterações de schema de dados consumidos por terceiros **DEVEM** ser tratadas como `MAJOR`.
- Restrições de dependências **DEVEM** usar intervalos explícitos (ex.: `pandas = ">=2.2,<3.0"`), evitando `*`.

---

## 3. Modularização e arquitetura

### 3.1 Separação por camadas

| Camada        | Responsabilidade                                                   | Pode depender de                   |
|---------------|--------------------------------------------------------------------|------------------------------------|
| `domain`      | Entidades, regras de negócio, validações e contratos (interfaces)  | Nenhuma outra camada do projeto    |
| `ingestion`   | Extração de dados de fontes externas                               | `domain`, `config`, `utils`        |
| `processing`  | Transformação, limpeza, enriquecimento e agregação                 | `domain`, `utils`                  |
| `quality`     | Schemas e regras de validação de dados                             | `domain`, `utils`                  |
| `storage`     | Escrita e leitura em destinos persistentes                         | `domain`, `config`, `utils`        |
| `pipelines`   | Orquestração do fluxo ponta a ponta                                | Todas as camadas                   |
| `config`      | Carregamento de configurações e variáveis de ambiente              | `utils`                            |
| `utils`       | Funções genéricas, sem conhecimento de negócio                     | Nenhuma outra camada do projeto    |

**Regra de dependência:** a camada `domain` **NÃO DEVE** importar bibliotecas de infraestrutura (clientes HTTP, drivers de banco, SDKs de cloud). A infraestrutura depende do domínio, nunca o contrário.

### 3.2 Separação entre regra de negócio e infraestrutura

```python
# src/f1/domain/models.py — regra de negócio pura, sem I/O
from dataclasses import dataclass


@dataclass(frozen=True)
class LapTime:
    driver_code: str
    lap_number: int
    milliseconds: int

    def is_valid(self) -> bool:
        return self.lap_number > 0 and self.milliseconds > 0
```

```python
# src/f1/domain/ports.py — contrato que a infraestrutura deve implementar
from typing import Protocol

from f1.domain.models import LapTime


class LapTimeSource(Protocol):
    def fetch(self, season: int, round_number: int) -> list[LapTime]: ...
```

```python
# src/f1/ingestion/api_client.py — infraestrutura implementando o contrato
import logging

import httpx

from f1.domain.models import LapTime

logger = logging.getLogger(__name__)


class HttpLapTimeSource:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)

    def fetch(self, season: int, round_number: int) -> list[LapTime]:
        logger.info("fetching_laps", extra={"season": season, "round": round_number})
        response = self._client.get(f"/{season}/{round_number}/laps.json")
        response.raise_for_status()
        return [self._to_domain(item) for item in response.json()["laps"]]

    @staticmethod
    def _to_domain(item: dict[str, object]) -> LapTime:
        return LapTime(
            driver_code=str(item["driver"]),
            lap_number=int(item["lap"]),
            milliseconds=int(item["ms"]),
        )
```

```python
# src/f1/pipelines/lap_times.py — orquestração por injeção de dependência
from f1.domain.ports import LapTimeSource
from f1.processing.laps import filter_valid_laps


def run_lap_times_pipeline(
    source: LapTimeSource, season: int, round_number: int
) -> int:
    laps = source.fetch(season, round_number)
    valid_laps = filter_valid_laps(laps)
    return len(valid_laps)
```

### 3.3 Regras de modularização

- Funções **DEVEM** ser pequenas, coesas e com responsabilidade única (referência: até ~30 linhas).
- Funções de transformação **DEVEM** ser, sempre que possível, **puras** (mesma entrada → mesma saída, sem efeitos colaterais), o que garante testabilidade e idempotência.
- **PROIBIDO:** scripts monolíticos que misturam extração, transformação, carga e configuração em um único arquivo.
- **PROIBIDO:** lógica executada em nível de módulo (no import). Código executável **DEVE** estar em funções e ser acionado por um ponto de entrada (`__main__.py`).
- Dependências externas (clientes, conexões, caminhos) **DEVEM** ser injetadas por parâmetro, não instanciadas dentro da regra de negócio.

```python
# src/f1/__main__.py
from f1.config.settings import get_settings
from f1.ingestion.api_client import HttpLapTimeSource
from f1.pipelines.lap_times import run_lap_times_pipeline
from f1.utils.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    source = HttpLapTimeSource(base_url=settings.api_base_url)
    run_lap_times_pipeline(source, season=2026, round_number=1)


if __name__ == "__main__":
    main()
```

---

## 4. Qualidade de código (Ruff + MyPy)

- O código **DEVE** seguir a **PEP 8**.
- O **Ruff** é a ferramenta oficial para **lint**, **formatação** e **organização de imports** (substitui flake8, black e isort).
- O **MyPy** é a ferramenta oficial de **validação estática de tipos**, garantindo que os type hints sejam efetivamente verificados.
- Toda configuração **DEVE** estar centralizada no `pyproject.toml`. **PROIBIDO** criar `ruff.toml`, `mypy.ini`, `.flake8`, `setup.cfg` ou equivalentes.
- O código **DEVE** passar **100%** no lint, na verificação de formatação e na checagem de tipos antes da abertura de qualquer PR.
- Supressões (`# noqa`, `# type: ignore`) **DEVEM** ser pontuais, indicar a regra específica (`# noqa: E501`, `# type: ignore[arg-type]`) e ser justificadas no PR.

### 4.1 Configuração do Ruff (`pyproject.toml`)

```toml
[tool.ruff]
line-length = 88
target-version = "py313"
src = ["src", "tests"]
extend-exclude = ["docs", "site"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle (erros)
    "W",    # pycodestyle (avisos)
    "F",    # pyflakes
    "I",    # isort (organização de imports)
    "N",    # pep8-naming
    "B",    # flake8-bugbear
    "UP",   # pyupgrade
    "ANN",  # flake8-annotations (type hints obrigatórios)
    "T20",  # flake8-print (proíbe print)
    "S",    # flake8-bandit (segurança)
    "SIM",  # flake8-simplify
    "TID",  # flake8-tidy-imports (imports absolutos)
    "PL",   # pylint
    "RUF",  # regras específicas do Ruff
]
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",    # uso de assert é esperado em testes
    "ANN",     # anotações não obrigatórias em testes
    "PLR2004", # valores literais em asserções
]

[tool.ruff.lint.isort]
known-first-party = ["f1"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
docstring-code-format = true
```

### 4.2 Configuração do MyPy (`pyproject.toml`)

```toml
[tool.mypy]
python_version = "3.13"
mypy_path = "src"
packages = ["f1"]
strict = true
warn_unreachable = true
pretty = true
plugins = ["pydantic.mypy"]   # necessário ao utilizar pydantic / pydantic-settings

# Bibliotecas de terceiros sem type hints: liberar somente o módulo específico
# [[tool.mypy.overrides]]
# module = ["biblioteca_sem_tipos.*"]
# ignore_missing_imports = true
```

### 4.3 Comandos

```bash
# Formatar o código
poetry run ruff format .

# Verificar lint
poetry run ruff check .

# Corrigir automaticamente (inclui ordenação de imports)
poetry run ruff check . --fix

# Validar tipagem estática
poetry run mypy src

# Validação sem alterar arquivos (uso em CI e antes do PR)
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy src
```

---

## 5. Testes (pytest)

- O **pytest** é o framework de testes obrigatório.
- Os testes **DEVEM** ser executados exclusivamente via `poetry run pytest`.
- Arquivos de teste **DEVEM** seguir o padrão `test_*.py`; funções, o padrão `test_<comportamento>`.

### 5.1 Política de cobertura

| Escopo                                                  | Cobertura   | Natureza                         |
|---------------------------------------------------------|-------------|----------------------------------|
| Projeto (`src/f1`)                                      | **≥ 50%**   | **Obrigatória** — bloqueia o build |
| Novos módulos                                           | ≥ 60%       | Meta                             |
| Serviços (`ingestion`, `storage`, `pipelines`)          | ≥ 70%       | Meta                             |
| Regras críticas (`domain`, `quality`, `processing`)     | ≥ 80%       | Meta                             |

- A cobertura mínima de 50% é validada automaticamente pelo `--cov-fail-under=50`.
- As metas **DEVEM** ser acompanhadas na revisão de PR; reduções de cobertura em regras críticas **DEVEM** ser justificadas.

```bash
# Verificar meta de um escopo específico (após rodar poetry run pytest)
poetry run coverage report --include="src/f1/domain/*" --fail-under=80
poetry run coverage report --include="src/f1/pipelines/*" --fail-under=70
```

### 5.2 Separação entre unitários e integração

| Tipo        | Diretório             | Características                                                         |
|-------------|-----------------------|-------------------------------------------------------------------------|
| Unitário    | `tests/unit/`         | Isolado, rápido, determinístico, **sem** rede, banco ou disco real      |
| Integração  | `tests/integration/`  | Valida interação entre componentes e recursos externos (ou emulados)    |

- Testes unitários **NÃO DEVEM** acessar rede, banco de dados ou sistema de arquivos real. Use mocks, stubs ou `tmp_path`.
- Testes de integração **DEVEM** ser marcados com `@pytest.mark.integration`.

### 5.3 Configuração (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = [
    "--strict-markers",
    "--cov=src/f1",
    "--cov-report=term-missing",
    "--cov-fail-under=50",
]
markers = [
    "integration: testes que dependem de recursos externos",
]

[tool.coverage.run]
source = ["src/f1"]
branch = true

[tool.coverage.report]
show_missing = true
skip_empty = true
```

### 5.4 Fixtures

Fixtures compartilhadas **DEVEM** ficar em `tests/conftest.py` (ou em `conftest.py` por subdiretório).

```python
# tests/conftest.py
import pytest

from f1.domain.models import LapTime


@pytest.fixture
def sample_laps() -> list[LapTime]:
    return [
        LapTime(driver_code="VER", lap_number=1, milliseconds=92_345),
        LapTime(driver_code="HAM", lap_number=1, milliseconds=92_810),
        LapTime(driver_code="LEC", lap_number=0, milliseconds=0),  # inválido
    ]


class FakeLapTimeSource:
    def __init__(self, laps: list[LapTime]) -> None:
        self._laps = laps

    def fetch(self, season: int, round_number: int) -> list[LapTime]:
        return self._laps


@pytest.fixture
def fake_source(sample_laps: list[LapTime]) -> FakeLapTimeSource:
    return FakeLapTimeSource(sample_laps)
```

### 5.5 Exemplos

```python
# tests/unit/processing/test_laps.py
from f1.processing.laps import filter_valid_laps


def test_filter_valid_laps_removes_invalid_entries(sample_laps):
    result = filter_valid_laps(sample_laps)

    assert len(result) == 2
    assert all(lap.is_valid() for lap in result)
```

```python
# tests/unit/pipelines/test_lap_times.py
from f1.pipelines.lap_times import run_lap_times_pipeline


def test_pipeline_returns_number_of_valid_laps(fake_source):
    assert run_lap_times_pipeline(fake_source, season=2026, round_number=1) == 2
```

```python
# tests/integration/test_api_client.py
import pytest

from f1.ingestion.api_client import HttpLapTimeSource


@pytest.mark.integration
def test_http_source_returns_laps():
    source = HttpLapTimeSource(base_url="http://localhost:8080")
    assert isinstance(source.fetch(season=2026, round_number=1), list)
```

### 5.6 Comandos

```bash
# Todos os testes, com verificação de cobertura
poetry run pytest

# Apenas testes unitários
poetry run pytest tests/unit

# Apenas testes de integração
poetry run pytest -m integration

# Excluir testes de integração
poetry run pytest -m "not integration"

# Teste específico
poetry run pytest tests/unit/processing/test_laps.py::test_filter_valid_laps_removes_invalid_entries

# Relatório de cobertura em HTML (saída em htmlcov/)
poetry run pytest --cov-report=html
```

---

## 6. Documentação (MkDocs Material)

- A documentação **DEVE** ser produzida com **MkDocs** e o tema **Material** (`mkdocs-material`), instalados pelo grupo `docs`.
- O conteúdo **DEVE** ser escrito em Markdown (UTF-8) no diretório `docs/` e versionado junto do código, no mesmo repositório.
- Mudanças que alterem arquitetura, execução, configuração ou contratos de dados **DEVEM** atualizar a documentação no mesmo PR.

### 6.1 Documentação técnica mínima

| Documento              | Conteúdo esperado                                                       |
|------------------------|-------------------------------------------------------------------------|
| `arquitetura.md`       | Camadas, fluxo de dados, decisões arquiteturais, fontes e destinos      |
| `estrutura.md`         | Organização de diretórios e responsabilidade de cada módulo             |
| `execucao-local.md`    | Pré-requisitos, instalação, variáveis de ambiente e execução            |
| `testes.md`            | Como rodar testes unitários, de integração e verificar cobertura        |
| `contribuicao.md`      | Fluxo de branches, padrão de commits, PR e checklist de qualidade       |

### 6.2 Configuração (`mkdocs.yml`)

```yaml
site_name: F1 — Documentação Técnica
repo_url: https://github.com/EmanuelSeven/f1
theme:
  name: material
  language: pt-BR
  features:
    - navigation.sections
    - navigation.top
    - content.code.copy
    - search.highlight
markdown_extensions:
  - admonition
  - tables
  - toc:
      permalink: true
  - pymdownx.highlight
  - pymdownx.superfences
nav:
  - Início: index.md
  - Arquitetura: arquitetura.md
  - Estrutura do projeto: estrutura.md
  - Execução local: execucao-local.md
  - Testes: testes.md
  - Como contribuir: contribuicao.md
```

### 6.3 Comandos

```bash
# Instalar dependências de documentação
poetry install --with docs

# Servidor local (http://127.0.0.1:8000)
poetry run mkdocs serve

# Build do site estático (saída em site/), falhando em avisos
poetry run mkdocs build --strict
```

---

## 7. Boas práticas adicionais

### 7.1 Tipagem estática

- Type hints são **obrigatórios** em todas as funções e métodos públicos e privados de `src/` (parâmetros e retorno).
- A tipagem **DEVE** ser validada pelo MyPy em modo `strict` (`poetry run mypy src`).
- Utilize a sintaxe moderna: `list[str]`, `dict[str, int]`, `str | None`.
- **Evite** `Any`; quando inevitável, justifique.

```python
def calculate_average_lap_ms(laps: list[LapTime]) -> float | None:
    if not laps:
        return None
    return sum(lap.milliseconds for lap in laps) / len(laps)
```

### 7.2 Logging estruturado

- **PROIBIDO** o uso de `print` em `src/` (regra `T20` do Ruff).
- Todo módulo **DEVE** obter seu logger com `logging.getLogger(__name__)`.
- Logs **DEVEM** ser estruturados (JSON em staging/prod), com contexto em campos, não concatenado na mensagem.
- **PROIBIDO** registrar secrets, tokens ou dados pessoais em logs.

```python
# src/f1/utils/logging.py
import json
import logging
import sys

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        payload.update(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
```

```python
# Uso
logger = logging.getLogger(__name__)
logger.info("pipeline_finished", extra={"pipeline": "lap_times", "rows": 1_240})
```

### 7.3 Variáveis de ambiente e `.env`

- Configurações sensíveis ou dependentes de ambiente **DEVEM** ser lidas de variáveis de ambiente.
- O arquivo `.env` é de uso **local** e **NÃO DEVE** ser versionado.
- O arquivo `.env.example` **DEVE** ser versionado, listando todas as variáveis com valores fictícios.
- A leitura **DEVE** ser centralizada em `src/f1/config/`; nenhum outro módulo lê `os.environ` diretamente.

```dotenv
# .env.example
F1_ENV=dev
F1_LOG_LEVEL=INFO
F1_API_BASE_URL=https://api.example.com
F1_DB_URL=postgresql://user:password@localhost:5432/f1
```

```python
# src/f1/config/settings.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="F1_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"
    log_level: str = "INFO"
    api_base_url: str
    db_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```bash
poetry add pydantic-settings
```

### 7.4 Gestão de secrets

- **PROIBIDO** comitar secrets, tokens, senhas, chaves de API, certificados ou strings de conexão reais.
- Em staging e produção, secrets **DEVEM** ser fornecidos por um cofre (ex.: AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, HashiCorp Vault) ou pelas variáveis protegidas do CI/CD.
- Secrets expostos acidentalmente **DEVEM** ser revogados imediatamente; remover do histórico não é suficiente.

### 7.5 Separação de ambientes

| Ambiente  | Finalidade                             | Origem da configuração                 | Formato de log |
|-----------|----------------------------------------|----------------------------------------|----------------|
| `dev`     | Desenvolvimento local                  | `.env` local                           | Texto ou JSON  |
| `staging` | Homologação com dados representativos  | Variáveis do CI/CD + cofre de secrets  | JSON           |
| `prod`    | Produção                               | Variáveis do CI/CD + cofre de secrets  | JSON           |

- O ambiente ativo **DEVE** ser definido pela variável `F1_ENV`.
- **PROIBIDO** condicionar regra de negócio ao nome do ambiente (`if env == "prod"`); diferenças entre ambientes **DEVEM** ser expressas apenas por configuração.
- **PROIBIDO** utilizar dados ou credenciais de produção em `dev`.

### 7.6 Encoding de arquivos

- Todos os arquivos de texto do repositório **DEVEM** estar em **UTF-8 sem BOM**, incluindo:
  - Markdown: `README.md`, `SKILL.md`, `docs/*.md`
  - Configuração: `pyproject.toml`, `mkdocs.yml`, `.pre-commit-config.yaml`, `.env.example`, arquivos `*.yml`/`*.yaml`/`*.toml`/`*.json`
  - Código-fonte: `*.py`
- **PROIBIDO** o uso de **UTF-16** (incluindo UTF-16 LE com BOM `0xFF 0xFE`) ou de codificações regionais (`cp1252`, `latin-1`).
- Leitura e escrita de arquivos em código **DEVEM** declarar o encoding explicitamente — no Python 3.13 o padrão no Windows ainda depende da localidade do sistema.

**Motivo:** arquivos em UTF-16 causam falhas como:

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte
```

```python
# Correto
from pathlib import Path

content = Path("docs/index.md").read_text(encoding="utf-8")
with open("output.json", "w", encoding="utf-8") as file:
    file.write(content)

# Incorreto — encoding dependente do sistema operacional
content = open("docs/index.md").read()
```

> **Atenção ao Windows PowerShell 5.1:** os operadores `>` e `>>` e o `Out-File` gravam em UTF-16 LE por padrão, e `-Encoding utf8` grava com BOM. **PROIBIDO** gerar arquivos do projeto com redirecionamento no PowerShell 5.1. Para gravar ou converter um arquivo em UTF-8 sem BOM:

```powershell
$content = Get-Content -Raw -Encoding Unicode .\README.md   # leitura de arquivo em UTF-16
[System.IO.File]::WriteAllText("$PWD\README.md", $content, [System.Text.UTF8Encoding]::new($false))
```

O padrão **DEVE** ser reforçado pelo `.editorconfig`:

```ini
# .editorconfig
root = true

[*]
charset = utf-8
insert_final_newline = true
trim_trailing_whitespace = true
```

### 7.7 Pre-commit (recomendado)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: fix-byte-order-marker   # remove BOM de arquivos UTF-8
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.4   # manter alinhado à versão do ruff no poetry.lock
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: poetry run mypy src
        language: system
        types: [python]
        pass_filenames: false
```

```bash
poetry run pre-commit install           # instala os hooks no repositório
poetry run pre-commit run --all-files   # executa em todos os arquivos
poetry run pre-commit autoupdate        # atualiza as versões dos hooks
```

### 7.8 `.gitignore` mínimo

```gitignore
# Ambiente
.venv/
.env

# Cache e artefatos
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
site/
dist/

# Dados locais
data/
*.parquet
*.csv
```

---

## 8. Padrões de Engenharia de Dados

### 8.1 Idempotência e reprocessamento

- Toda pipeline **DEVE** ser **idempotente**: executar novamente com os mesmos parâmetros **DEVE** produzir exatamente o mesmo resultado no destino.
- O reprocessamento de um período ou partição **NÃO DEVE** gerar registros duplicados.
- Estratégias aceitas:
  - **Sobrescrita de partição** (`overwrite` por partição, nunca da tabela inteira);
  - **Upsert / merge** por chave de negócio determinística;
  - **Escrita atômica**: gravar em local temporário e promover ao destino final apenas após sucesso.
- **PROIBIDO** o uso de `append` cego em cargas que possam ser reexecutadas.
- Toda pipeline **DEVE** aceitar parâmetros explícitos de período/partição (ex.: `season`, `round_number`, `execution_date`), permitindo backfill controlado.

```python
# src/f1/storage/parquet_writer.py
import shutil
from pathlib import Path

import pandas as pd


def write_partition(
    df: pd.DataFrame, base_path: Path, season: int, round_number: int
) -> Path:
    """Sobrescreve a partição de forma atômica, garantindo idempotência."""
    partition = base_path / f"season={season}" / f"round={round_number}"
    staging = partition.with_name(f"{partition.name}.tmp")

    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    df.to_parquet(staging / "part-00000.parquet", index=False, compression="zstd")

    shutil.rmtree(partition, ignore_errors=True)
    staging.rename(partition)
    return partition
```

### 8.2 Formato de armazenamento

- **Parquet** é o formato **preferencial** para dados analíticos e intermediários (colunar, tipado, comprimido).
- Compressão **RECOMENDADA**: `zstd` ou `snappy`.
- CSV e JSON **DEVEM** ser restritos à camada de ingestão bruta (quando a fonte os impõe) ou a exportações para sistemas externos.
- Dados **DEVEM** ser particionados por colunas de baixa cardinalidade e alto uso em filtros (ex.: `season`, `round`, data de referência).

### 8.3 Prevenção de small files

- **Evitar** a geração de muitos arquivos pequenos, que degradam leitura, metadados e custo de armazenamento.
- Tamanho-alvo **RECOMENDADO** por arquivo: **128 MB a 1 GB**.
- **Evitar** particionamento excessivo (ex.: partição por colunas de alta cardinalidade como `driver_id` ou timestamp completo).
- Processos de **compactação** periódica **DEVEM** ser previstos para tabelas com cargas incrementais frequentes.

### 8.4 Rastreabilidade da execução

- Toda execução **DEVE** gerar um identificador único (`run_id`), propagado em logs e métricas.
- Tabelas de saída **DEVEM** conter colunas técnicas de linhagem:

| Coluna          | Descrição                                       |
|-----------------|-------------------------------------------------|
| `_run_id`       | Identificador da execução que gerou o registro  |
| `_ingested_at`  | Timestamp UTC de ingestão                       |
| `_source`       | Origem do dado (endpoint, arquivo, tabela)      |

- Timestamps técnicos **DEVEM** estar em **UTC**.

```python
from datetime import UTC, datetime

import pandas as pd


def add_lineage_columns(df: pd.DataFrame, run_id: str, source: str) -> pd.DataFrame:
    return df.assign(
        _run_id=run_id,
        _ingested_at=datetime.now(UTC),
        _source=source,
    )
```

---

## 9. Observabilidade

Toda pipeline **DEVE** registrar, em log estruturado, as seguintes informações:

| Métrica / evento            | Campo                 | Obrigatório |
|-----------------------------|-----------------------|-------------|
| Início da execução          | `pipeline_started`    | Sim         |
| Término da execução         | `pipeline_finished`   | Sim         |
| Duração                     | `duration_seconds`    | Sim         |
| Registros lidos             | `records_read`        | Sim         |
| Registros processados       | `records_processed`   | Sim         |
| Registros rejeitados        | `records_rejected`    | Sim         |
| Erros                       | `pipeline_failed` + stack trace | Sim |
| Destino da carga            | `destination`         | Sim         |
| Identificador da execução   | `run_id`              | Sim         |

- Falhas **DEVEM** ser registradas com `logger.exception` e propagadas; **PROIBIDO** silenciar exceções (`except Exception: pass`).
- As métricas **DEVEM** ser coletadas de forma padronizada, por meio de utilitário comum em `src/f1/utils/`.

```python
# src/f1/utils/metrics.py
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    pipeline: str
    destination: str
    run_id: str = field(default_factory=lambda: uuid4().hex)
    records_read: int = 0
    records_processed: int = 0
    records_rejected: int = 0


@contextmanager
def track_pipeline(pipeline: str, destination: str) -> Iterator[PipelineMetrics]:
    metrics = PipelineMetrics(pipeline=pipeline, destination=destination)
    started = time.perf_counter()
    logger.info("pipeline_started", extra=asdict(metrics))
    try:
        yield metrics
    except Exception:
        duration = round(time.perf_counter() - started, 3)
        logger.exception(
            "pipeline_failed", extra={**asdict(metrics), "duration_seconds": duration}
        )
        raise
    duration = round(time.perf_counter() - started, 3)
    logger.info(
        "pipeline_finished", extra={**asdict(metrics), "duration_seconds": duration}
    )
```

```python
# Exemplo de pipeline instrumentada
with track_pipeline("lap_times", destination=str(output_path)) as metrics:
    laps = source.fetch(season, round_number)
    metrics.records_read = len(laps)

    result = validate_laps(laps_to_dataframe(laps))
    metrics.records_processed = len(result.valid)
    metrics.records_rejected = len(result.rejected)

    write_partition(result.valid, output_path, season, round_number)
```

Exemplo de saída:

```json
{"timestamp": "2026-11-08T10:15:42+0000", "level": "INFO", "logger": "f1.utils.metrics", "message": "pipeline_finished", "pipeline": "lap_times", "destination": "data/silver/lap_times", "run_id": "9f1c2e...", "records_read": 1240, "records_processed": 1232, "records_rejected": 8, "duration_seconds": 3.418}
```

---

## 10. Qualidade de dados

### 10.1 Validações obrigatórias

Todo dado que atravessa a fronteira entre camadas (ingestão → processamento → armazenamento) **DEVE** ser validado quanto a:

| Dimensão        | O que validar                                                   | Exemplo                                        |
|-----------------|-----------------------------------------------------------------|------------------------------------------------|
| **Schema**      | Presença e nome das colunas esperadas; ausência de colunas extras | `driver_code`, `lap_number`, `milliseconds`  |
| **Tipos**       | Tipo de dado de cada coluna                                     | `lap_number` é inteiro                         |
| **Nulidade**    | Campos obrigatórios não nulos                                   | `driver_code` não pode ser nulo                |
| **Ranges**      | Limites mínimos e máximos aceitáveis                            | `milliseconds` entre 1 e 600 000               |
| **Unicidade**   | Ausência de duplicidade pela chave de negócio                   | `(driver_code, lap_number)` único              |
| **Consistência**| Regras entre campos e referências entre conjuntos               | volta pertence a piloto existente na corrida   |

### 10.2 Regras

- Schemas de dados **DEVEM** ser declarados em código (`src/f1/quality/`) e versionados.
- Registros inválidos **NÃO DEVEM** ser descartados silenciosamente: **DEVEM** ser direcionados para uma área de **quarentena** com o motivo da rejeição e o `run_id`.
- A pipeline **DEVE** falhar quando a taxa de rejeição ultrapassar o limite configurado (referência: **5%**).
- Violações de **schema** **DEVEM** interromper a pipeline imediatamente.
- É **RECOMENDADO** o uso de bibliotecas especializadas, como **Pandera** (DataFrames) ou **Pydantic** (registros).

### 10.3 Exemplo com Pandera

```bash
poetry add pandera
```

```python
# src/f1/quality/lap_times.py
from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

MAX_REJECTION_RATE = 0.05

LAP_TIMES_SCHEMA = pa.DataFrameSchema(
    columns={
        "driver_code": pa.Column(str, nullable=False, checks=pa.Check.str_length(3, 3)),
        "lap_number": pa.Column(int, nullable=False, checks=pa.Check.in_range(1, 100)),
        "milliseconds": pa.Column(
            int, nullable=False, checks=pa.Check.in_range(1, 600_000)
        ),
    },
    unique=["driver_code", "lap_number"],
    strict=True,
    coerce=False,
)


class DataQualityError(Exception):
    """Taxa de rejeição acima do limite aceitável."""


@dataclass(frozen=True)
class ValidationResult:
    valid: pd.DataFrame
    rejected: pd.DataFrame


def validate_laps(df: pd.DataFrame) -> ValidationResult:
    try:
        valid = LAP_TIMES_SCHEMA.validate(df, lazy=True)
        return ValidationResult(valid=valid, rejected=df.iloc[0:0])
    except SchemaErrors as exc:
        failures = exc.failure_cases
        if failures["index"].isna().any():
            raise  # violação de schema (sem índice de linha): falha imediata
        failed_index = failures["index"].unique()
        rejected = df.loc[df.index.isin(failed_index)]
        valid = df.loc[~df.index.isin(failed_index)]

    if len(df) and len(rejected) / len(df) > MAX_REJECTION_RATE:
        raise DataQualityError(f"rejection rate above {MAX_REJECTION_RATE:.0%}")
    return ValidationResult(valid=valid, rejected=rejected)
```

> Violações de nível de schema (coluna ausente, coluna extra) não possuem índice de linha e, por isso, interrompem a pipeline imediatamente, conforme a regra 10.2.

---

## 11. Pipeline de CI/CD

### 11.1 Etapas obrigatórias

Toda alteração submetida via Pull Request **DEVE** executar, nesta ordem e sem falhas:

| Etapa | Comando                              | Objetivo                              |
|-------|--------------------------------------|---------------------------------------|
| 1     | `poetry install --with docs`         | Instalação reprodutível via lock      |
| 2     | `poetry run ruff format --check .`   | Verificação de formatação             |
| 3     | `poetry run ruff check .`            | Lint e organização de imports         |
| 4     | `poetry run mypy src`                | Validação estática de tipos           |
| 5     | `poetry run pytest`                  | Testes e cobertura mínima (≥ 50%)     |
| 6     | `poetry run mkdocs build --strict`   | Validação da documentação             |

- O status da pipeline **DEVE** ser configurado como **check obrigatório** na proteção da branch `main`.
- **PROIBIDO** realizar merge com qualquer etapa falhando ou ignorada.
- Builds de artefatos de produção **DEVEM** utilizar `poetry install --only main`.

### 11.2 Exemplo (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Instalar Poetry
        run: pipx install poetry

      - name: Instalar dependências
        run: poetry install --with docs

      - name: Formatação
        run: poetry run ruff format --check .

      - name: Lint
        run: poetry run ruff check .

      - name: Tipagem
        run: poetry run mypy src

      - name: Testes
        run: poetry run pytest

      - name: Documentação
        run: poetry run mkdocs build --strict
```

---

## 12. Padrões de Pull Request

### 12.1 Regras

- **PROIBIDO** commit ou merge direto na branch `main`. A `main` **DEVE** ser protegida no repositório remoto.
- Toda alteração **DEVE** ser feita em branch dedicada e integrada via Pull Request.
- O PR **DEVE** passar em **100%** das etapas da pipeline de CI/CD (formatação, lint, tipagem, testes e documentação).
- O PR **DEVE** manter a cobertura mínima de 50%.
- O PR **DEVE** ter ao menos **uma aprovação** de revisor.
- O PR **DEVE** ser pequeno e focado em um único objetivo.

### 12.2 Nomenclatura de branches

```text
feature/<descricao-curta>    # nova funcionalidade
fix/<descricao-curta>        # correção de bug
refactor/<descricao-curta>   # refatoração sem mudança de comportamento
docs/<descricao-curta>       # documentação
chore/<descricao-curta>      # manutenção, dependências, CI
```

### 12.3 Mensagens de commit (Conventional Commits)

```text
feat(ingestion): adiciona cliente para endpoint de voltas
fix(processing): corrige conversão de tempo de volta para milissegundos
docs: documenta execução local
chore(deps): atualiza pandas para 2.2.3
```

### 12.4 Template de descrição

```markdown
## Objetivo
Descrição clara do problema resolvido ou da funcionalidade entregue.

## Alterações
- Item 1
- Item 2

## Impacto em dados
Schemas, tabelas, partições ou contratos afetados (ou "Nenhum").
Necessidade de reprocessamento/backfill (ou "Nenhuma").

## Como testar
Passos ou comandos para validar a alteração.

## Checklist
- [ ] `poetry run ruff format --check .` sem erros
- [ ] `poetry run ruff check .` sem erros
- [ ] `poetry run mypy src` sem erros
- [ ] `poetry run pytest` passando com cobertura ≥ 50%
- [ ] `poetry run mkdocs build --strict` sem erros
- [ ] Testes adicionados/atualizados
- [ ] Pipeline idempotente e com métricas de observabilidade
- [ ] Validações de qualidade de dados aplicadas
- [ ] Documentação atualizada (se aplicável)
- [ ] Arquivos novos em UTF-8 sem BOM
- [ ] Nenhum secret ou dado sensível incluído
```

---

## 13. Convenções de nomenclatura e imports

### 13.1 Nomenclatura

| Elemento                 | Convenção          | Exemplo                          |
|--------------------------|--------------------|----------------------------------|
| Variáveis                | `snake_case`       | `lap_count`, `race_date`         |
| Funções e métodos        | `snake_case`       | `load_race_results()`            |
| Classes                  | `PascalCase`       | `LapTime`, `HttpLapTimeSource`   |
| Constantes               | `UPPER_CASE`       | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Módulos e pacotes        | `snake_case`       | `api_client.py`, `processing/`   |
| Membros privados         | prefixo `_`        | `_to_domain()`, `_client`        |
| Arquivos de teste        | `test_<modulo>.py` | `test_laps.py`                   |

```python
MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 10.0


class RaceResultLoader:
    def load_race_results(self, season: int) -> list[dict[str, object]]:
        retry_count = 0
        ...
```

### 13.2 Imports

- Imports **DEVEM** ser **absolutos**, a partir do pacote `f1`. **PROIBIDO** o uso de imports relativos (`from .models import ...`).
- **PROIBIDO** `from modulo import *`.
- A ordem dos imports é gerida automaticamente pelo Ruff (`I`): biblioteca padrão → terceiros → primeira parte (`f1`).

```python
# Correto
import logging
from pathlib import Path

import pandas as pd

from f1.domain.models import LapTime
from f1.utils.logging import configure_logging

# Incorreto
from .models import LapTime
from f1.domain.models import *
```

---

## 14. Checklist final

Antes de abrir um Pull Request, todos os comandos abaixo **DEVEM** ser executados com sucesso (mesmas etapas da pipeline de CI/CD):

```bash
poetry install --with docs
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy src
poetry run pytest
poetry run mkdocs build --strict
```

Arquivos que **DEVEM** ser versionados:

- `pyproject.toml` e `poetry.lock`
- `.python-version`
- `.env.example`
- `.editorconfig`
- `mkdocs.yml` e `docs/`
- `.github/workflows/ci.yml`
- `.pre-commit-config.yaml` (quando adotado)

Arquivos que **NÃO DEVEM** ser versionados:

- `.env` e qualquer arquivo contendo secrets
- `.venv/`, `__pycache__/`
- `.coverage`, `htmlcov/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`
- `site/`, `dist/`
- Dados brutos ou processados de execução local
