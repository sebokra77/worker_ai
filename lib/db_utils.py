import logging
import os
import hashlib
from datetime import datetime

def setup_logger(name: str, log_file: str, level=logging.INFO):
    """Tworzy logger zapisujący dane do pliku"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Upewnij się, że istnieje katalog dla pliku z logami
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Utwórz plik jeżeli nie istnieje, aby obsłużyć scenariusz pierwszego uruchomienia
    if not os.path.exists(log_file):
        with open(log_file, 'a', encoding='utf-8'):
            pass

    # Unikaj duplikowania handlerów przy wielokrotnym wywołaniu setup_logger
    existing_handler = next(
        (
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
            and getattr(handler, 'baseFilename', None) == os.path.abspath(log_file)
        ),
        None,
    )

    if existing_handler is None:
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
