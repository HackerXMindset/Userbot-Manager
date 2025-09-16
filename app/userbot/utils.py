"""
Userbot Utils - Shared utilities and helpers for userbot operations
"""

import re
import logging
from typing import List, Set, Tuple, Any, Optional
from collections import deque

from app.config import settings

logger = logging.getLogger(__name__)


class UserbotUtils:
    """Utility functions for userbot operations"""
    
    def __init__(self):
        # Solana address pattern
        self.solana_pattern = re.compile(settings.solana_pattern)
    
    def extract_solana_addresses(self, text: str) -> List[str]:
        """Extract Solana addresses from text"""
        if not text:
            return []
        
        matches = self.solana_pattern.findall(text)
        return list(set(matches))  # Remove duplicates
    
    def get_message_text(self, message) -> str:
        """Safely get message text as string"""
        if hasattr(message, 'text') and message.text:
            return str(message.text)
        return ""
    
    def get_user_name(self, sender) -> str:
        """Get user name from sender object"""
        if not sender:
            return "Unknown"
        
        if hasattr(sender, 'first_name'):
            name = sender.first_name or ""
            if hasattr(sender, 'last_name') and sender.last_name:
                name += f" {sender.last_name}"
            return name.strip() or "Unknown"
        
        if hasattr(sender, 'title'):
            return sender.title or "Unknown"
        
        if hasattr(sender, 'username') and sender.username:
            return f"@{sender.username}"
        
        return "Unknown"
    
    def get_chat_title(self, chat) -> str:
        """Get chat title from chat object"""
        if not chat:
            return "Unknown Chat"
        
        if hasattr(chat, 'title') and chat.title:
            return chat.title
        
        if hasattr(chat, 'first_name'):
            name = chat.first_name or ""
            if hasattr(chat, 'last_name') and chat.last_name:
                name += f" {chat.last_name}"
            return name.strip() or f"Chat {getattr(chat, 'id', 'Unknown')}"
        
        if hasattr(chat, 'username') and chat.username:
            return f"@{chat.username}"
        
        return f"Chat {getattr(chat, 'id', 'Unknown')}"


class MessageTracker:
    """Tracks sent messages for reply detection"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.sent_messages: Set[Tuple[int, int]] = set()  # (chat_id, message_id)
        self.message_queue = deque(maxlen=max_size)
    
    def track_message(self, chat_id: int, message_id: int):
        """Track a sent message"""
        message_key = (chat_id, message_id)
        
        # Add to set and queue
        self.sent_messages.add(message_key)
        self.message_queue.append(message_key)
        
        # Maintain size limit
        self._cleanup_old_messages()
        
        logger.debug(f"Tracked message: chat={chat_id}, msg_id={message_id}")
    
    def is_tracked_message(self, chat_id: int, message_id: int) -> bool:
        """Check if a message is being tracked"""
        return (chat_id, message_id) in self.sent_messages
    
    def _cleanup_old_messages(self):
        """Clean up old messages if we exceed max_size"""
        if len(self.sent_messages) > self.max_size:
            # Remove oldest messages that are not in the deque anymore
            current_messages = set(self.message_queue)
            messages_to_remove = self.sent_messages - current_messages
            
            for msg in messages_to_remove:
                self.sent_messages.discard(msg)
    
    def get_stats(self) -> dict:
        """Get tracker statistics"""
        return {
            'total_tracked': len(self.sent_messages),
            'max_size': self.max_size,
            'queue_size': len(self.message_queue)
        }


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls: int = 30, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
    
    def can_make_call(self) -> bool:
        """Check if we can make a call within rate limits"""
        import time
        now = time.time()
        
        # Remove old calls outside the time window
        while self.calls and self.calls[0] <= now - self.time_window:
            self.calls.popleft()
        
        return len(self.calls) < self.max_calls
    
    def record_call(self):
        """Record a call being made"""
        import time
        self.calls.append(time.time())
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        import time
        now = time.time()
        
        # Clean up old calls
        while self.calls and self.calls[0] <= now - self.time_window:
            self.calls.popleft()
        
        return {
            'calls_in_window': len(self.calls),
            'max_calls': self.max_calls,
            'time_window': self.time_window,
            'can_make_call': self.can_make_call()
        }


def format_token_address(address: str, length: int = 8) -> str:
    """Format token address for display"""
    if len(address) <= length * 2:
        return address
    return f"{address[:length]}...{address[-length:]}"


def validate_solana_address(address: str) -> bool:
    """Validate if a string is a valid Solana address format"""
    if not address or len(address) < 32:
        return False
    
    # Solana addresses are base58 encoded and typically 32-44 characters
    import re
    pattern = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
    return bool(pattern.match(address))


def safe_int_convert(value: Any, default: int = 0) -> int:
    """Safely convert a value to integer"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """Truncate text to maximum length"""
    if not text or len(text) <= max_length:
        return text or ""
    
    return text[:max_length - len(suffix)] + suffix

