# Contributing to LightWorker

LightWorker is available under the MIT License. Contributions are welcome.

## Prerequisites

- Python 3.11 or newer
- Git
- `pytest`

## Development setup

```bash
git clone https://github.com/ncepuee/LightWorker.git
cd LightWorker
python -m venv .venv
```

Activate the environment using `.venv\Scripts\Activate.ps1` on Windows PowerShell or `source .venv/bin/activate` on macOS/Linux, then run:

```bash
python -m pip install --upgrade pip
python -m pip install -e . pytest
python -m pytest
```

Tests must be self-contained and must not use real credentials, remote models or network services. Use temporary directories for SQLite databases and Git repositories.

## Guidelines

- Keep Python compatible with 3.11+ and preserve the zero-runtime-dependency design.
- Add regression tests for behavioral changes.
- Never commit local state, credentials, `.env`, `config.toml`, databases, logs or absolute user paths.
- Keep user-visible changes in `CHANGELOG.md`.
- Do not weaken the loopback, sandbox, approval or worktree safety boundaries.

## Release checklist

1. Keep `pyproject.toml`, `lightworker.__version__`, HTTP and MCP version strings aligned.
2. Update `CHANGELOG.md`.
3. Run the full test and package verification workflows.
4. Tag the verified commit as `vX.Y.Z` and attach the wheel and sdist to the GitHub Release.
