from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class Keyboards:
    """All inline keyboards for the management bot"""
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Main menu keyboard"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🧾 Overview", callback_data="menu:status"),
                InlineKeyboardButton(text="📈 Tracking", callback_data="menu:tracking")
            ],
            [
                InlineKeyboardButton(text="👥 Groups", callback_data="menu:groups"),
                InlineKeyboardButton(text="👤 Agents", callback_data="menu:userbots")
            ],
            [
                InlineKeyboardButton(text="📡 Sources", callback_data="menu:sources"),
                InlineKeyboardButton(text="🚨 Alerts", callback_data="menu:alerts")
            ],
            [
                InlineKeyboardButton(text="💹 Profit Logs", callback_data="menu:pnl"),
                InlineKeyboardButton(text="📬 Inbox", callback_data="menu:notifications"),
            ],
            [
                InlineKeyboardButton(text="✨ Curate Alpha", callback_data="menu:curate_alpha"),
                InlineKeyboardButton(text="📡 Auto-Tap", callback_data="menu:auto_click")
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
    @staticmethod
    def auto_click_menu(rules: List[Dict]) -> InlineKeyboardMarkup:
        """Auto click management menu"""
        keyboard = []
        for rule in rules:
            status = "✅" if rule['enabled'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} Chat: {rule['target_chat_id']}, Bot: {rule['bot_id']}",
                    callback_data=f"auto_click:view:{rule['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="➕ Add New Rule", callback_data="auto_click:add")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def auto_click_rule_details(rule: Dict) -> InlineKeyboardMarkup:
        """Auto click rule details menu"""
        status_btn = InlineKeyboardButton(
            text="🔴 Disable" if rule['enabled'] else "🟢 Enable",
            callback_data=f"auto_click:toggle:{rule['id']}"
        )
        return InlineKeyboardMarkup(inline_keyboard=[
            [status_btn],
            [InlineKeyboardButton(text="🗑️ Delete Rule", callback_data=f"auto_click:delete:{rule['id']}")],
            [InlineKeyboardButton(text="🔙 Back to List", callback_data="auto_click:list")]
        ])
