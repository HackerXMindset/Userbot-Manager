# Repository Guidelines

## Project Structure & Module Organization
- `src/main.rs` boots the Rust bot, loads dotenv config, and wires tracing. Keep startup logic here.
- `src/bot.rs` handles Telegram updates, message splitting, and response formatting; extend handlers or keyboards in this module.
- `src/api.rs` wraps external API calls with caching and error handling; prefer enriching this layer rather than calling `reqwest` directly.
- `src/types.rs` owns shared data models and serde derives; update types first, then adjust consumers.
- Legacy Python helpers (`telegram_bot.py`, `s.py`) are available for rapid prototyping; port validated improvements into the Rust entry points.
- Environment templates live in `.env.example`; never commit a real `.env`.

## Build, Test, and Development Commands
- `cargo check` performs a fast compilation sanity pass; run before pushing.
- `cargo run` starts the bot in debug mode; add `RUST_LOG=debug` when tracing issues.
- `cargo run --release` uses the optimized target that Production consumes.
- `cargo fmt` and `cargo fmt --check` enforce canonical formatting.
- `cargo clippy --all-targets -- -D warnings` keeps lint debt out of the main branch.
- `cargo test` executes unit and integration tests; combine with `-- --include-ignored` when adding slow suites.

## Coding Style & Naming Conventions
- Stick to Rust 2021 defaults: 4-space indentation, trailing commas for multi-line literals, and module-level `snake_case`.
- Types and traits use `PascalCase`; functions, modules, and variables use `snake_case`; constants stay in `SCREAMING_SNAKE_CASE`.
- When adding APIs, expose new functionality via focused helper functions instead of sprawling `async` blocks.
- Format commits via `cargo fmt` before staging changes; unexpected diffs should be addressed, not ignored.

## Testing Guidelines
- Co-locate unit tests inside the relevant module under `#[cfg(test)] mod tests`, naming functions like `test_fetch_token_metadata_returns_cache_hit`.
- Place cross-module scenarios under `tests/` to exercise the full Telegram pipeline.
- Ensure network-dependent tests mock HTTP responses; avoid hitting real endpoints in CI.
- Aim to cover new branches and error paths; document skipped cases in the PR description.

## Commit & Pull Request Guidelines
- Follow the existing imperative, Title-Case prefix style (`Feat:`, `Fix:`, `Enhance:`) with concise subjects under 72 characters.
- Reference related issues in the PR body, summarize the user impact, and call out configuration changes.
- Include screenshots or sample bot output when formatting or user-facing behavior changes.
- Confirm the checklist: `cargo fmt`, `cargo clippy`, `cargo test`, and any manual validations.

## Security & Configuration Tips
- Load secrets via `.env`; never print tokens in logs—prefer redacted tracing fields.
- Validate user-supplied addresses with the regex utilities in `src/api.rs` before hitting external APIs.
- Review rate limits before merging changes that increase request volume, and document any new environment variables in `.env.example`.
