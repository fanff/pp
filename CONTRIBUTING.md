# Contributing

Thanks for contributing to PP.

## Development setup

```bash
uv sync
uv run pytest
```

Run backend locally:

```bash
uvicorn ppback.main:app --reload
```

## Branching policy

- Do not commit directly to `master`/`main`.
- Create a dedicated branch for each task or change.
- Keep branches focused and short-lived.

Suggested branch names:

- `feat/<short-topic>`
- `fix/<short-topic>`
- `chore/<short-topic>`
- `docs/<short-topic>`

## Commit message convention

Use Conventional Commits:

```text
<type>(optional-scope): <short summary>
```

Common types:

- `feat`: new user-facing feature
- `fix`: bug fix
- `chore`: maintenance/refactor/tooling
- `docs`: documentation-only changes
- `test`: tests added or updated
- `perf`: performance improvement

Examples:

- `feat(cache): add typed cache wrapper for hook_user`
- `fix(ws): handle missing token payload in handshake`
- `chore(compose): remove legacy frontend services`
- `docs(readme): update backend-only local run steps`

## Pull request checklist

- Keep behavior changes small and explicit.
- Update tests for changed behavior.
- Run `uv run pytest` locally before opening PR.
- Update docs when contracts, commands, or workflows change.
