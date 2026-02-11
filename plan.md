# Source Service Refactor Plan (Step-by-Step)

Follow these instructions exactly, one step at a time. Do not skip or combine steps.

## Goal
Move code out of `app/ui/sources/service.py` so that file becomes smaller than 800 lines. Keep existing behaviour.

## Current Files
- `app/ui/sources/service.py` (1,581 lines)
- `app/ui/sources/menu.py`
- `app/ui/sources/selection.py`
- `app/ui/handlers/sources.py`

Everything still works; we just need to split more code out of `service.py`.

## General Rules
1. Never delete a function without adding the same behaviour somewhere else.
2. After moving code, create a thin wrapper in `SourceService` that calls the new function.
3. After every major move, run `python -m compileall app/ui/sources` to check for syntax errors.
4. After every major move, run `wc -l app/ui/sources/service.py` and make sure the number goes down.

## Phase 1: Detail & Setup Module
1. Create a new file `app/ui/sources/detail.py` if it does not exist.
2. Copy these functions from `app/ui/sources/service.py` into `detail.py` (keep their bodies exactly the same):
   - `start_add_global_source`
   - `start_add_source`
   - `show_manage_sources`
   - `show_group_sources`
   - `show_source_details`
   - `start_set_source_name`
   - `process_source_name_input`
   - `show_monitor_bot_selection`
   - `show_forward_bot_selection`
   - `set_monitor_bot`
   - `set_forward_bot`
   - `clear_source_bots`
3. In `detail.py`, change each function signature to accept `service` instead of `self`. For example:
   ```python
   async def start_add_global_source(service, query: types.CallbackQuery, state: FSMContext):
   ```
4. Inside each function in `detail.py`, replace every `self.` with `service.`.
5. In `app/ui/sources/service.py`, replace each original function body with a one-line delegator. Example:
   ```python
   async def start_add_global_source(self, query: types.CallbackQuery, state: FSMContext):
       return await detail.start_add_global_source(self, query, state)
   ```
6. At the top of `service.py`, add `from app.ui.sources import detail`.
7. Run:
   ```bash
   python -m compileall app/ui/sources/detail.py
   python -m compileall app/ui/sources
   ```
   Fix any errors before continuing.
8. Run:
   ```bash
   wc -l app/ui/sources/service.py
   ```
   Confirm the number is smaller than before moving the code.

## Phase 2: Routing Module
1. Create `app/ui/sources/routing.py`.
2. Move these functions from `service.py` into `routing.py` (repeat steps 2–8 from Phase 1):
   - `show_add_route_menu`
   - `show_userbot_selection`
   - `show_bot_picker`
   - `handle_auto_assign`
   - `create_routing_rule`
   - `remove_routing_rule`
3. After moving, update `service.py` wrappers and imports (`from app.ui.sources import routing`).
4. Run compile and line-count checks again.

## Phase 3: User Module
1. Create `app/ui/sources/users.py`.
2. Move these functions (repeat the same process):
   - `start_add_user`
   - `_lookup_user_info`
   - `process_user_input`
   - `manage_source_users`
   - `remove_user_from_source`
3. Update wrappers/imports, run compile checks, run line count.

## Phase 4: Blockchain Module
1. Create `app/ui/sources/blockchain.py`.
2. Move these functions (same process):
   - `show_blockchain_selector`
   - `toggle_blockchain`
   - `confirm_blockchain_selection`
3. Update `service.py` to import `blockchain` and delegate in the wrappers.
4. Make sure `handle_sources_action` calls the new functions from the blockchain module where needed.
5. Run compile checks and line count.

## Final Validation
1. Run `python -m compileall app/ui/sources` one last time.
2. Run `wc -l app/ui/sources/service.py` and confirm it is under 800 lines.
3. Optionally smoke-test main flows (menu, routing, user management) if feasible.
