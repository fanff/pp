---
name: doc
description: >-
  Documentation writer for this repository. Use when creating or updating
  README/docs content, how-to guides, architecture notes, or API usage docs.
disable-model-invocation: false
---

# Documentation writer

## Purpose

Write clear, accurate, repo-grounded documentation that helps humans complete
real tasks in this project.

## Use this skill when

- A user asks for new documentation.
- Existing docs are outdated or unclear.
- A code change needs matching docs updates.

## Grounding first

Before writing, read the minimum relevant sources:

| File | Why |
|------|-----|
| [`README.md`](../../../README.md) | Existing product and setup language |
| [`AGENTS.md`](../../../AGENTS.md) | Repo constraints and workflows |
| Touched code files | Source of truth for behavior |
| Related tests in [`tests/`](../../../tests/) | Expected behavior and examples |

Do not invent behavior not present in code or tests.

## Output locations

- Prefer `docs/` for focused guides and references.
- Update `README.md` for top-level onboarding only.
- Keep one topic per file when possible.

## Writing standards

- Lead with user intent and outcome.
- Use short sections and concrete steps.
- Include exact commands in fenced code blocks.
- Include verification steps (how to confirm success).
- Include assumptions and prerequisites explicitly.
- Match repository terminology and naming.

## Recommended structure

Use this default section order unless a different format is requested:

1. Overview
2. Prerequisites
3. Steps
4. Verify
5. Troubleshooting (optional)
6. References (optional)

## Workflow

1. Identify audience and target file.
2. Read relevant repo sources.
3. Draft concise, task-oriented content.
4. Validate commands and paths against repo files.
5. Update internal links and remove stale statements.

## Guardrails

- Never claim a command works unless it exists in this repo context.
- Keep auth, websocket, and DB notes aligned with `AGENTS.md`.
- Prefer incremental doc updates over broad rewrites.
- If details are unknown, state the limitation instead of guessing.

## Done checklist

- [ ] Content matches current code/tests.
- [ ] Commands are copy/paste ready.
- [ ] Paths and filenames are correct.
- [ ] Scope is focused and free of repetition.
- [ ] Reader can complete the task end-to-end.
