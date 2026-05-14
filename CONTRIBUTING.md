# Contributing

## Development setup

```bash
uv sync
pytest
```

## Running locally

```bash
uvicorn ppback.main:app --reload
```

## Quick-startup validation

Verify imports and boot without a long-running server:

```bash
timeout 5 uvicorn ppback.main:app --lifespan=on 2>&1 || true
```

## Branching policy

- Do not commit to `master`/`main` directly.
- Create a dedicated branch per task: `feat/`, `fix/`, `chore/`, `docs/`.

## Commit message convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `perf`.

Examples:

```
feat(cache): add typed cache wrapper for hook_user
fix(ws): handle missing token payload in handshake
chore(compose): remove legacy frontend services
docs(readme): update backend-only local run steps
```

## Pull request checklist

- Keep changes small and explicit.
- Update tests for changed behaviour.
- Run `pytest` locally before opening PR.
- Update docs when contracts, commands, or workflows change.
