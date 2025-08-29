"""
Telegram Bot Management System

A sophisticated management bot + userbot workers system for monitoring 
Telegram groups and forwarding Solana addresses with advanced scheduling, 
quotas, and alerts.
"""

__version__ = "1.0.0"
__author__ = "Telegram Bot System"

from .config import settings
from .db import db

__all__ = ["settings", "db"]