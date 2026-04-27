import logging
import logging.handlers
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Get logging configuration from environment variables
LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
LOG_DIR = os.getenv("LOG_DIR", os.path.join(BASE_DIR, "logs"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))


def cleanup_old_logs():
    """Delete log files older than LOG_RETENTION_DAYS"""
    if not os.path.exists(LOG_DIR):
        return
    
    cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    deleted_count = 0
    
    # Walk through all subdirectories in the log directory
    for root, _dirs, files in os.walk(LOG_DIR):
        for filename in files:
            # Match both .log files and rotated files like .log.2025-10-17
            if '.log' not in filename:
                continue
                
            filepath = os.path.join(root, filename)
            try:
                # Get the file's modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                # Delete if older than retention period
                if file_mtime < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1
            except (OSError, IOError):
                # Skip files that can't be accessed
                pass
    
    if deleted_count > 0:
        print(f"[Logger] Cleaned up {deleted_count} old log file(s) older than {LOG_RETENTION_DAYS} days")

def rotate_log_if_needed(log_file):
    """
    Check if the log file exists and is from a previous day.
    If so, rotate it manually before the handler takes over.
    This handles cases where the bot wasn't running at midnight.
    """
    if not os.path.exists(log_file):
        return
    
    try:
        # Get the file's modification date
        file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
        file_date = file_mtime.date()
        today = datetime.now().date()
        
        # If the file is from a previous day, rotate it
        if file_date < today:
            # Create the rotated filename with the file's date
            rotated_name = f"{log_file}.{file_date.strftime('%Y-%m-%d')}"
            
            # Don't overwrite if rotated file already exists
            if not os.path.exists(rotated_name):
                os.rename(log_file, rotated_name)
                print(f"[Logger] Rotated previous log: {os.path.basename(log_file)} -> {os.path.basename(rotated_name)}")
            else:
                # If rotated file exists, just remove the old log to avoid duplicates
                os.remove(log_file)
    except (OSError, IOError):
        # If we can't rotate, just continue - the handler will append to the existing file
        pass


def setup_logger(name, log_file, level=LOG_LEVEL, console_output=True):
    """Set up a logger with file rotation and optional console output"""
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Rotate the log file if it's from a previous day (handles bot not running at midnight)
    rotate_log_if_needed(log_file)
    
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
    log_file = os.path.join(LOG_DIR, "bot", "bot.log")
    return setup_logger("TTS-Bot", log_file, console_output=True)

def get_tts_server_logger():
    """Get the TTS server logger with file output only"""
    log_file = os.path.join(LOG_DIR, "tts_server", "tts-server.log")
    return setup_logger("TTS-Server", log_file, console_output=False)

# Clean up old log files on startup
cleanup_old_logs()

# Initialize loggers
bot_logger = get_bot_logger()
tts_server_logger = get_tts_server_logger()
