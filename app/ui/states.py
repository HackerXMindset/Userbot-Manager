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
    target_edit_alert_mode = State()
    target_edit_sensitivity = State()
    target_edit_thresholds = State()
    
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

    # Command Forwarding
    cmd_fwd_add_rule_source_group = State()
    cmd_fwd_add_rule_command = State()
    cmd_fwd_add_rule_monitored_users = State()
    cmd_fwd_add_rule_forwarding_bot = State()
    cmd_fwd_add_rule_destination = State()
    cmd_fwd_add_rule_replying_users = State()
    cmd_fwd_add_rule_schedule = State()
    cmd_fwd_add_rule_custom_interval = State()
    cmd_fwd_add_rule_summary = State()
    cmd_fwd_add_monitored_user_id = State()
    cmd_fwd_add_replying_user_id = State()
    cmd_fwd_edit_command = State()
    cmd_fwd_schedule_settings = State()

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
    curate_alpha_set_min_mentions = State()
    curate_alpha_set_time_window = State()
    curate_alpha_edit_field = State()

    # Template Management
    template_add_name = State()
    template_add_text = State()
    template_edit_name = State()
    template_edit_text = State()
    template_assign_select_groups = State()
    
    
