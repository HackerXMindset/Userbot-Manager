from aiogram.fsm.state import State, StatesGroup

class ManagementStates(StatesGroup):
    """FSM states for management bot"""
    
    # Group management
    adding_group = State()
    setting_quota = State()
    setting_cooldown = State()
    
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
    
    # Alerts
    adding_gain_threshold = State()
    setting_drop_percentage = State()
    custom_drop_input = State()
    
    # Targets
    adding_target = State()
    
    # Sources
    adding_source_chat_id = State()
    adding_source_user_id = State()
    
    
