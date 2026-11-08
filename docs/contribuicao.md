# Como contribuir

## Fluxo

1. Crie uma branch a partir da `main` (commit direto na `main` é proibido):
   `feature/…`, `fix/…`, `refactor/…`, `docs/…` ou `chore/…`.
2. Faça commits pequenos em [Conventional Commits](https://www.conventionalcommits.org/pt-br/):
   `feat(ingestion): …`, `fix(processing): …`, `docs: …`, `chore(deps): …`.
3. Abra um Pull Request focado em um único objetivo, com ao menos uma aprovação e a CI verde.

As regras completas estão no guia de padrões de engenharia do projeto.

## Checklist antes do PR

```bash
poetry install --with docs
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy src
poetry run pytest
poetry run mkdocs build --strict
```

Atalhos (taskipy) para o dia a dia:

| Comando | Executa |
|---|---|
| `poetry run task format` | `ruff format .` + `ruff check . --fix` |
| `poetry run task lint` | `ruff format --check .` + `ruff check .` + `mypy src` |
| `poetry run task test` | `pytest -m "not integration"` |
| `poetry run task docs` | `mkdocs serve` (requer `poetry install --with docs`) |

- [ ] Testes adicionados/atualizados
- [ ] Pipeline idempotente e com métricas de observabilidade
- [ ] Validações de qualidade de dados aplicadas
- [ ] Documentação atualizada (inclusive o [Dicionário de dados](datasets.md), se o schema mudou)
- [ ] Arquivos novos em UTF-8 sem BOM
- [ ] Nenhum secret ou dado sensível incluído

## Pipeline de CI (GitHub Actions)

Definida em `.github/workflows/ci.yml`. Dispara em push para `main` e `dev`, em todo Pull Request e manualmente (aba **Actions → CI → Run workflow**). Um push novo na mesma branch cancela a execução anterior.

| Job | Quando roda | O que faz |
|---|---|---|
| **Qualidade, testes e docs** | Sempre | `poetry check --lock` → `poetry install --with docs` → `ruff format --check` → `ruff check` → `mypy src` + `mypy src/f1/dashboard.py` → `pytest -m "not integration"` (mínimo de 50%) → metas por camada (não bloqueiam) → `mkdocs build --strict` |
| **Publicar documentação** | Push em `main`, depois do job anterior passar | `mkdocs gh-deploy` para a branch `gh-pages` |
| **Testes de integração** | Execução manual com a opção marcada | `pytest -m integration` contra a OpenF1 real (pulados se a API responder 401 por sessão ao vivo) |

O resumo de cobertura aparece na página de cada execução, e o `coverage.xml` fica disponível como artefato.

!!! tip "Proteção da `main`"
    O SKILL.md exige que o job **Qualidade, testes e docs** seja check obrigatório. Configure em **Settings → Branches → Add branch ruleset** (ou *Branch protection rules*) para `main`: exija Pull Request com 1 aprovação e o status check `Qualidade, testes e docs`.

## Versionamento

O projeto segue SemVer (`poetry version patch|minor|major`). Mudanças de schema silver consumidas por terceiros são **MAJOR**.
