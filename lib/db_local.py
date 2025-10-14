import mysql.connector
from mysql.connector import Error

def connect_local(cfg):
    """Tworzy połączenie z bazą lokalną MySQL"""
    try:
        conn = mysql.connector.connect(
            host=cfg['DB_LOCAL_HOST'],
            user=cfg['DB_LOCAL_USER'],
            password=cfg['DB_LOCAL_PASSWORD'],
            database=cfg['DB_LOCAL_NAME'],
            port=cfg['DB_LOCAL_PORT']
        )
        return conn
    except Error as e:
        print(f"Błąd połączenia z bazą lokalną: {e}")
        return None
