import logging
import sys

def setup_logging():
    """Configures logging to file and console."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File handler
    file_handler = logging.FileHandler('app.log', mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Add new handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Redirect print to logging
    def logger_print(*args, **kwargs):
        logging.info(' '.join(map(str, args)))

    # Replace built-in print
    __builtins__['print'] = logger_print

    logging.info("Logging configured. Print statements are now logged.")
