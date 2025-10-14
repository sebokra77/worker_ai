import logging
import hashlib
from datetime import datetime

def setup_logger(name: str, log_file: str, level=logging.INFO):
    """Tworzy logger zapisujący dane do pliku"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def hash_text(text: str) -> str:
    """Zwraca SHA256 dla podanego tekstu"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def now_str() -> str:
    """Zwraca aktualny czas w formacie ISO"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
