import json
import logging
from typing import List

from aiogram import types
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


async def show_blockchain_selector(service, query: types.CallbackQuery, rule_id: int, current_chains: List[str] = None, state: FSMContext = None):
    """Show blockchain selector for routing rule"""
    logger.info(f"[BLOCKCHAIN_DEBUG] show_blockchain_selector called: rule_id={rule_id}, current_chains={current_chains}")
    try:
        # Get routing rule if current_chains not provided
        if current_chains is None:
            logger.info(f"[BLOCKCHAIN_DEBUG] Fetching rule from DB for rule_id={rule_id}")
            rule = await service.db.fetchrow("SELECT * FROM routing_rules WHERE id = $1", rule_id)
            logger.info(f"[BLOCKCHAIN_DEBUG] DB returned rule: {dict(rule) if rule else None}")
            if not rule:
                logger.error(f"[BLOCKCHAIN_DEBUG] Rule {rule_id} not found in database")
                await query.answer("❌ Rule not found")
                return
            # Parse JSON if it's a string, otherwise use as-is
            allowed_chains_raw = rule.get('allowed_chains', ['SOL'])
            if isinstance(allowed_chains_raw, str):
                current_chains = json.loads(allowed_chains_raw)
            else:
                current_chains = allowed_chains_raw
            logger.info(f"[BLOCKCHAIN_DEBUG] Loaded current_chains from DB: {current_chains}")

        # Store in state for toggle handling
        if state:
            await state.update_data(blockchain_edit_rule_id=rule_id, blockchain_edit_chains=current_chains)
            logger.info(f"[BLOCKCHAIN_DEBUG] Updated FSM state with rule_id={rule_id}, chains={current_chains}")
        else:
            logger.warning(f"[BLOCKCHAIN_DEBUG] No FSM state provided, skipping state update")

        text = "<b>⛓️ Select Blockchains</b>\n\n"
        text += "Choose which blockchains this routing rule will forward:\n\n"
        text += "🟣 <b>Solana (SOL)</b> - Solana tokens\n"
        text += "🟡 <b>BNB Smart Chain</b> - BSC tokens\n\n"
        text += "⚠️ <b>At least one blockchain must be selected</b>"

        logger.info(f"[BLOCKCHAIN_DEBUG] Creating keyboard with chains={current_chains}, rule_id={rule_id}")
        keyboard = service.keyboards.blockchain_selector(current_chains, rule_id, context="routing")
        logger.info(f"[BLOCKCHAIN_DEBUG] Keyboard created, editing message")
        await query.message.edit_text(text, reply_markup=keyboard)
        logger.info(f"[BLOCKCHAIN_DEBUG] Message edited successfully")

    except Exception as e:
        logger.error(f"[BLOCKCHAIN_DEBUG] ❌ ERROR in show_blockchain_selector: {e}", exc_info=True)
        await query.answer(f"❌ Error: {str(e)}", show_alert=True)


async def toggle_blockchain(service, query: types.CallbackQuery, rule_id: int, chain: str, state: FSMContext = None):
    """Toggle blockchain selection"""
    logger.info(f"[BLOCKCHAIN_DEBUG] toggle_blockchain called: rule_id={rule_id}, chain={chain}")
    try:
        # Try to get current chains from FSM state first (preserves previous toggles)
        current_chains = None
        if state:
            data = await state.get_data()
            current_chains = data.get('blockchain_edit_chains')
            if current_chains:
                logger.info(f"[BLOCKCHAIN_DEBUG] Using chains from FSM state: {current_chains}")

        # Only fetch from DB if not in FSM state
        if current_chains is None:
            logger.info(f"[BLOCKCHAIN_DEBUG] No FSM state, fetching from DB for rule_id={rule_id}")
            rule = await service.db.fetchrow("SELECT allowed_chains FROM routing_rules WHERE id = $1", rule_id)
            logger.info(f"[BLOCKCHAIN_DEBUG] DB returned: {dict(rule) if rule else None}")
            if not rule:
                logger.error(f"[BLOCKCHAIN_DEBUG] Rule {rule_id} not found")
                await query.answer("❌ Rule not found", show_alert=True)
                return

            # Parse JSON if it's a string, otherwise use as-is
            allowed_chains_raw = rule['allowed_chains']
            if isinstance(allowed_chains_raw, str):
                current_chains = json.loads(allowed_chains_raw)
            else:
                current_chains = list(allowed_chains_raw)
            logger.info(f"[BLOCKCHAIN_DEBUG] Loaded from DB: {current_chains}")

        logger.info(f"[BLOCKCHAIN_DEBUG] Current chains before toggle: {current_chains}")

        # Toggle chain
        if chain in current_chains:
            current_chains.remove(chain)
            logger.info(f"[BLOCKCHAIN_DEBUG] Removed {chain} from chains: {current_chains}")
        else:
            current_chains.append(chain)
            logger.info(f"[BLOCKCHAIN_DEBUG] Added {chain} to chains: {current_chains}")

        # Update state with fresh data
        if state:
            await state.update_data(blockchain_edit_rule_id=rule_id, blockchain_edit_chains=current_chains)
            logger.info(f"[BLOCKCHAIN_DEBUG] Updated FSM state")
        else:
            logger.warning(f"[BLOCKCHAIN_DEBUG] No FSM state provided, skipping state update")

        # Refresh display
        logger.info(f"[BLOCKCHAIN_DEBUG] Refreshing blockchain selector display")
        await show_blockchain_selector(service, query, rule_id, current_chains, state=state)
        await query.answer()
        logger.info(f"[BLOCKCHAIN_DEBUG] Toggle completed successfully")

    except Exception as e:
        logger.error(f"[BLOCKCHAIN_DEBUG] ❌ ERROR in toggle_blockchain: {e}", exc_info=True)
        await query.answer(f"❌ Error: {str(e)}", show_alert=True)


async def confirm_blockchain_selection(service, query: types.CallbackQuery, rule_id: int, state: FSMContext = None):
    """Confirm and save blockchain selection"""
    logger.info(f"[BLOCKCHAIN_DEBUG] confirm_blockchain_selection called: rule_id={rule_id}")
    try:
        # Get selected chains from state
        return_to_filters = None
        if state:
            data = await state.get_data()
            selected_chains = data.get('blockchain_edit_chains', ['SOL'])
            return_to_filters = data.get('route_filters_return')
            logger.info(f"[BLOCKCHAIN_DEBUG] Selected chains from FSM state: {selected_chains}")
        else:
            logger.warning(f"[BLOCKCHAIN_DEBUG] No FSM state provided, fetching from DB")
            rule = await service.db.fetchrow("SELECT allowed_chains FROM routing_rules WHERE id = $1", rule_id)
            if rule:
                # Parse JSON if it's a string, otherwise use as-is
                allowed_chains_raw = rule['allowed_chains']
                if isinstance(allowed_chains_raw, str):
                    selected_chains = json.loads(allowed_chains_raw)
                else:
                    selected_chains = list(allowed_chains_raw)
            else:
                selected_chains = ['SOL']
            logger.info(f"[BLOCKCHAIN_DEBUG] Selected chains from DB: {selected_chains}")

        # Normalize chain values to uppercase identifiers
        selected_chains = [chain.upper() for chain in selected_chains]

        # Validate: at least one chain must be selected
        if not selected_chains:
            logger.warning(f"[BLOCKCHAIN_DEBUG] No chains selected, showing validation error")
            await query.answer("⚠️ Select at least one blockchain", show_alert=True)
            return

        # Update routing rule
        logger.info(f"[BLOCKCHAIN_DEBUG] Updating rule {rule_id} with chains: {selected_chains}")
        await service.source_model.update_routing_rule_chains(rule_id, selected_chains)
        logger.info(f"[BLOCKCHAIN_DEBUG] Rule updated successfully")

        # Get source_id for redirect
        rule = await service.db.fetchrow("SELECT source_chat_id FROM routing_rules WHERE id = $1", rule_id)
        logger.info(f"[BLOCKCHAIN_DEBUG] Fetched source_chat_id: {rule['source_chat_id'] if rule else None}")
        if rule:
            await query.answer("✅ Blockchain filter updated!")
            if return_to_filters == rule_id and state:
                logger.info(f"[BLOCKCHAIN_DEBUG] Returning to route filters for rule {rule_id}")
                await state.update_data(route_filters_return=None)
                await service.show_route_filters(query, rule_id, state)
            else:
                logger.info(f"[BLOCKCHAIN_DEBUG] Redirecting to source details for source_id={rule['source_chat_id']}")
                await service.show_source_details(query, rule['source_chat_id'])
        else:
            logger.error(f"[BLOCKCHAIN_DEBUG] Rule {rule_id} not found after update")
            await query.answer("❌ Rule not found")

    except Exception as e:
        logger.error(f"[BLOCKCHAIN_DEBUG] ❌ ERROR in confirm_blockchain_selection: {e}", exc_info=True)
        await query.answer(f"❌ Error: {str(e)}", show_alert=True)
