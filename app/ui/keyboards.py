from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional, Dict, Any

class Keyboards:
    """All inline keyboards for the management bot"""
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Main menu keyboard"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Status", callback_data="menu:status"),
                InlineKeyboardButton(text="👥 Groups", callback_data="menu:groups")
            ],
            [
                InlineKeyboardButton(text="📅 Schedules", callback_data="menu:schedules"),
                InlineKeyboardButton(text="📦 Quotas", callback_data="menu:quotas")
            ],
            [
                InlineKeyboardButton(text="🤖 Userbots", callback_data="menu:userbots"),
                InlineKeyboardButton(text="🎯 Targets", callback_data="menu:targets")
            ],
            [
                InlineKeyboardButton(text="📡 Sources", callback_data="menu:sources")
            ],
            [
                InlineKeyboardButton(text="🚨 Alerts", callback_data="menu:alerts")
            ],
            [
                InlineKeyboardButton(text="📈 Tracking", callback_data="menu:tracking"),
                InlineKeyboardButton(text="⚙️ Settings", callback_data="menu:settings")
            ],
            [
                InlineKeyboardButton(text="❌ Close", callback_data="menu:close")
            ]
        ])
    
    @staticmethod
    def groups_menu(groups: List[Dict]) -> InlineKeyboardMarkup:
        """Groups management menu"""
        keyboard = []
        
        for group in groups[:10]:  # Limit to 10 for UI
            status = "✅" if group['enabled'] else "❌"
            title = group['title'][:20] if group['title'] else f"ID: {group['tg_chat_id']}"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {title}",
                    callback_data=f"group:view:{group['id']}"
                )
            ])
        
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
                InlineKeyboardButton(text="📅 Schedules", callback_data=f"group:schedules:{group['id']}"),
                InlineKeyboardButton(text="🎯 Targets", callback_data=f"group:targets:{group['id']}")
            ],
            [
                InlineKeyboardButton(text="📦 Set Quota", callback_data=f"group:quota:{group['id']}"),
                InlineKeyboardButton(text="⏱ Set Cooldown", callback_data=f"group:cooldown:{group['id']}")
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
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"group:schedules:{group_id}")
                ]
            ])
        
        return InlineKeyboardMarkup(inline_keyboard=[])
    
    @staticmethod
    def userbots_menu(userbots: List[Dict]) -> InlineKeyboardMarkup:
        """Userbots management menu"""
        keyboard = []
        
        for bot in userbots[:8]:
            status_icon = "🟢" if bot['status'] == 'active' else "🔴"
            name = bot['session_name'][:20]
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} {name}",
                    callback_data=f"userbot:view:{bot['id']}"
                )
            ])
        
        keyboard.extend([
            [
                InlineKeyboardButton(text="➕ Add Userbot", callback_data="userbot:add"),
                InlineKeyboardButton(text="🔄 Check Health", callback_data="userbot:health")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
            ]
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    @staticmethod
    def alerts_config(current_gains: List[int], drop_pct: float) -> InlineKeyboardMarkup:
        """Alerts configuration menu"""
        gains_text = ", ".join([f"{g}x" for g in current_gains])
        
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📈 Gains: {gains_text}", callback_data="alerts:gains")],
            [InlineKeyboardButton(text=f"📉 Drop: {drop_pct*100:.0f}%", callback_data="alerts:drop")],
            [
                InlineKeyboardButton(text="➕ Add Gain", callback_data="alerts:add_gain"),
                InlineKeyboardButton(text="➖ Remove Gain", callback_data="alerts:remove_gain")
            ],
            [
                InlineKeyboardButton(text="🔄 Set Drop %", callback_data="alerts:set_drop"),
                InlineKeyboardButton(text="⚙️ Per-Group", callback_data="alerts:per_group")
            ],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
        ])
    
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
        buttons = []
        
        if page > 1:
            buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:page:{page-1}"))
        
        buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{prefix}:page:info"))
        
        if page < total_pages:
            buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:page:{page+1}"))
        
        return buttons