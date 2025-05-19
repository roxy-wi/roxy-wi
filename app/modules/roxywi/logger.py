import logging
import json
import os
import sys
from typing import Any, Optional
from datetime import datetime

from flask import request, has_request_context

# Define log levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

# Global logger instance
_logger = None


class StructuredLogFormatter(logging.Formatter):
    """
    Custom formatter for structured logging.
    Outputs logs in JSON format for better parsing by log analysis tools.
    """
    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as a JSON string.

        Args:
            record: The log record to format

        Returns:
            A JSON string representation of the log record
        """
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
        }

        # Add exception info if available
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }

        # Add request context if available
        if has_request_context():
            log_data['request'] = {
                'method': request.method,
                'path': request.path,
                'ip': request.remote_addr,
            }

        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key.startswith('_') and not key.startswith('__'):
                clean_key = key[1:]  # Remove the leading underscore
                log_data[clean_key] = value

        return json.dumps(log_data)


def setup_logger(
    log_path: str = '/var/log/roxy-wi',
    log_file: str = 'roxy-wi.log',
    log_level: int = logging.INFO,
    console_logging: bool = False
) -> logging.Logger:
    """
    Set up the logger with the specified configuration.

    Args:
        log_path: The directory where log files will be stored
        log_file: The name of the log file
        log_level: The minimum log level to record
        console_logging: Whether to also log to the console

    Returns:
        The configured logger instance
    """
    global _logger

    if _logger is not None:
        return _logger

    # Create logger
    logger = logging.getLogger('roxy-wi')
    logger.setLevel(log_level)
    logger.propagate = False

    # Create log directory if it doesn't exist
    os.makedirs(log_path, exist_ok=True)

    # Create file handler
    file_handler = logging.FileHandler(os.path.join(log_path, log_file))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(StructuredLogFormatter())
    logger.addHandler(file_handler)

    # Add console handler if requested
    if console_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """
    Get the configured logger instance.
    If the logger hasn't been set up yet, set it up with default configuration.
    
    Returns:
        The configured logger instance
    """
    global _logger

    if _logger is None:
        _logger = setup_logger()

    return _logger


def log(
    level: int,
    message: str,
    server_ip: Optional[str] = None,
    user_id: Optional[int] = None,
    service: Optional[str] = None,
    exception: Optional[Exception] = None,
    **kwargs: Any
) -> None:
    """
    Log a message with the specified level and additional context.

    Args:
        level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: The log message
        server_ip: The IP of the server related to the log message
        user_id: The ID of the user related to the log message
        service: The service related to the log message
        exception: An exception to include in the log
        **kwargs: Additional fields to include in the log
    """
    logger = get_logger()

    # Add extra fields with underscore prefix to avoid conflicts
    extra = {f'_{k}': v for k, v in kwargs.items()}

    if server_ip:
        extra['_server_ip'] = server_ip
    if user_id:
        extra['_user_id'] = user_id
    if service:
        extra['_service'] = service

    # Create a LogRecord with the extra fields
    if exception:
        logger.log(level, message, extra=extra, exc_info=exception)
    else:
        logger.log(level, message, extra=extra)


def debug(message: str, **kwargs: Any) -> None:
    """Log a DEBUG level message."""
    log(DEBUG, message, **kwargs)


def info(message: str, **kwargs: Any) -> None:
    """Log an INFO level message."""
    log(INFO, message, **kwargs)


def warning(message: str, **kwargs: Any) -> None:
    """Log a WARNING level message."""
    log(WARNING, message, **kwargs)


def error(message: str, **kwargs: Any) -> None:
    """Log an ERROR level message."""
    log(ERROR, message, **kwargs)


def critical(message: str, **kwargs: Any) -> None:
    """Log a CRITICAL level message."""
    log(CRITICAL, message, **kwargs)


def exception(message: str, exc: Optional[Exception] = None, **kwargs: Any) -> None:
    """
    Log an exception with ERROR level.
    If exc is not provided, the current exception from sys.exc_info() will be used.
    """
    log(ERROR, message, exception=exc, **kwargs)
