import os
from dotenv import load_dotenv

def load_env():
    """Ładuje zmienne z pliku .env do słownika"""
    load_dotenv()
    config = {
        'DB_LOCAL_HOST': os.getenv('DB_LOCAL_HOST'),
        'DB_LOCAL_PORT': int(os.getenv('DB_LOCAL_PORT', 3306)),
        'DB_LOCAL_USER': os.getenv('DB_LOCAL_USER'),
        'DB_LOCAL_PASSWORD': os.getenv('DB_LOCAL_PASSWORD'),
        'DB_LOCAL_NAME': os.getenv('DB_LOCAL_NAME'),
        'BATCH_SIZE': int(os.getenv('BATCH_SIZE', 500)),
        'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
        'LOG_FORMAT': os.getenv('LOG_FORMAT', '[%(asctime)s] %(levelname)s: %(message)s'),
        'LOG_SQL_QUERIES': os.getenv('LOG_SQL_QUERIES', 'false').lower() == 'true'
    }
    return config
