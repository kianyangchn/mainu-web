# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `app/`: `app/main.py` wires the FastAPI stack, `app/routes/` holds HTTP handlers, `app/services/llm.py` brokers multimodal LLM calls, and `app/templates/` contains Jinja mobile-first views. Product context is captured in `PRD-web.txt`, while `pyproject.toml` defines dependencies. Tests mirror the package layout inside `tests/`. Keep deployment collateral (Railway configs, Dockerfile) at repo root and document new directories in this section as the project grows.

## Build, Test, and Development Commands
Install dependencies with `uv sync` (uv respects the `pyproject.toml` lock and creates an isolated environment automatically). Serve the app locally using `uv run uvicorn app.main:app --reload`. Execute the test suite via `uv run pytest` and check coverage with `uv run coverage run -m pytest` followed by `uv run coverage report`.

## Coding Style & Naming Conventions
Follow `black` formatting (88-char lines) and run `ruff check --fix` before committing. Use type hints throughout; prefer `pydantic` models for request/response schemas. Modules and packages should use snake_case (`app/menu_parser.py`), classes in PascalCase, constants in SCREAMING_SNAKE_CASE, and async endpoints prefixed with the verb they serve (`get_menu`, `post_share_link`). When shipping HTML/CSS, keep layout mobile-first and touch-friendly per the PRD.

## Testing Guidelines
Adopt `pytest` with tests colocated under `tests/` mirroring the package structure (`tests/routes/test_share.py`). Name test functions `test_<behavior_under_test>`. Maintain ≥85% line coverage and include regression tests whenever fixing production bugs. Integration tests that hit the multimodal LLM should be marked with `@pytest.mark.external` so they can be gated in CI.

## Commit & Pull Request Guidelines
Create a dedicated branch for each feature or fix (`git checkout -b feat/mobile-capture`). Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, `chore:`) to aid changelog automation. Each PR should link to the relevant PRD section or issue, describe the user-facing impact, list verification steps (commands run, screenshots for UI changes), and note any new environment variables. Request review once CI (formatting, lint, tests) is green.

## Product Alignment
Reference `PRD-web.txt` before large changes. It defines the mobile-first UX strategy, single-Python-app architecture, Railway deployment model, and reliance on a multimodal LLM instead of bespoke OCR. Call out PRD impacts in design docs and PR descriptions when altering flows or infrastructure.

If requirements feel unclear, ask the user before proceeding.

## Environment & Deployment Notes
Railway is the primary deployment target. Store secrets via Railway variables, keep state in PostgreSQL/Redis add-ons, and document any cron/worker services alongside the code that depends on them. For LLM access, centralize API keys in a dedicated settings module (`app/config.py`) and avoid hard-coding endpoints inside business logic.
