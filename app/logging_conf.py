import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Setup logging configuration for the application"""
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        fmt='%(levelname)s - %(name)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    configure_library_loggers()
    
    logging.info(f"Logging configured - Level: {log_level}, File: {log_file or 'Console only'}")

def configure_library_loggers():
    """Configure logging levels for third-party libraries"""
    
    # Reduce noise from libraries
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiogram').setLevel(logging.INFO)
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('asyncpg').setLevel(logging.WARNING)
    
    # Keep our application loggers at INFO
    logging.getLogger('app').setLevel(logging.INFO)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name"""
    return logging.getLogger(name)

class ContextFilter(logging.Filter):
    """Add context information to log records"""
    
    def __init__(self, context: dict = None):
        super().__init__()
        self.context = context or {}
    
    def filter(self, record):
        for key, value in self.context.items():
            setattr(record, key, value)
        return True

class TimedRotatingHandler(logging.Handler):
    """Custom handler for timed log rotation"""
    
    def __init__(self, base_filename: str, when: str = 'midnight', interval: int = 1):
        super().__init__()
        self.base_filename = base_filename
        self.when = when
        self.interval = interval
        self.current_handler = None
        self._setup_handler()
    
    def _setup_handler(self):
        """Setup the current file handler"""
        from logging.handlers import TimedRotatingFileHandler
        
        self.current_handler = TimedRotatingFileHandler(
            self.base_filename,
            when=self.when,
            interval=self.interval,
            backupCount=7,  # Keep 7 days of logs
            encoding='utf-8'
        )
        
        # Set formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.current_handler.setFormatter(formatter)
    
    def emit(self, record):
        """Emit a log record"""
        if self.current_handler:
            self.current_handler.emit(record)

# Performance logging utilities
class PerformanceLogger:
    """Logger for performance metrics"""
    
    def __init__(self, name: str = 'performance'):
        self.logger = logging.getLogger(name)
    
    def log_execution_time(self, operation: str, duration: float, **kwargs):
        """Log execution time for an operation"""
        extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.info(f"PERF: {operation} took {duration:.3f}s {extra_info}")
    
    def log_database_query(self, query_type: str, duration: float, rows: int = None):
        """Log database query performance"""
        rows_info = f"rows={rows}" if rows is not None else ""
        self.logger.info(f"DB: {query_type} took {duration:.3f}s {rows_info}")
    
    def log_api_call(self, endpoint: str, duration: float, status_code: int = None):
        """Log API call performance"""
        status_info = f"status={status_code}" if status_code else ""
        self.logger.info(f"API: {endpoint} took {duration:.3f}s {status_info}")

# Security logging
class SecurityLogger:
    """Logger for security events"""
    
    def __init__(self, name: str = 'security'):
        self.logger = logging.getLogger(name)
    
    def log_auth_attempt(self, user_id: int, success: bool, source: str = None):
        """Log authentication attempt"""
        result = "SUCCESS" if success else "FAILED"
        source_info = f"from={source}" if source else ""
        self.logger.warning(f"AUTH: {result} user_id={user_id} {source_info}")
    
    def log_permission_denied(self, user_id: int, action: str, resource: str = None):
        """Log permission denied events"""
        resource_info = f"resource={resource}" if resource else ""
        self.logger.warning(f"PERM_DENIED: user_id={user_id} action={action} {resource_info}")
    
    def log_suspicious_activity(self, user_id: int, activity: str, details: dict = None):
        """Log suspicious activity"""
        details_str = " ".join([f"{k}={v}" for k, v in (details or {}).items()])
        self.logger.error(f"SUSPICIOUS: user_id={user_id} activity={activity} {details_str}")

# System health logging
class HealthLogger:
    """Logger for system health metrics"""
    
    def __init__(self, name: str = 'health'):
        self.logger = logging.getLogger(name)
    
    def log_service_status(self, service: str, status: str, details: dict = None):
        """Log service status change"""
        details_str = " ".join([f"{k}={v}" for k, v in (details or {}).items()])
        self.logger.info(f"SERVICE: {service} status={status} {details_str}")
    
    def log_resource_usage(self, resource: str, usage: float, threshold: float = None):
        """Log resource usage"""
        threshold_info = f"threshold={threshold}" if threshold else ""
        level = logging.WARNING if threshold and usage > threshold else logging.INFO
        self.logger.log(level, f"RESOURCE: {resource} usage={usage:.2f} {threshold_info}")
    
    def log_error_rate(self, component: str, error_count: int, total_count: int):
        """Log error rate for a component"""
        error_rate = (error_count / total_count * 100) if total_count > 0 else 0
        level = logging.WARNING if error_rate > 5 else logging.INFO
        self.logger.log(level, f"ERROR_RATE: {component} {error_count}/{total_count} ({error_rate:.1f}%)")

# Initialize default loggers
performance_logger = PerformanceLogger()
security_logger = SecurityLogger()
health_logger = HealthLogger()