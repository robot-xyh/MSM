# Repository Guidelines

## Project Structure & Module Organization

This repository is currently empty aside from this contributor guide. As code is added, keep the top-level layout predictable:

- `src/` for application or library source code.
- `tests/` for automated tests that mirror `src/` structure.
- `assets/` for static files such as images, fixtures, sample data, or generated media.
- `docs/` for longer design notes, usage guides, or architecture records.

Avoid placing implementation files directly in the repository root unless they are standard project entry points such as `Makefile`, `package.json`, `pyproject.toml`, or `README.md`.

## Build, Test, and Development Commands

No build or test tooling is present yet. When tooling is introduced, document the canonical commands here and prefer commands that work from the repository root. Examples:

- `npm test` or `pytest` to run the full test suite.
- `npm run lint` or `ruff check .` to run static checks.
- `make build` to produce production artifacts.
- `make dev` or `npm run dev` to start a local development server.

If a command requires environment variables or generated files, document those prerequisites next to the command.

## Coding Style & Naming Conventions

Follow the formatter and linter configured for the language in use. If no formatter exists yet, add one before the codebase grows. Use descriptive file and symbol names, keep modules focused, and prefer lower-case directory names such as `src/api/` or `tests/unit/`.

Do not mix unrelated formatting changes with functional edits. Keep generated files out of source directories unless the project explicitly requires them.

## Testing Guidelines

Add tests with each meaningful behavior change. Mirror source paths where practical, for example `src/parser/reader.py` with `tests/parser/test_reader.py`. Use clear test names that describe behavior and expected outcomes.

When adding test tooling, include one command that runs the complete suite locally and in CI.

## Commit & Pull Request Guidelines

This directory is not currently a Git repository, so no existing commit convention is available. Once Git history exists, prefer short imperative commit subjects such as `Add parser validation` or `Fix asset loading`.

Pull requests should include a concise summary, test results, linked issues when applicable, and screenshots or recordings for visible UI changes.

## Agent-Specific Instructions

Before editing, inspect the current tree and preserve user-created files. Do not overwrite `AGENTS.md` without an explicit request.
