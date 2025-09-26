# Helius Placeholder Catalogue (Phase 5)

Rust now returns `holders` (Helius `getTokenLargestAccounts`) and `supply_ui_amount` (`getTokenSupply`). The Python placeholder service exposes the following keys:

## Snapshot
- `helius_data_slot`
- `helius_holder_count`
- `helius_holder_total_ui_amount`
- `helius_remaining_share`

## Top Holder Aggregates
- `helius_top1_ui_amount`, `helius_top1_share`
- `helius_top5_ui_amount`, `helius_top5_share`
- `helius_top10_ui_amount`, `helius_top10_share`
- `helius_top20_ui_amount`, `helius_top20_share`

## Per-Holder (1–20)
For each `n` from 1 to 20:
- `helius_holder_{n}_address`
- `helius_holder_{n}_short`
- `helius_holder_{n}_ui_amount`
- `helius_holder_{n}_ui_amount_string`
- `helius_holder_{n}_raw_amount`
- `helius_holder_{n}_decimals`
- `helius_holder_{n}_percent_of_sample`
- `helius_holder_{n}_percent_of_supply`
- `helius_holder_{n}_user`
- `helius_holder_{n}_balance_short`
- `helius_holder_{n}_percent_short`
- `helius_breakdown_{n}`

## Creator Holdings
- `helius_creator_is_holder`
- `helius_creator_holding_ui_amount`
- `helius_creator_holding_ui_amount_string`
- `helius_creator_holding_raw_amount`
- `helius_creator_holding_percent_of_sample`
- `helius_creator_holding_percent_of_supply`

Percent of supply values are only populated when `getTokenSupply` returns a UI amount. Creator fields are marked "No" if the creator address is not present in the top 20 set.

## Formatted Display Helpers
- `helius_holder_{n}_user`: compact rank + wallet tail (e.g. `1..UoTa`, `10.4JSb`).
- `helius_holder_{n}_balance_short`: compact human-readable holdings (e.g. `347.3M`).
- `helius_holder_{n}_percent_short`: percent of supply with two decimals (e.g. `34.73%`).
- `helius_breakdown_{n}`: percent of supply with one decimal for inline breakdown strings (e.g. `11.2`).
