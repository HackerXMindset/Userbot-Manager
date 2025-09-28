from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel, TargetModel

logger = logging.getLogger(__name__)

class TargetsHandler:
    """Handler for target management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
        self.target_model = TargetModel(db)
    
    async def handle_target_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle target actions"""
        parts = query.data.split(':')  # Allow more parts for group_id context
        action = parts[1]
        
        if action == 'add':
            await self.start_add_target(query, state)
        elif action == 'select_group':
            group_id = int(parts[2])
            await self.prompt_for_target_chat_id(query, state, group_id)
        elif action == 'delete':
            if len(parts) > 2:
                target_id = int(parts[2])
                await self.delete_target(query, target_id)
            else:
                await self.show_delete_target_list(query)
        elif action == 'select_for_alerts':
            await self.show_targets_for_alerts(query)
        elif action == 'alerts_menu':
            target_id = int(parts[2])
            group_id = int(parts[3]) if len(parts) > 3 else None
            await self.show_alerts_menu(query, target_id, group_id)
        elif action == 'alerts_toggle':
            parts = query.data.split(':', 3)
            target_id = int(parts[2])
            mode = parts[3]
            await self.toggle_alert_mode(query, target_id, mode)
        elif action == 'alerts_enable':
            target_id = int(parts[2])
            await self.toggle_alerts_enabled(query, target_id)
        elif action == 'alerts_modes':
            target_id = int(parts[2])
            await self.show_alert_modes(query, target_id)
        elif action == 'alerts_set_sensitivity':
            target_id = int(parts[2])
            await self.prompt_for_sensitivity(query, state, target_id)
        elif action == 'alerts_set_thresholds':
            target_id = int(parts[2])
            await self.prompt_for_thresholds(query, state, target_id)
        else:
            await self.show_targets_menu(query)
    
    async def show_targets_menu(self, query: types.CallbackQuery):
        """Show targets overview"""
        try:
            # Get all targets with group information
            targets = await self.db.fetch("""
                SELECT t.*, g.display_name as group_display_name, g.title as group_title, g.tg_chat_id as group_tg_chat_id
                FROM targets t
                LEFT JOIN groups g ON g.id = t.group_id
                ORDER BY g.display_name, t.dest_chat_id
            """)
            
            text = "<b>🎯 Targets Overview</b>\n\n"
            
            if not targets:
                text += "No targets configured.\nTargets are the channels where calls are sent."
            else:
                text += f"<b>Available Targets ({len(targets)}):</b>\n\n"
                for i, target in enumerate(targets, 1):
                    group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"

                    # Get alert summary
                    alert_summary = await self.target_model.get_alert_summary(target['id'])
                    alert_text = alert_summary.get('summary_text', 'Alerts: Unknown')

                    text += f"{i}. <code>{target['dest_chat_id']}</code>\n"
                    text += f"   └ Group: {group_name}\n"
                    text += f"   └ {alert_text}\n\n"
            
            keyboard_rows = []
            if targets:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➕ Add Target", callback_data="targets:add"),
                    InlineKeyboardButton(text="🗑️ Delete Target", callback_data="targets:delete")
                ])
                # Add alerts config button for individual targets
                if len(targets) > 0:
                    keyboard_rows.append([
                        InlineKeyboardButton(text="⚙️ Configure Alerts", callback_data="targets:select_for_alerts")
                    ])
            else:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➕ Add Target", callback_data="targets:add")
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            try:
                await query.message.edit_text(text, reply_markup=keyboard)
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    # Message content is identical, just answer the callback
                    await query.answer()
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"Error showing targets menu: {e}")
            await query.answer("❌ Error loading targets")

    async def start_add_target(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding a target - first select which group"""
        try:
            # Get available groups
            groups = await self.db.fetch("SELECT * FROM groups WHERE enabled = true ORDER BY title")
            
            if not groups:
                await query.answer("❌ No groups available. Create a group first.")
                return
            
            text = (
                "<b>➕ Add Target</b>\n\n"
                "First, select which group this target belongs to:"
            )
            
            keyboard_rows = []
            for group in groups:
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"👥 {group_name}",
                        callback_data=f"targets:select_group:{group['id']}"
                    )
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="targets:menu")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error starting add target: {e}")
            await query.answer("❌ Error starting target setup")
    
    async def prompt_for_target_chat_id(self, query: types.CallbackQuery, state: FSMContext, group_id: int):
        """Prompt for target chat ID after group selection"""
        try:
            # Get group details
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = (
                f"<b>➕ Add Target for {group_name}</b>\n\n"
                "Now enter the target chat ID where calls should be sent.\n\n"
                "<b>Examples:</b>\n"
                "• Channel: -1001234567890\n"
                "• Group: -1001234567890\n"
                "• Your private chat ID\n\n"
                "Type /cancel to abort."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="targets:add")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.adding_target.state)
            await state.update_data(message_id=query.message.message_id, group_id=group_id)
            
        except Exception as e:
            logger.error(f"Error prompting for target chat ID: {e}")
            await query.answer("❌ Error setting up target input")
    
    async def show_delete_target_list(self, query: types.CallbackQuery):
        """Show list of targets for deletion"""
        try:
            # Get all targets with group information
            targets = await self.db.fetch("""
                SELECT t.*, g.display_name as group_display_name, g.title as group_title, g.tg_chat_id as group_tg_chat_id
                FROM targets t
                LEFT JOIN groups g ON g.id = t.group_id
                ORDER BY g.display_name, t.dest_chat_id
            """)
            
            if not targets:
                await query.answer("❌ No targets to delete")
                return
            
            text = "<b>🗑️ Delete Target</b>\n\n"
            text += "Select a target to delete:"
            
            keyboard_rows = []
            for target in targets:
                group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                button_text = f"🗑️ {target['dest_chat_id']} ({group_name})"
                if len(button_text) > 35:
                    button_text = button_text[:32] + "..."
                
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"targets:delete:{target['id']}"
                    )
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="targets:menu")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete target list: {e}")
            await query.answer("❌ Error loading targets for deletion")
    
    async def delete_target(self, query: types.CallbackQuery, target_id: int):
        """Delete a specific target"""
        try:
            # Get target info before deletion
            target = await self.db.fetchrow(
                "SELECT * FROM targets WHERE id = $1", target_id
            )
            
            if not target:
                await query.answer("❌ Target not found")
                return
            
            # Delete the target
            result = await self.db.execute(
                "DELETE FROM targets WHERE id = $1", target_id
            )
            
            text = f"✅ <b>Target Deleted</b>\n\n"
            text += f"Target Chat ID: <code>{target['dest_chat_id']}</code>\n\n"
            text += "This target has been removed from the system."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 View Targets", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Target deleted successfully")
            
        except Exception as e:
            logger.error(f"Error deleting target: {e}")
            await query.answer("❌ Error deleting target")

    async def process_target_input(self, message: types.Message, state: FSMContext):
        """Process target addition input"""
        if message.text == '/cancel':
            await state.clear()
            await message.answer(
                "Target addition cancelled.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )
            return
        
        try:
            # Get state data
            data = await state.get_data()
            group_id = data.get('group_id')
            
            if not group_id:
                await message.answer("❌ Error: No group selected. Please try again.")
                await state.clear()
                return
            
            # Parse input - should be a chat ID
            text = message.text.strip()
            
            # Try to convert to integer (chat ID)
            try:
                chat_id = int(text)
            except ValueError:
                await message.answer(
                    "❌ Invalid input. Please enter a valid chat ID (numbers only).\n\n"
                    "Example: -1001234567890"
                )
                return
            
            # Check if target already exists for this group
            existing = await self.db.fetchval(
                "SELECT id FROM targets WHERE group_id = $1 AND dest_chat_id = $2", 
                group_id, chat_id
            )
            
            if existing:
                await message.answer(
                    f"❌ Target <code>{chat_id}</code> already exists for this group!"
                )
                return
            
            # Get group info for confirmation
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Add target to database with proper group association
            result = await self.db.fetchrow(
                "INSERT INTO targets (group_id, dest_chat_id, created_at) VALUES ($1, $2, NOW()) RETURNING *",
                group_id, chat_id
            )
            
            await message.answer(
                f"✅ <b>Target Added Successfully!</b>\n\n"
                f"Group: <b>{group_name}</b>\n"
                f"Target ID: {result['id']}\n"
                f"Chat ID: <code>{result['dest_chat_id']}</code>\n\n"
                f"This group can now forward calls to this target.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 View Targets", callback_data="menu:targets")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Error adding target: {e}")
            await message.answer(f"❌ Error adding target: {e}")
        
        finally:
            await state.clear()

    # Alert Configuration Methods

    async def show_targets_for_alerts(self, query: types.CallbackQuery):
        """Show list of targets to select for alert configuration"""
        try:
            targets = await self.target_model.get_targets_with_group_info()

            text = "<b>⚙️ Configure Target Alerts</b>\n\n"
            text += "Select a target to configure alerts:"

            keyboard_rows = []
            for target in targets:
                group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                button_text = f"🎯 {target['dest_chat_id']} ({group_name})"
                if len(button_text) > 35:
                    button_text = button_text[:32] + "..."

                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"targets:alerts_menu:{target['id']}"
                    )
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="targets:menu")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing targets for alerts: {e}")
            await query.answer("❌ Error loading targets")

    async def show_alerts_menu(self, query: types.CallbackQuery, target_id: int, group_id: int = None):
        """Show alerts configuration menu for specific target"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            alert_summary = await self.target_model.get_alert_summary(target_id)
            modes = alert_summary.get('modes', {})
            thresholds = alert_summary.get('thresholds', [])
            sensitivity = alert_summary.get('sensitivity_percent', 0.50)
            enabled = alert_summary.get('enabled', True)

            text = f"<b>⚙️ Alert Configuration</b>\n\n"
            text += f"<b>Target:</b> <code>{target['dest_chat_id']}</code>\n"
            text += f"<b>Status:</b> {'🟢 ON' if enabled else '🔴 OFF'}\n\n"

            if enabled:
                text += f"<b>Alert Modes:</b>\n"
                for mode, is_enabled in modes.items():
                    icon = "✅" if is_enabled else "❌"
                    text += f"  {icon} {mode.title()}\n"

                text += f"\n<b>Sensitivity:</b> {sensitivity*100:.0f}%\n"
                text += f"<b>Thresholds:</b> {', '.join([str(x) for x in thresholds])}\n"

            # Determine the correct back callback
            back_callback = f"group:alerts:{group_id}" if group_id else "targets:select_for_alerts"

            keyboard = self.keyboards.target_alerts_menu(target, back_callback=back_callback)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing alerts menu: {e}")
            await query.answer("❌ Error loading alert configuration")

    async def show_alert_modes(self, query: types.CallbackQuery, target_id: int):
        """Show alert modes configuration"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            modes = self.target_model.parse_alert_modes(target)

            text = f"<b>🎛️ Alert Modes Configuration</b>\n\n"
            text += f"<b>Target:</b> <code>{target['dest_chat_id']}</code>\n\n"
            text += f"Toggle alert modes on/off:\n\n"

            for mode, enabled in modes.items():
                status = "✅ ON" if enabled else "❌ OFF"
                text += f"<b>{mode.title()}:</b> {status}\n"

            keyboard = self.keyboards.target_alerts_mode_keyboard(target)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing alert modes: {e}")
            await query.answer("❌ Error loading alert modes")

    async def toggle_alerts_enabled(self, query: types.CallbackQuery, target_id: int):
        """Toggle alerts enabled/disabled for target"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            new_enabled = not target['alerts_enabled']
            await self.target_model.update_alerts_enabled(target_id, new_enabled)

            status = "enabled" if new_enabled else "disabled"
            await query.answer(f"✅ Alerts {status}")
            await self.show_alerts_menu(query, target_id)

        except Exception as e:
            logger.error(f"Error toggling alerts: {e}")
            await query.answer("❌ Error updating alerts")

    async def toggle_alert_mode(self, query: types.CallbackQuery, target_id: int, mode: str):
        """Toggle specific alert mode for target"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            modes = self.target_model.parse_alert_modes(target)
            if mode in modes:
                modes[mode] = not modes[mode]
                await self.target_model.update_alert_modes(target_id, modes)

                status = "enabled" if modes[mode] else "disabled"
                await query.answer(f"✅ {mode.title()} alerts {status}")
                await self.show_alert_modes(query, target_id)
            else:
                await query.answer("❌ Invalid alert mode")

        except Exception as e:
            logger.error(f"Error toggling alert mode: {e}")
            await query.answer("❌ Error updating alert mode")

    async def prompt_for_sensitivity(self, query: types.CallbackQuery, state: FSMContext, target_id: int):
        """Prompt for sensitivity percentage input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.get_alert_sensitivity_percent(target)

            text = (
                f"<b>⚡ Set Sensitivity Percentage</b>\n\n"
                f"<b>Target:</b> <code>{target['dest_chat_id']}</code>\n"
                f"<b>Current:</b> {current*100:.0f}%\n\n"
                f"Enter new sensitivity percentage (5-500%):\n"
                f"Example: 50 (for 50%)\n\n"
                f"<i>Sensitivity controls how often alerts fire.\n"
                f"50% = alerts at 1.5x, 2.25x, 3.375x, etc.</i>\n\n"
                f"Type /cancel to abort."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_menu:{target_id}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.target_edit_sensitivity.state)
            await state.update_data(target_id=target_id, message_id=query.message.message_id)

        except Exception as e:
            logger.error(f"Error prompting for sensitivity: {e}")
            await query.answer("❌ Error setting up sensitivity input")

    async def prompt_for_thresholds(self, query: types.CallbackQuery, state: FSMContext, target_id: int):
        """Prompt for thresholds input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.parse_alert_thresholds(target)

            text = (
                f"<b>📊 Set Alert Thresholds</b>\n\n"
                f"<b>Target:</b> <code>{target['dest_chat_id']}</code>\n"
                f"<b>Current:</b> {', '.join([str(x) for x in current])}\n\n"
                f"Enter new thresholds as comma-separated numbers:\n"
                f"Example: 2,5,10,25\n\n"
                f"<i>Thresholds are multipliers from initial market cap.\n"
                f"2 = 2x gains, 5 = 5x gains, etc.</i>\n\n"
                f"Type /cancel to abort."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_menu:{target_id}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.target_edit_thresholds.state)
            await state.update_data(target_id=target_id, message_id=query.message.message_id)

        except Exception as e:
            logger.error(f"Error prompting for thresholds: {e}")
            await query.answer("❌ Error setting up thresholds input")

    async def process_sensitivity_input(self, message: types.Message, state: FSMContext):
        """Process sensitivity percentage input"""
        if message.text == '/cancel':
            await state.clear()
            await message.answer(
                "Sensitivity configuration cancelled.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )
            return

        try:
            data = await state.get_data()
            target_id = data.get('target_id')

            if not target_id:
                await message.answer("❌ Error: No target selected. Please try again.")
                await state.clear()
                return

            # Parse and validate sensitivity input
            text = message.text.strip()
            try:
                sensitivity_percent = float(text)

                # Clamp to valid range (5% to 500%)
                if sensitivity_percent < 5 or sensitivity_percent > 500:
                    await message.answer(
                        "❌ Sensitivity must be between 5% and 500%.\n"
                        "Example: 50 (for 50% sensitivity)"
                    )
                    return

                # Convert to decimal (50 -> 0.50)
                sensitivity_decimal = sensitivity_percent / 100.0

            except ValueError:
                await message.answer(
                    "❌ Invalid input. Please enter a number between 5 and 500.\n"
                    "Example: 50 (for 50% sensitivity)"
                )
                return

            # Update target sensitivity
            await self.target_model.update_alert_sensitivity(target_id, sensitivity_decimal)

            await message.answer(
                f"✅ <b>Sensitivity Updated!</b>\n\n"
                f"New sensitivity: {sensitivity_percent:.0f}%\n"
                f"This means alerts will fire when tokens reach:\n"
                f"1x → {1.0 * (1 + sensitivity_decimal):.2f}x → {1.0 * (1 + sensitivity_decimal)**2:.2f}x → etc.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⚙️ Alert Config", callback_data=f"targets:alerts_menu:{target_id}")],
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )

        except Exception as e:
            logger.error(f"Error processing sensitivity input: {e}")
            await message.answer(f"❌ Error updating sensitivity: {e}")

        finally:
            await state.clear()

    async def process_thresholds_input(self, message: types.Message, state: FSMContext):
        """Process thresholds input with validation"""
        if message.text == '/cancel':
            await state.clear()
            await message.answer(
                "Thresholds configuration cancelled.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )
            return

        try:
            data = await state.get_data()
            target_id = data.get('target_id')

            if not target_id:
                await message.answer("❌ Error: No target selected. Please try again.")
                await state.clear()
                return

            # Parse and validate thresholds input
            text = message.text.strip()

            # Validate and parse thresholds
            thresholds = self._validate_thresholds_input(text)
            if thresholds is None:
                await message.answer(
                    "❌ Provide numbers like 2,3.5,5\n\n"
                    "Examples:\n"
                    "• 2,5,10,25\n"
                    "• 1.5,3,7.5\n"
                    "• 2"
                )
                return

            # Update target thresholds
            await self.target_model.update_alert_thresholds(target_id, thresholds)

            threshold_text = ', '.join([str(x) for x in sorted(thresholds)])
            await message.answer(
                f"✅ <b>Thresholds Updated!</b>\n\n"
                f"New thresholds: {threshold_text}\n"
                f"Alerts will fire when tokens reach these multipliers from initial market cap.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⚙️ Alert Config", callback_data=f"targets:alerts_menu:{target_id}")],
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )

        except Exception as e:
            logger.error(f"Error processing thresholds input: {e}")
            await message.answer(f"❌ Error updating thresholds: {e}")

        finally:
            await state.clear()

    def _validate_thresholds_input(self, text: str) -> list[float] | None:
        """Validate and parse thresholds input"""
        try:
            # Split by comma and clean up
            parts = [part.strip() for part in text.split(',')]

            thresholds = []
            for part in parts:
                if not part:
                    continue

                try:
                    threshold = float(part)
                    if threshold <= 0:
                        return None  # Invalid: negative or zero
                    thresholds.append(threshold)
                except ValueError:
                    return None  # Invalid: not a number

            if not thresholds:
                return None  # Invalid: no valid numbers

            # Deduplicate and sort
            unique_thresholds = sorted(list(set(thresholds)))

            # Limit to reasonable count
            if len(unique_thresholds) > 20:
                return None  # Too many thresholds

            return unique_thresholds

        except Exception:
            return None

    def _merge_alert_modes_with_defaults(self, current_modes: dict) -> dict:
        """Persistence helper to merge defaults when alerts_modes is missing keys"""
        defaults = {
            "pnl": True,
            "dynamic": True,
            "threshold": True,
            "sensitivity": True
        }

        # Start with defaults
        result = defaults.copy()

        # Update with current values if they exist
        if isinstance(current_modes, dict):
            result.update(current_modes)

        return result
