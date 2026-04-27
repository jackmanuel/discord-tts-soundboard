import logging
import logging.handlers
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
LOG_DIR = os.getenv("LOG_DIR", os.path.join(BASE_DIR, "logs"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))


def cleanup_old_logs():
    """Delete log files older than LOG_RETENTION_DAYS"""
    if not os.path.exists(LOG_DIR):
        return
    
    cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    deleted_count = 0
    
    for root, _dirs, files in os.walk(LOG_DIR):
        for filename in files:
            if '.log' not in filename:
                continue
                
            filepath = os.path.join(root, filename)
            try:
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_mtime < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1
            except (OSError, IOError):
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
        file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
        file_date = file_mtime.date()
        today = datetime.now().date()
        
        if file_date < today:
            rotated_name = f"{log_file}.{file_date.strftime('%Y-%m-%d')}"
            
            if not os.path.exists(rotated_name):
                os.rename(log_file, rotated_name)
                print(f"[Logger] Rotated previous log: {os.path.basename(log_file)} -> {os.path.basename(rotated_name)}")
            else:
                os.remove(log_file)
    except (OSError, IOError):
        pass


def setup_logger(name, log_file, level=LOG_LEVEL, console_output=True):
    """Set up a logger with file rotation and optional console output"""
    
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    rotate_log_if_needed(log_file)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
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

cleanup_old_logs()

bot_logger = get_bot_logger()
tts_server_logger = get_tts_server_logger()
