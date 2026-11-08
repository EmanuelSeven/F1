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

## Versionamento

O projeto segue SemVer (`poetry version patch|minor|major`). Mudanças de schema silver consumidas por terceiros são **MAJOR**.
