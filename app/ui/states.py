from aiogram.fsm.state import State, StatesGroup

class ManagementStates(StatesGroup):
    """FSM states for management bot"""
    
    # Group management
    adding_group = State()
    setting_quota = State()
    setting_cooldown = State()
    group_set_name = State()
    
    # Schedule management
    setting_schedule_time = State()
    setting_schedule_window = State()
    custom_schedule_start_time = State()
    custom_schedule_end_time = State()
    custom_schedule_max_calls = State()
    
    # Userbot management
    userbot_login_phone = State()
    userbot_login_code = State()
    userbot_login_2fa = State()
    userbot_set_name = State()
    
    
    # Targets
    adding_target = State()
    
    # Sources
    adding_source_chat_id = State()
    adding_source_user_id = State()
    source_set_name = State()

    # PNL Forwarding
    pnl_waiting_for_source_forward = State()
    pnl_waiting_for_destination_forward = State()
    pnl_waiting_for_user_forward = State()
    pnl_add_rule_source_group = State()
    pnl_add_rule_monitored_users = State()
    pnl_add_rule_forwarding_bot = State()
    pnl_add_rule_destination = State()
    pnl_add_rule_replying_users = State()
    pnl_add_monitored_user_id = State()
    pnl_add_replying_user_id = State()
    pnl_add_rule_summary = State()

    # Notifications
    setting_notification_channel = State()
    adding_blacklist_user = State()

    # Auto Click
    adding_auto_click_rule_target = State()
    adding_auto_click_rule_bot_id = State()
    adding_auto_click_rule_button_text = State()

    # Curate Alpha
    curate_alpha_add_rule_name = State()
    curate_alpha_select_sources = State()
    curate_alpha_select_forwarding_bot = State()
    curate_alpha_set_destination = State()
    curate_alpha_set_time_window = State()
    curate_alpha_edit_field = State()
    
    
