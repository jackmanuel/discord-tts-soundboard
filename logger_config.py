import logging
import logging.handlers
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get logging configuration from environment variables
LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))

def setup_logger(name, log_file, level=LOG_LEVEL, console_output=True):
    """Set up a logger with file rotation and optional console output"""
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with daily rotation (keep configured number of days)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler (if requested)
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

def get_bot_logger():
    """Get the bot logger with both file and console output"""
    log_file = os.path.join(LOG_DIR, "bot", f"bot-{datetime.now().strftime('%Y-%m-%d')}.log")
    return setup_logger("TTS-Bot", log_file, console_output=True)

def get_tts_server_logger():
    """Get the TTS server logger with file output only"""
    log_file = os.path.join(LOG_DIR, "tts_server", f"tts-server-{datetime.now().strftime('%Y-%m-%d')}.log")
    return setup_logger("TTS-Server", log_file, console_output=False)

# Initialize loggers
bot_logger = get_bot_logger()
tts_server_logger = get_tts_server_logger()