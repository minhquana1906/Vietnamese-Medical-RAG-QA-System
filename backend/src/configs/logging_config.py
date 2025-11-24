import sys

from loguru import logger

from .setup import get_backend_settings

settings = get_backend_settings()


def configure_logging(log_level: str = "INFO", json_logs: bool = False):
    logger.remove()

    if json_logs:
        logger.add(
            sys.stderr,
            format="{message}",
            level=log_level,
            serialize=True,
            backtrace=True,
            diagnose=True,
        )

        logger.add(
            "logs/app.log",
            format="{message}",
            level=log_level,
            serialize=True,
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            backtrace=True,
            diagnose=True,
        )
    else:
        # Colorized format for development
        # Color codes:
        # <green>: timestamps
        # <level>: auto-colored by level (DEBUG=blue, INFO=white, WARNING=yellow, ERROR=red, CRITICAL=bold red)
        # <cyan>: module/function/line info
        # <blue>: alternative highlight color
        # <yellow>: warnings
        # <red>: errors
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=log_level,
            backtrace=True,
            diagnose=True,
            colorize=True,
        )

        # logger.add(
        #     "logs/app.log",
        #     format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        #     level=log_level,
        #     rotation="50 MB",
        #     retention="14 days",
        # )

    logger.info(f"Logging configured with level={log_level}, json_logs={json_logs}")


def get_logger():
    return logger


configure_logging(
    log_level=settings.log_level or "INFO",
    json_logs=False,
)
