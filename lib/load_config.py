import os
from dotenv import load_dotenv


def load_env():
    """Ładuje konfigurację środowiska z pliku ``.env``.

    Returns:
        dict: Słownik z kluczami niezbędnymi do połączenia z bazą lokalną oraz
            ustawieniami aplikacji.

    Raises:
        ValueError: Gdy brakuje obowiązkowych zmiennych środowiskowych.
    """

    load_dotenv()

    config = {
        'DB_LOCAL_HOST': os.getenv('DB_LOCAL_HOST', '127.0.0.1'),
        'DB_LOCAL_PORT': int(os.getenv('DB_LOCAL_PORT', 3306)),
        'DB_LOCAL_USER': os.getenv('DB_LOCAL_USER'),
        'DB_LOCAL_PASSWORD': os.getenv('DB_LOCAL_PASSWORD'),
        'DB_LOCAL_NAME': os.getenv('DB_LOCAL_NAME'),
        'BATCH_SIZE': int(os.getenv('BATCH_SIZE', 500)),
        'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
        'LOG_FORMAT': os.getenv('LOG_FORMAT', '[%(asctime)s] %(levelname)s: %(message)s'),
        'LOG_SQL_QUERIES': os.getenv('LOG_SQL_QUERIES', 'false').lower() == 'true'
    }

    missing = [key for key in (
        'DB_LOCAL_USER',
        'DB_LOCAL_PASSWORD',
        'DB_LOCAL_NAME',
    ) if not config[key]]

    if missing:
        raise ValueError(
            'Brak wymaganych zmiennych środowiskowych: ' + ', '.join(missing)
        )

    return config
