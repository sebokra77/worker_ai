import mysql.connector
from mysql.connector import Error


def connect_local(cfg):
    """Inicjuje połączenie TCP/IP z lokalną bazą MySQL.

    Args:
        cfg (dict): Dane konfiguracyjne z pliku ``.env``.

    Returns:
        mysql.connector.connection.MySQLConnection | None: Gotowe połączenie
        lub ``None`` gdy wystąpi błąd inicjalizacji.
    """

    try:
        connection_config = {
            'host': cfg['DB_LOCAL_HOST'],
            'user': cfg['DB_LOCAL_USER'],
            'password': cfg['DB_LOCAL_PASSWORD'],
            'database': cfg['DB_LOCAL_NAME'],
            'port': cfg['DB_LOCAL_PORT'],
            'unix_socket': None,
        }

        # Wymuszenie połączenia TCP/IP zamiast nazwanych potoków
        conn = mysql.connector.connect(**connection_config)
        return conn
    except Error as error:
        print(f"Błąd połączenia z bazą lokalną: {error}")
        return None
