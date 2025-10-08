# Repository Guidelines

## Project Structure & Module Organization
The Python control plane lives in `app/`, with `ui/` for bot menus, `userbot/` for Telethon workers, `services/` for cross-cutting logic, and `models/` wrapping asyncpg access. SQL migrations sit in `migrations/` and run at startup. The Rust Solana agent occupies `telegram_token_bot/` alongside its `Cargo.toml`. Reusable seeding scripts land in `scripts/`, message templates in `templates/`, and `main.py` remains as the legacy single-user bot.

## Build, Test, and Development Commands
```
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app/runner.py               # management bot
cargo run --release                # Rust token bot
pytest tests/test_auto_click.py    # async DB smoke
python tests/test_batch.py         # DexScreener sanity
```
Activate the venv before running management scripts. The Rust bot reads the same `.env` via `dotenv`; use `cargo build --release` in CI to catch compile errors.

## Coding Style & Naming Conventions
Python code follows PEP 8 with 4-space indents, descriptive async names, and type hints where data crosses services (see `app/db.py:11`). Keep constants in UPPER_SNAKE_CASE and prefer Pydantic models for config. For Rust, rely on idiomatic Tokio patterns and run `cargo fmt` and `cargo clippy --all-targets` before review. Docstrings should capture intent while loggers stay scoped (`logging.getLogger(__name__)`).

## Testing Guidelines
Tests expect an accessible Postgres at `SUPABASE_POOLER_URL`; point to a disposable schema and let `db.run_migrations()` seed it. `test_auto_click.py` mocks Telethon but writes to the DB, so reset fixtures afterward. The DexScreener probe in `tests/test_batch.py` issues live HTTP calls—toggle with `DEX_TEST=1` or patch `aiohttp` when offline. Add unit tests beside new modules and name them `test_<module>.py`.

## Commit & Pull Request Guidelines
Commits in this repo favor short, lower-case subjects (`git log -5`); start with an imperative verb under ~60 chars, e.g., `add bnb auto-click filter`. Expand in the body when migrations, scripts, or configuration changes are involved. Pull requests should explain operator impact, link issues, and include UI screenshots whenever menu flows change. Flag follow-up tasks (migrations, seeded templates) in the checklist so deployers know what to run.

## Security & Configuration Tips
Use `.env.example` as the contract for configuration and keep real tokens out of version control. Rotate Supabase credentials shared for testing and prefer scoped service roles. The local `userbot.db` aids experiments only; avoid committing it unless fixture updates are intentional. Validate any new env keys through `app/config.py` so misconfigurations fail fast.
