from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class Keyboards:
    """All inline keyboards for the management bot"""

    @staticmethod
    def format_blockchain_emojis(allowed_chains: List[str]) -> str:
        """Format blockchain filter as emojis

        Args:
            allowed_chains: List of allowed blockchains (e.g., ["SOL", "BNB"])

        Returns:
            String with blockchain emojis (e.g., "🟣 SOL 🟡 BNB")
        """
        if not allowed_chains:
            return "❌"

        emojis = []
        if "SOL" in allowed_chains:
            emojis.append("🟣 SOL")
        if "BNB" in allowed_chains:
            emojis.append("🟡 BNB")

        return " ".join(emojis) if emojis else "❌"

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Main menu keyboard"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🧾 Overview", callback_data="menu:status"),
                InlineKeyboardButton(text="🎯 Target", callback_data="menu:groups")
            ],
            [
                InlineKeyboardButton(text="👤 Agents", callback_data="menu:userbots")
            ],
            [
                InlineKeyboardButton(text="📡 Sources", callback_data="menu:sources"),
                InlineKeyboardButton(text="💹 Profit Logs", callback_data="menu:pnl")
            ],
            [
                InlineKeyboardButton(text="📬 Inbox", callback_data="menu:notifications"),
                InlineKeyboardButton(text="📡 Auto-Tap", callback_data="menu:auto_click")
            ],
            [
                InlineKeyboardButton(text="✨ Curate Alpha", callback_data="menu:curate_alpha"),
                InlineKeyboardButton(text="📝 Templates", callback_data="menu:templates")
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="menu:settings")
            ],
            [
                InlineKeyboardButton(text="🔻 Collapse", callback_data="menu:close")
            ]
        ])
    
    @staticmethod
    def groups_menu(groups: List[Dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
        """Groups management menu"""
        keyboard = []
        
        for group in groups:
            status = "✅" if group['enabled'] else "❌"
            display_name = (group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}")[:20]
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {display_name}",
                    callback_data=f"group:view:{group['id']}"
                )
            ])
        
        if total_pages > 1:
            keyboard.append(Keyboards.pagination("groups_page", page, total_pages))

        keyboard.append([
            InlineKeyboardButton(text="➕ Add Group", callback_data="group:add"),
            InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def group_details(group: Dict) -> InlineKeyboardMarkup:
        """Single group details menu"""
        status_btn = InlineKeyboardButton(
            text="🔴 Disable" if group['enabled'] else "🟢 Enable",
            callback_data=f"group:toggle:{group['id']}"
        )
        
        return InlineKeyboardMarkup(inline_keyboard=[
            [status_btn],
            [
                InlineKeyboardButton(text="✏️ Set Name", callback_data=f"group:set_name:{group['id']}"),
                InlineKeyboardButton(text="📅 Schedules", callback_data=f"group:schedules:{group['id']}")
            ],
            [
                InlineKeyboardButton(text="🤖 Assign Bot", callback_data=f"group:assign:{group['id']}"),
                InlineKeyboardButton(text="📊 Stats", callback_data=f"group:stats:{group['id']}")
            ],
            [
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"group:delete:{group['id']}"),
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:groups")
            ]
        ])
    
    @staticmethod
    def schedule_wizard(group_id: int, step: str = 'days') -> InlineKeyboardMarkup:
        """Schedule creation wizard"""
        if step == 'days':
            return InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Mon", callback_data=f"sched:day:1:{group_id}"),
                    InlineKeyboardButton(text="Tue", callback_data=f"sched:day:2:{group_id}"),
                    InlineKeyboardButton(text="Wed", callback_data=f"sched:day:3:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="Thu", callback_data=f"sched:day:4:{group_id}"),
                    InlineKeyboardButton(text="Fri", callback_data=f"sched:day:5:{group_id}"),
                    InlineKeyboardButton(text="Sat", callback_data=f"sched:day:6:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="Sun", callback_data=f"sched:day:7:{group_id}"),
                    InlineKeyboardButton(text="All Days", callback_data=f"sched:day:all:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="✅ Continue", callback_data=f"sched:next:{group_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"group:schedules:{group['id']}")
                ]
            ])
        
        return InlineKeyboardMarkup(inline_keyboard=[])
    
    @staticmethod
    def userbots_menu(userbots: List[Dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
        """Userbots management menu"""
        keyboard = []
        
        for bot in userbots:
            status_icon = "🟢" if bot['status'] == 'active' else "🔴"
            name = (bot.get('display_name') or bot['session_name'])[:20]
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} {name}",
                    callback_data=f"userbot:view:{bot['id']}"
                )
            ])
        
        if total_pages > 1:
            keyboard.append(Keyboards.pagination("userbots_page", page, total_pages))

        keyboard.extend([
            [
                InlineKeyboardButton(text="➕ Add Userbot", callback_data="userbot:add"),
                InlineKeyboardButton(text="🔄 Check Health", callback_data="userbot:health")
            ],
            [
                InlineKeyboardButton(text="🔄 Refresh Sources", callback_data="userbot:refresh_sources")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
            ]
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def confirm_action(action: str, item_id: Any) -> InlineKeyboardMarkup:
        """Generic confirmation dialog"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes", callback_data=f"confirm:{action}:{item_id}"),
                InlineKeyboardButton(text="❌ No", callback_data=f"cancel:{action}:{item_id}")
            ]
        ])
    
    @staticmethod
    def number_picker(prefix: str, current: int, min_val: int = 0, max_val: int = 100) -> InlineKeyboardMarkup:
        """Number picker with increment/decrement"""
        keyboard = [
            [
                InlineKeyboardButton(text="-10", callback_data=f"{prefix}:dec:10"),
                InlineKeyboardButton(text="-1", callback_data=f"{prefix}:dec:1"),
                InlineKeyboardButton(text=f"{current}", callback_data=f"{prefix}:current"),
                InlineKeyboardButton(text="+1", callback_data=f"{prefix}:inc:1"),
                InlineKeyboardButton(text="+10", callback_data=f"{prefix}:inc:10")
            ],
            [
                InlineKeyboardButton(text="✅ Set", callback_data=f"{prefix}:set:{current}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"{prefix}:cancel")
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def back_button(callback_data: str) -> InlineKeyboardMarkup:
        """Simple back button"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data=callback_data)]
        ])
    
    @staticmethod
    def cancel_button(callback_data: str) -> InlineKeyboardMarkup:
        """Simple cancel button"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data=callback_data)]
        ])
    
    @staticmethod
    def pagination(prefix: str, page: int, total_pages: int) -> List[InlineKeyboardButton]:
        """Pagination buttons"""
        logger.debug(f"Generating pagination with prefix='{prefix}', page={page}, total_pages={total_pages}")
        buttons = []
        
        if page > 1:
            callback_data = f"{prefix}:page:{page-1}"
            logger.debug(f"  - Previous button callback: {callback_data}")
            buttons.append(InlineKeyboardButton(text="⬅️", callback_data=callback_data))
        
        buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{prefix}:page:info"))
        
        if page < total_pages:
            callback_data = f"{prefix}:page:{page+1}"
            logger.debug(f"  - Next button callback: {callback_data}")
            buttons.append(InlineKeyboardButton(text="➡️", callback_data=callback_data))
        
        return buttons

    @staticmethod
    def notifications_menu(settings: Dict, blacklist: List[Dict]) -> InlineKeyboardMarkup:
        """Notifications management menu"""
        keyboard = [
            [
                InlineKeyboardButton(text="📢 Set Channel", callback_data="notifications:set_channel"),
            ],
            [
                InlineKeyboardButton(text=f"🚫 Blacklist ({len(blacklist)})", callback_data="notifications:blacklist"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:main"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def notification_blacklist_menu(blacklist: List[Dict]) -> InlineKeyboardMarkup:
        """Notification blacklist management menu"""
        keyboard = []
        for user in blacklist:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑️ Remove {user['user_id']}",
                    callback_data=f"notifications:remove_blacklist:{user['user_id']}"
                )
            ])
        keyboard.append([
            InlineKeyboardButton(text="➕ Add User", callback_data="notifications:add_blacklist"),
        ])
        keyboard.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="menu:notifications"),
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def pnl_rules_list(rules: List[Dict]) -> InlineKeyboardMarkup:
        keyboard = []
        for rule in rules[:10]:
            status = "✅" if rule['enabled'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {rule['source_group_title']} -> {rule['destination_channel_title']}",
                    callback_data=f"pnl:view:{rule['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="➕ Add New Rule", callback_data="pnl:add")])
        keyboard.append([InlineKeyboardButton(text="🔄 Set Dynamic Forwarding", callback_data="cmd_fwd:list")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def pnl_rule_details_menu(rule: Dict) -> InlineKeyboardMarkup:
        status_btn = InlineKeyboardButton(
            text="🔴 Disable" if rule['enabled'] else "🟢 Enable",
            callback_data=f"pnl:toggle:{rule['id']}"
        )
        return InlineKeyboardMarkup(inline_keyboard=[
            [status_btn],
            [
                InlineKeyboardButton(text="👥 Manage Command Users", callback_data=f"pnl:manage_command_users:{rule['id']}"),
            ],
            [
                InlineKeyboardButton(text="👥 Manage Reply Users", callback_data=f"pnl:manage_reply_users:{rule['id']}")
            ],
            [InlineKeyboardButton(text="🤖 Set Forwarding Bot", callback_data=f"pnl:set_fwd_bot:{rule['id']}")],
            [InlineKeyboardButton(text="🗑️ Delete Rule", callback_data=f"pnl:delete:{rule['id']}")],
            [InlineKeyboardButton(text="🔙 Back to List", callback_data="pnl:list")]
        ])

    @staticmethod
    def pnl_select_source_group_keyboard(groups: List[Dict]) -> InlineKeyboardMarkup:
        keyboard = []
        for group in groups:
            display_name = (group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}")[:20]
            keyboard.append([
                InlineKeyboardButton(text=display_name, callback_data=f"pnl:wizard_source_group:{group['id']}")
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="pnl:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def pnl_manage_users_keyboard(user_ids: List[int], user_type: str, rule_id: int = None) -> InlineKeyboardMarkup:
        keyboard = []
        for user_id in user_ids:
            keyboard.append([
                InlineKeyboardButton(text=f"🗑️ Remove {user_id}", callback_data=f"pnl:wizard_remove_{user_type}:{user_id}")
            ])
        
        add_callback = f"pnl:wizard_add_{user_type}"
        
        keyboard.append([InlineKeyboardButton(text=f"➕ Add {user_type.replace('_', ' ').title()}", callback_data=add_callback)])
        
        if rule_id:
            keyboard.append([InlineKeyboardButton(text="🔙 Back to Rule", callback_data=f"pnl:view:{rule_id}")])
        else:
            next_callback = f"pnl:wizard_next_to_fwd_bot" if user_type == "monitored" else f"pnl:wizard_next_to_summary"
            keyboard.append([InlineKeyboardButton(text="➡️ Continue", callback_data=next_callback)])
            keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="pnl:list")])
            
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def pnl_select_forwarding_bot_keyboard(userbots: List[Dict]) -> InlineKeyboardMarkup:
        keyboard = []
        for bot in userbots:
            keyboard.append([
                InlineKeyboardButton(text=(bot.get('display_name') or bot['session_name']), callback_data=f"pnl:wizard_fwd_bot:{bot['id']}")
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="pnl:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def pnl_confirm_delete(rule_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"pnl:confirm_delete:{rule_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"pnl:view:{rule_id}")
            ]
        ])

    @staticmethod
    def pnl_rule_summary_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Save Rule", callback_data="pnl:wizard_save")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="pnl:list")]
        ])

    @staticmethod
    def pnl_rule_details_text(rule: Dict, source_group: Dict, dest_channel_info: Dict, fwd_bot: Dict) -> str:
        status = '✅ Enabled' if rule['enabled'] else '❌ Disabled'
        
        source_title = source_group['title'] if source_group else 'N/A'
        dest_title = dest_channel_info['title']
        bot_name = fwd_bot['display_name'] if fwd_bot else 'Not Set'
        
        command_users = rule.get('allowed_pnl_command_user_ids', []) or []
        reply_users = rule.get('allowed_reply_user_ids', []) or []

        text = (
            f"<b>💸 PNL Forwarding Rule Details</b>\n\n"
            f"<b>Status: {status}</b>\n\n"
            f"<b>Source Group:</b>\n"
            f"  └ {source_title}\n\n"
            f"<b>Destination Channel:</b>\n"
            f"  └ {dest_title}\n\n"
            f"<b>Forwarding Userbot:</b>\n"
            f"  └ {bot_name}\n\n"
            f"<b>Permissions:</b>\n"
            f"  ├ <b>Command Users:</b> {len(command_users) if command_users else 'Anyone'}\n"
            f"  └ <b>Reply Users:</b> {len(reply_users) if reply_users else 'Anyone'}"
        )
        
        # Optionally, list some of the user IDs
        if command_users:
            text += "\n\n<b>Command User IDs:</b>\n" + ", ".join(map(str, command_users[:5]))
            if len(command_users) > 5:
                text += "..."
        
        if reply_users:
            text += "\n\n<b>Reply User IDs:</b>\n" + ", ".join(map(str, reply_users[:5]))
            if len(reply_users) > 5:
                text += "..."
                
        return text

    # ===== COMMAND FORWARDING KEYBOARDS =====

    @staticmethod
    def cmd_fwd_rules_list(rules: List[Dict]) -> InlineKeyboardMarkup:
        """Command forwarding rules list keyboard"""
        keyboard = []
        for rule in rules[:10]:
            status = "✅" if rule['enabled'] else "❌"
            schedule_status = "⏰" if rule.get('schedule_enabled') else ""
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status}{schedule_status} {rule['command_text']} → {rule.get('destination_channel_title', f'ID:{rule['destination_channel_id']}')}",
                    callback_data=f"cmd_fwd:view:{rule['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="➕ Add New Command Rule", callback_data="cmd_fwd:add")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back to PNL", callback_data="pnl:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_rule_details_menu(rule: Dict) -> InlineKeyboardMarkup:
        """Command forwarding rule details menu"""
        status_btn = InlineKeyboardButton(
            text="🔴 Disable" if rule['enabled'] else "🟢 Enable",
            callback_data=f"cmd_fwd:toggle:{rule['id']}"
        )
        schedule_btn = InlineKeyboardButton(
            text="⏰ Disable Schedule" if rule.get('schedule_enabled') else "⏰ Enable Schedule",
            callback_data=f"cmd_fwd:toggle_schedule:{rule['id']}"
        )
        timestamp_btn = InlineKeyboardButton(
            text="🕒 Disable Timestamp" if rule.get('post_timestamp') else "🕒 Enable Timestamp",
            callback_data=f"cmd_fwd:toggle_timestamp:{rule['id']}"
        )

        keyboard = [
            [status_btn],
            [schedule_btn],
            [timestamp_btn]
        ]

        # Only show timezone selector if timestamp posting is enabled
        if rule.get('post_timestamp'):
            timezone = rule.get('timestamp_timezone', 'IST')
            timezone_btn = InlineKeyboardButton(
                text=f"🌍 Timezone: {timezone}",
                callback_data=f"cmd_fwd:set_timezone:{rule['id']}"
            )
            keyboard.append([timezone_btn])

        keyboard.extend([
            [
                InlineKeyboardButton(text="💬 Edit Command", callback_data=f"cmd_fwd:edit_command:{rule['id']}"),
                InlineKeyboardButton(text="👥 Manage Command Users", callback_data=f"cmd_fwd:manage_command_users:{rule['id']}"),
            ],
            [
                InlineKeyboardButton(text="👥 Manage Reply Users", callback_data=f"cmd_fwd:manage_reply_users:{rule['id']}"),
                InlineKeyboardButton(text="🤖 Set Forwarding Bot", callback_data=f"cmd_fwd:set_fwd_bot:{rule['id']}")
            ],
            [
                InlineKeyboardButton(text="⚙️ Schedule Settings", callback_data=f"cmd_fwd:schedule_settings:{rule['id']}"),
                InlineKeyboardButton(text="🔇 Ignore Messages", callback_data=f"cmd_fwd:manage_excluded:{rule['id']}")
            ],
            [InlineKeyboardButton(text="🗑️ Delete Rule", callback_data=f"cmd_fwd:delete:{rule['id']}")],
            [InlineKeyboardButton(text="🔙 Back to List", callback_data="cmd_fwd:list")]
        ])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_timezone_selection_keyboard(rule_id: int, current_tz: str) -> InlineKeyboardMarkup:
        """Timezone selection keyboard"""
        timezones = [
            ('IST', 'Indian Standard Time'),
            ('UTC', 'Coordinated Universal Time'),
            ('EST', 'Eastern Standard Time'),
            ('PST', 'Pacific Standard Time'),
            ('CST', 'Central Standard Time'),
            ('JST', 'Japan Standard Time'),
            ('AEST', 'Australian Eastern Standard Time'),
            ('CET', 'Central European Time'),
            ('GMT', 'Greenwich Mean Time')
        ]

        keyboard = []
        row = []
        for i, (tz_code, tz_name) in enumerate(timezones):
            button_text = f"{'✅ ' if tz_code == current_tz else ''}{tz_code}"
            row.append(InlineKeyboardButton(
                text=button_text,
                callback_data=f"cmd_fwd:select_timezone:{rule_id}:{tz_code}"
            ))
            if len(row) == 3 or i == len(timezones) - 1:
                keyboard.append(row)
                row = []

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"cmd_fwd:view:{rule_id}")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_select_source_group_keyboard(groups: List[Dict]) -> InlineKeyboardMarkup:
        """Source group selection for command forwarding"""
        keyboard = []
        for group in groups:
            display_name = (group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}")[:20]
            keyboard.append([
                InlineKeyboardButton(text=display_name, callback_data=f"cmd_fwd:wizard_source_group:{group['id']}")
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_fwd:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_manage_users_keyboard(user_ids: List[int], user_type: str, rule_id: int = None) -> InlineKeyboardMarkup:
        """User management keyboard for command forwarding"""
        keyboard = []
        for user_id in user_ids:
            keyboard.append([
                InlineKeyboardButton(text=f"🗑️ Remove {user_id}", callback_data=f"cmd_fwd:wizard_remove_{user_type}:{user_id}")
            ])

        add_callback = f"cmd_fwd:wizard_add_{user_type}"

        keyboard.append([InlineKeyboardButton(text=f"➕ Add {user_type.replace('_', ' ').title()}", callback_data=add_callback)])

        if rule_id:
            keyboard.append([InlineKeyboardButton(text="🔙 Back to Rule", callback_data=f"cmd_fwd:view:{rule_id}")])
        else:
            if user_type == "monitored":
                next_callback = f"cmd_fwd:wizard_next_to_fwd_bot"
            elif user_type == "replying":
                next_callback = f"cmd_fwd:wizard_next_to_schedule"
            else:
                next_callback = f"cmd_fwd:wizard_next_to_destination"
            keyboard.append([InlineKeyboardButton(text="➡️ Continue", callback_data=next_callback)])
            keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_fwd:list")])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_select_forwarding_bot_keyboard(userbots: List[Dict]) -> InlineKeyboardMarkup:
        """Forwarding bot selection for command forwarding"""
        keyboard = []
        for bot in userbots:
            keyboard.append([
                InlineKeyboardButton(text=(bot.get('display_name') or bot['session_name']), callback_data=f"cmd_fwd:wizard_fwd_bot:{bot['id']}")
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_fwd:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_schedule_options_keyboard() -> InlineKeyboardMarkup:
        """Schedule options keyboard"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ No Schedule (Manual only)", callback_data="cmd_fwd:wizard_schedule:none")],
            [InlineKeyboardButton(text="⏰ Every 1 hour", callback_data="cmd_fwd:wizard_schedule:60")],
            [InlineKeyboardButton(text="⏰ Every 6 hours", callback_data="cmd_fwd:wizard_schedule:360")],
            [InlineKeyboardButton(text="⏰ Every 24 hours", callback_data="cmd_fwd:wizard_schedule:1440")],
            [InlineKeyboardButton(text="⚙️ Custom Interval", callback_data="cmd_fwd:wizard_schedule:custom")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_fwd:list")]
        ])

    @staticmethod
    def cmd_fwd_confirm_delete(rule_id: int) -> InlineKeyboardMarkup:
        """Delete confirmation for command forwarding rule"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"cmd_fwd:confirm_delete:{rule_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"cmd_fwd:view:{rule_id}")
            ]
        ])

    @staticmethod
    def cmd_fwd_rule_summary_keyboard() -> InlineKeyboardMarkup:
        """Rule summary keyboard for command forwarding"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Save Rule", callback_data="cmd_fwd:wizard_save")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_fwd:list")]
        ])

    @staticmethod
    def cmd_fwd_excluded_messages_keyboard(excluded_texts: List[str], rule_id: int) -> InlineKeyboardMarkup:
        """Keyboard for managing excluded message texts"""
        keyboard = []

        # Show each excluded text with remove button
        for i, text in enumerate(excluded_texts):
            # Truncate long texts for display
            display_text = text if len(text) <= 40 else text[:37] + "..."
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑️ Remove \"{display_text}\"",
                    callback_data=f"cmd_fwd:remove_excluded:{rule_id}:{i}"
                )
            ])

        # Add new excluded text button
        keyboard.append([InlineKeyboardButton(text="➕ Add Excluded Text", callback_data=f"cmd_fwd:add_excluded:{rule_id}")])

        # Back button
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Rule", callback_data=f"cmd_fwd:view:{rule_id}")])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def cmd_fwd_rule_details_text(rule: Dict, source_group: Dict, dest_channel_info: Dict, fwd_bot: Dict) -> str:
        """Generate details text for command forwarding rule"""
        status = '✅ Enabled' if rule['enabled'] else '❌ Disabled'
        schedule_status = '✅ Enabled' if rule.get('schedule_enabled') else '❌ Disabled'

        source_title = source_group['title'] if source_group else 'N/A'
        dest_title = dest_channel_info['title']
        bot_name = fwd_bot['display_name'] if fwd_bot else 'Not Set'

        command_users = rule.get('allowed_command_user_ids', []) or []
        reply_users = rule.get('allowed_reply_user_ids', []) or []

        text = (
            f"<b>🔄 Command Forwarding Rule Details</b>\n\n"
            f"<b>Status: {status}</b>\n"
            f"<b>Schedule: {schedule_status}</b>\n\n"
            f"<b>Command:</b>\n"
            f"  └ {rule['command_text']}\n\n"
            f"<b>Source Group:</b>\n"
            f"  └ {source_title}\n\n"
            f"<b>Destination Channel:</b>\n"
            f"  └ {dest_title}\n\n"
            f"<b>Forwarding Userbot:</b>\n"
            f"  └ {bot_name}\n\n"
            f"<b>Permissions:</b>\n"
            f"  ├ <b>Command Users:</b> {len(command_users) if command_users else 'Anyone'}\n"
            f"  └ <b>Reply Users:</b> {len(reply_users) if reply_users else 'Anyone'}"
        )

        # Add schedule information
        if rule.get('schedule_enabled') and rule.get('schedule_interval_minutes'):
            hours = rule['schedule_interval_minutes'] // 60
            minutes = rule['schedule_interval_minutes'] % 60
            if hours > 0:
                if minutes > 0:
                    interval_text = f"{hours}h {minutes}m"
                else:
                    interval_text = f"{hours}h"
            else:
                interval_text = f"{minutes}m"
            text += f"\n\n<b>Schedule:</b>\n  └ Every {interval_text}"

            if rule.get('next_scheduled_at'):
                text += f"\n  └ Next: {rule['next_scheduled_at'].strftime('%Y-%m-%d %H:%M UTC')}"

        # Add timestamp posting information
        timestamp_status = '✅ Enabled' if rule.get('post_timestamp') else '❌ Disabled'
        text += f"\n\n<b>Timestamp Posting: {timestamp_status}</b>"
        if rule.get('post_timestamp'):
            timezone = rule.get('timestamp_timezone', 'IST')
            text += f"\n  └ Timezone: {timezone}"

        return text

    @staticmethod
    def auto_click_menu(rules: List[Dict]) -> InlineKeyboardMarkup:
        """Auto click main menu (clean - no rule list)"""
        keyboard = [
            [InlineKeyboardButton(text="🔍 Scanning Clicker", callback_data="auto_click:scanning_menu")],
            [InlineKeyboardButton(text="🔫 Raider", callback_data="auto_click:raider_menu")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def scanning_menu() -> InlineKeyboardMarkup:
        """Scanning Clicker submenu"""
        keyboard = [
            [InlineKeyboardButton(text="➕ Add New Rule", callback_data="auto_click:add")],
            [InlineKeyboardButton(text="📋 Show All Rules", callback_data="auto_click:scanning_list")],
            [InlineKeyboardButton(text="🔙 Back to Auto-Tap", callback_data="auto_click:menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def scanning_rules_list(rules: List[Dict], page: int = 1) -> InlineKeyboardMarkup:
        """List of scanning rules (static rules only) with pagination"""
        keyboard = []
        static_rules = [r for r in rules if r.get('rule_type') == 'static' or not r.get('rule_type')]

        # Pagination
        items_per_page = 9
        total_pages = max(1, (len(static_rules) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_rules = static_rules[start_idx:end_idx]

        for rule in page_rules:
            status = "✅" if rule['enabled'] else "❌"
            rule_name = rule.get('name')

            if rule_name:
                text = f"{status} 📍 {rule_name}"
            else:
                text = f"{status} 📍 Chat: {rule['target_chat_id']}, Bot: {rule.get('bot_id', 'N/A')}"

            keyboard.append([
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"auto_click:view:{rule['id']}"
                )
            ])

        if not keyboard:
            keyboard.append([InlineKeyboardButton(text="No scanning rules yet", callback_data="auto_click:scanning_menu")])

        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(text="« Prev", callback_data=f"auto_click:scanning_list:{page-1}"))
            nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(text="Next »", callback_data=f"auto_click:scanning_list:{page+1}"))
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(text="🔙 Back to Scanning Menu", callback_data="auto_click:scanning_menu")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def raider_menu() -> InlineKeyboardMarkup:
        """Raider submenu"""
        keyboard = [
            [InlineKeyboardButton(text="➕ Add New Raider Rule", callback_data="auto_click:add_dynamic")],
            [InlineKeyboardButton(text="📋 Show All Rules", callback_data="auto_click:raider_list")],
            [InlineKeyboardButton(text="💬 Manage Replies", callback_data="dynamic_reply:menu")],
            [InlineKeyboardButton(text="🔙 Back to Auto-Tap", callback_data="auto_click:menu")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def raider_rules_list(rules: List[Dict], page: int = 1) -> InlineKeyboardMarkup:
        """List of raider rules (dynamic rules only) with pagination"""
        keyboard = []
        dynamic_rules = [r for r in rules if r.get('rule_type') == 'dynamic']

        # Pagination
        items_per_page = 9
        total_pages = max(1, (len(dynamic_rules) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_rules = dynamic_rules[start_idx:end_idx]

        for rule in page_rules:
            status = "✅" if rule['enabled'] else "❌"
            rule_name = rule.get('name')

            if rule_name:
                text = f"{status} 🔄 {rule_name}"
            else:
                text = f"{status} 🔄 Chat: {rule['target_chat_id']}, User: {rule.get('user_id', 'N/A')}"

            keyboard.append([
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"auto_click:view:{rule['id']}"
                )
            ])

        if not keyboard:
            keyboard.append([InlineKeyboardButton(text="No raider rules yet", callback_data="auto_click:raider_menu")])

        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(text="« Prev", callback_data=f"auto_click:raider_list:{page-1}"))
            nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(text="Next »", callback_data=f"auto_click:raider_list:{page+1}"))
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(text="🔙 Back to Raider Menu", callback_data="auto_click:raider_menu")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def auto_click_rule_details(rule: Dict) -> InlineKeyboardMarkup:
        """Auto click rule details menu"""
        rule_id = rule['id']
        rule_type = rule.get('rule_type', 'static')

        keyboard = [
            [InlineKeyboardButton(
                text="🔴 Disable" if rule['enabled'] else "🟢 Enable",
                callback_data=f"auto_click:toggle:{rule_id}"
            )],
            [InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"auto_click:edit_name:{rule_id}")],
        ]

        if rule_type == 'dynamic':
            # Auto-reply toggle
            auto_reply_enabled = rule.get('auto_reply_enabled', False)
            keyboard.append([InlineKeyboardButton(
                text=f"💬 Auto-Reply: {'ON' if auto_reply_enabled else 'OFF'}",
                callback_data=f"auto_click:toggle_reply:{rule_id}"
            )])

            # Ticker edit button
            keyboard.append([InlineKeyboardButton(
                text="🏷 Edit Ticker",
                callback_data=f"auto_click:edit_ticker:{rule_id}"
            )])

            keyboard.extend([
                [InlineKeyboardButton(text="✏️ Edit Monitored User", callback_data=f"auto_click:edit_user:{rule_id}")],
                [InlineKeyboardButton(text="✏️ Edit Button Texts", callback_data=f"auto_click:edit_buttons:{rule_id}")],
                [InlineKeyboardButton(text="✏️ Edit Clicking Bots", callback_data=f"auto_click:edit_userbots:{rule_id}")],
            ])

        # Back button depends on rule type
        if rule_type == 'dynamic':
            back_callback = "auto_click:raider_list"
            back_text = "🔙 Back to Rules"
        else:
            back_callback = "auto_click:scanning_list"
            back_text = "🔙 Back to Rules"

        keyboard.extend([
            [InlineKeyboardButton(text="🗑️ Delete Rule", callback_data=f"auto_click:delete:{rule_id}")],
            [InlineKeyboardButton(text=back_text, callback_data=back_callback)]
        ])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def dynamic_click_select_userbot_keyboard(userbots: List[Dict], selected_ids: List[int] = []) -> InlineKeyboardMarkup:
        """Userbot selection for dynamic click rule (multi-select)"""
        keyboard = []
        for bot in userbots:
            display_name = bot.get('display_name') or bot['session_name']
            is_selected = bot['id'] in selected_ids
            
            button_text = f"{'✅' if is_selected else '👤'} {display_name}"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"auto_click_dynamic_wizard:toggle_userbot:{bot['id']}"
                )
            ])
        
        # Add Done button only if at least one userbot is selected
        if selected_ids:
            keyboard.append([
                InlineKeyboardButton(text="✅ Done", callback_data="auto_click_dynamic_wizard:userbots_done")
            ])

        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="auto_click:list")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def dynamic_reply_menu() -> InlineKeyboardMarkup:
        """Dynamic Reply management menu"""
        keyboard = [
            [InlineKeyboardButton(text="➕ Add Reply", callback_data="dynamic_reply:add")],
            [InlineKeyboardButton(text="📋 List All Replies", callback_data="dynamic_reply:list")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu:auto_click")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def dynamic_reply_list(replies: List[Dict], usage_stats: Dict[int, int] = None, page: int = 1) -> InlineKeyboardMarkup:
        """
        Display list of all replies with delete buttons and pagination.
        usage_stats is optional {reply_id: use_count} for showing usage per rule.
        """
        keyboard = []

        # Pagination
        items_per_page = 9
        total_pages = max(1, (len(replies) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_replies = replies[start_idx:end_idx]

        for reply in page_replies:
            reply_id = reply['id']
            text = reply['message_text']
            use_count = usage_stats.get(reply_id, 0) if usage_stats else 0

            # Truncate text for display
            display_text = text[:50] + "..." if len(text) > 50 else text
            button_text = f"🗑 [{use_count} uses] {display_text}"

            keyboard.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"dynamic_reply:delete:{reply_id}"
            )])

        # Pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(text="« Prev", callback_data=f"dynamic_reply:list:{page-1}"))
            nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(text="Next »", callback_data=f"dynamic_reply:list:{page+1}"))
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="dynamic_reply:menu")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Settings main menu"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 Gain Alerts", callback_data="gain_alerts:menu")],
            [InlineKeyboardButton(text="🌙 Gain Alert Settings", callback_data="settings:gain_alerts")],
            [InlineKeyboardButton(text="📊 Token Status", callback_data="settings:token_status")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
        ])

    @staticmethod
    def gain_alert_settings_menu(
        gain_threshold: float,
        drop_threshold: float,
        drop_floor: float,
        chart_group_count: int,
        chart_threshold_label: str,
        chart_bot_label: str,
        guardrail_labels: Dict[str, str],
    ) -> InlineKeyboardMarkup:
        """Gain alert settings menu with current values"""
        keyboard = [
            [InlineKeyboardButton(
                text=f"📈 Gain Threshold: {gain_threshold*100:.0f}%",
                callback_data="settings:edit_gain_threshold"
            )],
            [InlineKeyboardButton(
                text=f"📉 Drop Threshold: {drop_threshold*100:.0f}%",
                callback_data="settings:edit_drop_threshold"
            )],
            [InlineKeyboardButton(
                text=f"💰 Minimum MC: ${drop_floor:,.0f}",
                callback_data="settings:edit_drop_floor"
            )],
            [InlineKeyboardButton(
                text=f"💰 Set MC Threshold ({chart_threshold_label})",
                callback_data="settings:edit_chart_threshold"
            )],
            [InlineKeyboardButton(
                text=f"🤖 Set Chart Bot ID ({chart_bot_label})",
                callback_data="settings:edit_chart_bot"
            )],
            [
                InlineKeyboardButton(
                    text=f"Age: {guardrail_labels['min_age_minutes']}",
                    callback_data="settings:edit_guardrail:min_age_minutes"
                ),
                InlineKeyboardButton(
                    text=f"Liq: {guardrail_labels['min_liquidity_usd']}",
                    callback_data="settings:edit_guardrail:min_liquidity_usd"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"Vol: {guardrail_labels['min_volume_usd']}",
                    callback_data="settings:edit_guardrail:min_volume_usd"
                ),
                InlineKeyboardButton(
                    text=f"MC x: {guardrail_labels['min_multiplier']}",
                    callback_data="settings:edit_guardrail:min_multiplier"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"Price Δ: {guardrail_labels['max_price_change_pct']}",
                    callback_data="settings:edit_guardrail:max_price_change_pct"
                ),
                InlineKeyboardButton(
                    text=f"Strat: {guardrail_labels['checks_required']}",
                    callback_data="settings:edit_guardrail:checks_required"
                ),
            ],
            [InlineKeyboardButton(
                text="📝 Edit Alert Template",
                callback_data="settings:edit_gain_template"
            )],
            [InlineKeyboardButton(
                text=f"⚙️ Chart Request Groups ({chart_group_count})",
                callback_data="gain_alerts:chart_groups:menu"
            )],
            [InlineKeyboardButton(text="🔙 Back", callback_data="settings:main")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def token_status_menu() -> InlineKeyboardMarkup:
        """Token status menu"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Scheduler Overview", callback_data="settings:scheduler_overview")],
            [InlineKeyboardButton(text="🪙 Active Tokens", callback_data="settings:tokens_list:active:1")],
            [InlineKeyboardButton(text="⛔ Stopped Tokens", callback_data="settings:tokens_list:stopped:1")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="settings:main")]
        ])

    @staticmethod
    def gain_alerts_main_menu(entries: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """Main menu for gain alerts monitored sources."""
        keyboard: List[List[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text="➕ Add Monitored Source", callback_data="gain_alerts:add")]
        ]

        for entry in entries:
            chat_id = entry.get("chat_id")
            button_text = entry.get("button_text") or f"{chat_id}"
            keyboard.append([
                InlineKeyboardButton(text=button_text, callback_data=f"gain_alerts:view:{chat_id}")
            ])

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="settings:main")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def gain_alerts_type_selector() -> InlineKeyboardMarkup:
        """Type selection keyboard for monitored sources."""
        keyboard = [
            [InlineKeyboardButton(text="📢 Channel", callback_data="gain_alerts:add:type:channel")],
            [InlineKeyboardButton(text="👥 Group", callback_data="gain_alerts:add:type:group")],
            [InlineKeyboardButton(text="💬 DM", callback_data="gain_alerts:add:type:dm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:cancel")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def gain_alerts_add_confirm() -> InlineKeyboardMarkup:
        """Confirmation keyboard for adding monitored sources."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data="gain_alerts:add:confirm")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:cancel")]
        ])

    @staticmethod
    def chart_groups_menu(groups: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """Chart request groups menu."""
        keyboard: List[List[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text="➕ Add Group", callback_data="gain_alerts:chart_groups:add")]
        ]

        for group in groups:
            chat_id = group.get("chat_id")
            label = group.get("label")
            if label:
                button_text = f"🗑️ Remove {chat_id} ({label})"
            else:
                button_text = f"🗑️ Remove {chat_id}"

            keyboard.append([
                InlineKeyboardButton(text=button_text, callback_data=f"gain_alerts:chart_groups:remove:{chat_id}")
            ])

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="gain_alerts:menu")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def token_list_navigation(status: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
        """Token list with pagination"""
        keyboard = []

        # Pagination
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"settings:tokens_list:{status}:{page-1}"))
            nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"settings:tokens_list:{status}:{page+1}"))
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="settings:token_status")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def blockchain_selector(current_chains: List[str], rule_id: int = None, context: str = "routing") -> InlineKeyboardMarkup:
        """Blockchain selection keyboard for routing rules

        Args:
            current_chains: List of currently selected blockchains (e.g., ["SOL", "BNB"])
            rule_id: ID of the rule being edited (None for new rule creation)
            context: Context for callbacks ("routing" or "curated")
        """
        sol_check = "✅" if "SOL" in current_chains else "☐"
        bnb_check = "✅" if "BNB" in current_chains else "☐"

        # Build callback prefix based on context
        if rule_id is not None:
            callback_prefix = f"{context}:blockchain"
            confirm_callback = f"{context}:blockchain_confirm:{rule_id}"
            back_callback = f"{context}:view:{rule_id}"
        else:
            callback_prefix = f"{context}:blockchain"
            confirm_callback = f"{context}:blockchain_confirm:new"
            back_callback = f"{context}:cancel"

        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🟣 Solana {sol_check}",
                    callback_data=f"{callback_prefix}:toggle_sol:{rule_id or 'new'}"
                ),
                InlineKeyboardButton(
                    text=f"🟡 BNB {bnb_check}",
                    callback_data=f"{callback_prefix}:toggle_bnb:{rule_id or 'new'}"
                )
            ],
            [
                InlineKeyboardButton(text="◀️ Back", callback_data=back_callback),
                InlineKeyboardButton(text="✅ Confirm", callback_data=confirm_callback)
            ]
        ])
