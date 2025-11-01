import sys

from loguru import logger


def setup_logging():
    # Remove default logger
    logger.remove()

    # Define log format with colors
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    # Add console handler with colorization
    logger.add(
        sys.stderr,
        format=log_format,
        level="INFO",
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Add file handler for all logs (without colors)
    log_file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} - "
        "{message}"
    )

    logger.add(
        "logs/app.log",
        format=log_file_format,
        level="DEBUG",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        colorize=False,
    )

    # Add separate error log file
    logger.add(
        "logs/error.log",
        format=log_file_format,
        level="ERROR",
        rotation="50 MB",
        retention="60 days",
        compression="zip",
        colorize=False,
    )
    return logger


def get_logger():
    return logger
