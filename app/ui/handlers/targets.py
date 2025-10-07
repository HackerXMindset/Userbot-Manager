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

        # Handle pagination for targets view by group
        if parts[0] == 'targets_group_page':
            page = int(parts[2])
            group_id = int(parts[3])
            await self.show_targets_for_group(query, group_id, page)
            return

        # Handle pagination for targets alerts view
        if parts[0] == 'targets_alerts_page':
            page = int(parts[2])
            await self.show_targets_for_alerts(query, page)
            return

        action = parts[1]
        
        if action == 'view_group':
            group_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 1
            await self.show_targets_for_group(query, group_id, page)
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
            group_id = int(parts[3]) if len(parts) > 3 else None
            await self.prompt_for_sensitivity(query, state, target_id, group_id)
        elif action == 'alerts_set_thresholds':
            target_id = int(parts[2])
            group_id = int(parts[3]) if len(parts) > 3 else None
            await self.prompt_for_thresholds(query, state, target_id, group_id)
        elif action == 'sens_quick':
            target_id = int(parts[2])
            percent = int(parts[3])
            group_id = int(parts[4]) if len(parts) > 4 else None
            await self.apply_quick_sensitivity(query, target_id, percent, group_id)
        elif action == 'sens_custom':
            target_id = int(parts[2])
            await self.prompt_for_sensitivity_custom(query, state, target_id)
        elif action == 'thresh_preset':
            target_id = int(parts[2])
            preset = parts[3]
            group_id = int(parts[4]) if len(parts) > 4 else None
            await self.apply_threshold_preset(query, target_id, preset, group_id)
        elif action == 'thresh_custom':
            target_id = int(parts[2])
            await self.prompt_for_thresholds_custom(query, state, target_id)
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
            
            text = f"🎯 <b>Targets</b> ({len(targets)})\n\n"

            if not targets:
                text += "No targets configured."
            else:
                for i, target in enumerate(targets):
                    group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"

                    status = "🟢" if target['alerts_enabled'] else "🔴"
                    modes = self.target_model.parse_alert_modes(target)
                    mode_count = sum(1 for v in modes.values() if v)

                    # Tree structure like Groups UI
                    text += f"{status} {group_name}\n"

                    if target['alerts_enabled']:
                        # Get active mode icons
                        active_icons = []
                        if modes.get('pnl'): active_icons.append('📈')
                        if modes.get('threshold'): active_icons.append('🎚️')
                        if modes.get('sensitivity'): active_icons.append('⚡')
                        if modes.get('dynamic'): active_icons.append('🔄')

                        mode_icons_str = ' '.join(active_icons) if active_icons else 'None'
                        text += f"  └ Modes: {mode_count}/4 active ({mode_icons_str})\n"
                    else:
                        text += f"  └ Alerts OFF\n"

                    text += "\n"
            
            keyboard_rows = []
            if targets:
                # Add alerts config button for individual targets
                keyboard_rows.append([
                    InlineKeyboardButton(text="⚙️ Configure Alerts", callback_data="targets:select_for_alerts")
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            try:
                await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    # Message content is identical, just answer the callback
                    await query.answer()
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"Error showing targets menu: {e}")
            await query.answer("❌ Error loading targets")



    # Alert Configuration Methods

    async def show_targets_for_alerts(self, query: types.CallbackQuery, page: int = 1):
        """Show list of targets to select for alert configuration"""
        try:
            targets = await self.target_model.get_targets_with_group_info()

            page_size = 6
            total_pages = (len(targets) + page_size - 1) // page_size
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_targets = targets[start_index:end_index]

            text = f"🎯 <b>Targets</b> (Page {page}/{total_pages})\n\n"

            for i, target in enumerate(paginated_targets):
                group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                status = "🟢" if target['alerts_enabled'] else "🔴"
                modes = self.target_model.parse_alert_modes(target)
                mode_count = sum(1 for v in modes.values() if v)
                total_modes = 4

                group_name_short = group_name[:30] if len(group_name) > 30 else group_name

                # Show tree structure like Groups UI
                text += f"{status} <b>{group_name_short}</b>\n"

                if target['alerts_enabled']:
                    # Get active mode icons
                    active_icons = []
                    if modes.get('pnl'): active_icons.append('📈')
                    if modes.get('threshold'): active_icons.append('🎚️')
                    if modes.get('sensitivity'): active_icons.append('⚡')
                    if modes.get('dynamic'): active_icons.append('🔄')

                    mode_icons_str = ' '.join(active_icons) if active_icons else 'None'

                    # Calculate preview of next alerts
                    thresholds = self.target_model.parse_alert_thresholds(target)
                    sensitivity = self.target_model.get_alert_sensitivity_percent(target)

                    next_alerts = []
                    if modes.get('sensitivity') and sensitivity:
                        for j in range(1, 3):
                            next_alerts.append(1.0 * (1 + sensitivity) ** j)
                    if modes.get('threshold') and thresholds:
                        next_alerts.extend(sorted(thresholds)[:3])

                    next_alerts = sorted(set(next_alerts))[:4]
                    preview = ', '.join([f"{x:.1f}x" if x < 10 else f"{x:.0f}x" for x in next_alerts]) if next_alerts else 'None'

                    text += f"  ├ Modes: {mode_count}/{total_modes} active ({mode_icons_str})\n"
                    text += f"  └ Next: {preview}\n"
                else:
                    text += f"  └ Alerts OFF\n"

                text += "\n"

            keyboard_rows = []
            row = []
            for i, target in enumerate(paginated_targets):
                group_name = target['group_display_name'] or target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                group_name_short = group_name[:16]
                status = "🟢" if target['alerts_enabled'] else "🔴"
                button_text = f"{status} {group_name_short}"

                row.append(InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"targets:alerts_menu:{target['id']}"
                ))

                if len(row) == 2 or i == len(paginated_targets) - 1:
                    keyboard_rows.append(row)
                    row = []

            if total_pages > 1:
                keyboard_rows.append(self.keyboards.pagination("targets_alerts_page", page, total_pages))

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="targets:menu")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error showing targets for alerts: {e}")
            await query.answer("❌ Error loading targets")

    async def show_alerts_menu(self, query: types.CallbackQuery, target_id: int, group_id: int = None):
        """Show all-in-one alerts configuration screen - REDESIGNED for clean UI"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            # Get target group name for display
            group_info = await self.db.fetchrow("""
                SELECT display_name, title, tg_chat_id
                FROM groups WHERE id = $1
            """, target['group_id']) if target.get('group_id') else None

            if group_info:
                group_name = group_info['display_name'] or group_info['title'] or f"Chat {group_info['tg_chat_id']}"
            else:
                group_name = f"Chat {target['dest_chat_id']}"

            # Get alert configuration
            alert_summary = await self.target_model.get_alert_summary(target_id)
            modes = alert_summary.get('modes', {})
            thresholds = alert_summary.get('thresholds', [])
            sensitivity = alert_summary.get('sensitivity_percent', 0.50)
            enabled = alert_summary.get('enabled', True)

            # Status
            status_icon = "🟢" if enabled else "🔴"
            status_text = "ENABLED" if enabled else "DISABLED"

            # Build clean UI text with tree structure (matching Groups UI)
            text = f"⚙️ <b>{group_name}</b>\n\n"
            text += f"<b>STATUS</b>\n{status_icon} Alerts <b>{status_text}</b>\n\n"

            if enabled:
                # Show alert modes with tree structure
                text += f"<b>MODES</b>\n"

                # PNL mode
                pnl_status = "✅" if modes.get('pnl', True) else "❌"
                text += f"📈 PNL Commands\n"
                text += f"  └ {pnl_status} {'Active' if modes.get('pnl', True) else 'Disabled'}\n\n"

                # Threshold mode
                thresh_status = "✅" if modes.get('threshold', True) else "❌"
                thresh_text = ', '.join([f'{x}x' for x in thresholds]) if thresholds else "None"
                text += f"🎚️ Threshold\n"
                text += f"  ├ {thresh_status} {'Active' if modes.get('threshold', True) else 'Disabled'}\n"
                text += f"  └ Values: {thresh_text}\n\n"

                # Sensitivity mode
                sens_status = "✅" if modes.get('sensitivity', True) else "❌"
                sens_pct = sensitivity * 100
                text += f"⚡ Sensitivity\n"
                text += f"  ├ {sens_status} {'Active' if modes.get('sensitivity', True) else 'Disabled'}\n"
                text += f"  └ Rate: {sens_pct:.0f}% (+{sensitivity:.2f} per alert)\n\n"

                # Dynamic mode
                dynamic_status = "✅" if modes.get('dynamic', False) else "❌"
                text += f"🔄 Dynamic Tracking\n"
                text += f"  └ {dynamic_status} {'Active' if modes.get('dynamic', False) else 'Disabled'}\n\n"

                # Preview of next alerts
                text += f"<b>PREVIEW</b>\n"

                # Combine threshold and sensitivity alerts
                next_alerts = []

                # Add threshold alerts
                for thresh in sorted(thresholds):
                    if modes.get('threshold', True):
                        next_alerts.append((thresh, 'T'))

                # Add first 3 sensitivity alerts
                if modes.get('sensitivity', True):
                    for i in range(1, 4):
                        sens_mult = 1.0 * (1 + sensitivity) ** i
                        next_alerts.append((sens_mult, 'S'))

                # Sort and format
                next_alerts = sorted(set(next_alerts), key=lambda x: x[0])[:6]  # Show first 6
                preview_text = ", ".join([f"{mult:.2f}x" for mult, _ in next_alerts])
                text += f"Next alerts: {preview_text}..."
            else:
                text += f"<i>Enable alerts to configure modes</i>"

            # Determine back callback
            back_callback = f"group:alerts:{group_id}" if group_id else "targets:select_for_alerts"

            # Use new keyboard layout
            keyboard = self.keyboards.target_alerts_config_clean(target, back_callback=back_callback)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error showing alerts menu: {e}", exc_info=True)
            await query.answer("❌ Error loading alert configuration")

    async def show_alert_modes(self, query: types.CallbackQuery, target_id: int):
        """Show alert modes configuration"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            modes = self.target_model.parse_alert_modes(target)
            thresholds = self.target_model.parse_alert_thresholds(target)

            mode_descriptions = {
                "pnl": "Send /pnl commands",
                "dynamic": "Legacy mode",
                "threshold": f"Fire at {', '.join([str(t) + 'x' for t in thresholds])}",
                "sensitivity": "Progressive tracking"
            }

            mode_icons = {
                "pnl": "📈",
                "dynamic": "🔄",
                "threshold": "🎚️",
                "sensitivity": "⚡"
            }

            text = f"🎛️ Alert Modes\n\n━━━━━━━━━━━━━━━━━━━━\n\n"

            for mode, enabled in modes.items():
                icon = mode_icons.get(mode, "•")
                status = "✅" if enabled else "❌"
                desc = mode_descriptions.get(mode, "")
                mode_name = mode.upper()
                text += f"{icon} {mode_name}                 {status}\n   {desc}\n\n"

            text += "━━━━━━━━━━━━━━━━━━━━\n\nTap mode to toggle on/off"

            keyboard = self.keyboards.target_alerts_mode_keyboard(target)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

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

    async def prompt_for_sensitivity(self, query: types.CallbackQuery, state: FSMContext, target_id: int, group_id: int = None):
        """Prompt for sensitivity percentage input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.get_alert_sensitivity_percent(target)
            current_pct = current * 100
            seq = [1.0 * (1 + current)**i for i in range(4)]
            seq_text = " → ".join([f"{s:.2f}x" for s in seq])

            text = (
                f"⚡ Sensitivity\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"CURRENT      <b>{current_pct:.0f}%</b>\n\n"
                f"ALERT MULTIPLIERS\n"
                f"{seq_text}\n"
                f"<i>(from baseline MC)</i>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Enter new % (5-500):\n\n"
                f"  <code>25%</code>  → 1.25x, 1.56x, 1.95x\n"
                f"  <code>50%</code>  → 1.5x, 2.25x, 3.4x\n"
                f"  <code>100%</code> → 2x, 4x, 8x\n\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

            # Build callback data with optional group_id
            group_suffix = f":{group_id}" if group_id else ""

            # Show quick-set buttons instead of FSM
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="25%", callback_data=f"targets:sens_quick:{target_id}:25{group_suffix}"),
                    InlineKeyboardButton(text="50%", callback_data=f"targets:sens_quick:{target_id}:50{group_suffix}"),
                    InlineKeyboardButton(text="75%", callback_data=f"targets:sens_quick:{target_id}:75{group_suffix}"),
                    InlineKeyboardButton(text="100%", callback_data=f"targets:sens_quick:{target_id}:100{group_suffix}")
                ],
                [
                    InlineKeyboardButton(text="✏️ Custom", callback_data=f"targets:sens_custom:{target_id}{group_suffix}"),
                    InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_menu:{target_id}{group_suffix}")
                ]
            ])

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error prompting for sensitivity: {e}")
            await query.answer("❌ Error setting up sensitivity input")

    async def prompt_for_thresholds(self, query: types.CallbackQuery, state: FSMContext, target_id: int, group_id: int = None):
        """Prompt for thresholds input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.parse_alert_thresholds(target)
            current_text = ', '.join([f'{x}x' for x in current])

            text = (
                f"🎚️ Thresholds\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"CURRENT      <b>{current_text}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"PRESETS\n\n"
                f"  <b>Conservative</b>\n"
                f"  2x, 5x, 10x, 25x\n\n"
                f"  <b>Balanced</b>\n"
                f"  2x, 7x, 25x, 100x\n\n"
                f"  <b>Aggressive</b>\n"
                f"  3x, 10x, 50x\n\n"
                f"  <b>Moonshot</b>\n"
                f"  5x, 25x, 100x, 500x\n\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )

            # Build callback data with optional group_id
            group_suffix = f":{group_id}" if group_id else ""

            # Show preset buttons instead of FSM
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Conservative", callback_data=f"targets:thresh_preset:{target_id}:conservative{group_suffix}")],
                [InlineKeyboardButton(text="Balanced", callback_data=f"targets:thresh_preset:{target_id}:balanced{group_suffix}")],
                [InlineKeyboardButton(text="Aggressive", callback_data=f"targets:thresh_preset:{target_id}:aggressive{group_suffix}")],
                [InlineKeyboardButton(text="Moonshot", callback_data=f"targets:thresh_preset:{target_id}:moonshot{group_suffix}")],
                [InlineKeyboardButton(text="✏️ Custom", callback_data=f"targets:thresh_custom:{target_id}{group_suffix}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_menu:{target_id}{group_suffix}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

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
                await message.answer(
                    "❌ Error: No target selected. Please try again.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="targets:select_for_alerts")]
                    ])
                )
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
                await message.answer(
                    "❌ Error: No target selected. Please try again.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="targets:select_for_alerts")]
                    ])
                )
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

    async def show_targets_for_group(self, query: types.CallbackQuery, group_id: int, page: int = 1):
        """Show targets for a specific group with pagination"""
        try:
            # Get targets for the group
            targets = await self.target_model.get_by_group_id(group_id)

            # Get group info
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['display_name'] or group['title'] or f"Group {group_id}" if group else f"Group {group_id}"

            # Pagination logic (same as groups.py)
            page_size = 5
            total_pages = (len(targets) + page_size - 1) // page_size if targets else 1
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_targets = targets[start_index:end_index]

            text = f"<b>🎯 Targets in {group_name} (Page {page}/{total_pages})</b>\n\n"

            if not targets:
                text += "No targets configured for this group.\nClick 'Add Target' to create one."
            else:
                for i, target in enumerate(paginated_targets, start_index + 1):
                    # Get alert summary
                    alert_summary = await self.target_model.get_alert_summary(target['id'])
                    alert_text = alert_summary.get('summary_text', 'Alerts: Unknown')

                    text += f"{i}. 📱 <code>{target['dest_chat_id']}</code>\n"
                    text += f"   └ {alert_text}\n\n"

            keyboard_rows = []

            # Target action buttons
            for target in paginated_targets:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"⚙️ Configure {target['dest_chat_id']}",
                        callback_data=f"targets:alerts_menu:{target['id']}:{group_id}"
                    )
                ])

            # Navigation buttons
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")
            ])

            # Pagination buttons (same pattern as groups.py)
            if total_pages > 1:
                pagination_buttons = self.keyboards.pagination(f"targets_group_page", page, total_pages)
                # Add group_id to pagination callback
                for button in pagination_buttons:
                    if button.callback_data.endswith(str(page-1)) or button.callback_data.endswith(str(page+1)):
                        button.callback_data += f":{group_id}"
                keyboard_rows.append(pagination_buttons)

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Error showing targets for group {group_id}: {e}")
            await query.answer("❌ Error loading targets for group")

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

    async def apply_quick_sensitivity(self, query: types.CallbackQuery, target_id: int, percent: int, group_id: int = None):
        """Apply quick sensitivity preset"""
        try:
            sensitivity_decimal = percent / 100.0
            await self.target_model.update_alert_sensitivity(target_id, sensitivity_decimal)

            await query.answer(f"✅ Set to {percent}%")
            await self.show_alerts_menu(query, target_id, group_id)
        except Exception as e:
            logger.error(f"Error applying quick sensitivity: {e}")
            await query.answer("❌ Error updating sensitivity")

    async def prompt_for_sensitivity_custom(self, query: types.CallbackQuery, state: FSMContext, target_id: int):
        """Prompt for custom sensitivity input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.get_alert_sensitivity_percent(target)
            current_pct = current * 100

            text = (
                f"⚡ Custom Sensitivity\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"CURRENT      <b>{current_pct:.0f}%</b>\n\n"
                f"Enter percentage (5-500):\n"
                f"Example: 75\n\n"
                f"Type /cancel to abort."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_set_sensitivity:{target_id}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await state.set_state(ManagementStates.target_edit_sensitivity.state)
            await state.update_data(target_id=target_id, message_id=query.message.message_id)

        except Exception as e:
            logger.error(f"Error prompting for custom sensitivity: {e}")
            await query.answer("❌ Error setting up sensitivity input")

    async def apply_threshold_preset(self, query: types.CallbackQuery, target_id: int, preset: str, group_id: int = None):
        """Apply threshold preset"""
        try:
            presets = {
                "conservative": [2, 5, 10, 25],
                "balanced": [2, 7, 25, 100],
                "aggressive": [3, 10, 50],
                "moonshot": [5, 25, 100, 500]
            }

            thresholds = presets.get(preset, [2, 7, 25])
            await self.target_model.update_alert_thresholds(target_id, thresholds)

            await query.answer(f"✅ {preset.title()} preset applied")
            await self.show_alerts_menu(query, target_id, group_id)
        except Exception as e:
            logger.error(f"Error applying preset: {e}")
            await query.answer("❌ Error updating thresholds")

    async def prompt_for_thresholds_custom(self, query: types.CallbackQuery, state: FSMContext, target_id: int):
        """Prompt for custom threshold input"""
        try:
            target = await self.target_model.get_by_id(target_id)
            if not target:
                await query.answer("❌ Target not found")
                return

            current = self.target_model.parse_alert_thresholds(target)
            current_text = ', '.join([f'{x}x' for x in current])

            text = (
                f"🎚️ Custom Thresholds\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"CURRENT      <b>{current_text}</b>\n\n"
                f"Enter comma-separated:\n"
                f"Example: 2,5,10,25\n\n"
                f"Type /cancel to abort."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"targets:alerts_set_thresholds:{target_id}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await state.set_state(ManagementStates.target_edit_thresholds.state)
            await state.update_data(target_id=target_id, message_id=query.message.message_id)

        except Exception as e:
            logger.error(f"Error prompting for custom thresholds: {e}")
            await query.answer("❌ Error setting up thresholds input")
