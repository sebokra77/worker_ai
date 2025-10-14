#!/usr/bin/env python3
import sys
from lib.load_config import load_env
from lib.db_utils import setup_logger
from lib.db_local import connect_local
from lib.db_remote import connect_remote
from lib.task import get_next_task, get_remote_db_params

def main():
    # Załaduj konfigurację i logger
    cfg = load_env()
    logger = setup_logger('sync', 'logs/sync.log')

    logger.info("=== Rozpoczęcie synchronizacji ===")

    # Połączenie z bazą lokalną
    conn_local = connect_local(cfg)
    if not conn_local:
        logger.error("Nie udało się połączyć z bazą lokalną.")
        sys.exit(1)

    cursor_local = conn_local.cursor(dictionary=True)

    # Pobierz zadanie do wykonania
    task = get_next_task(cursor_local)
    if not task:
        logger.info("Brak zadań do synchronizacji.")
        return

    logger.info(f"Pobrano zadanie ID={task['id_task']} z bazy {task['id_database']}")

    # Pobierz parametry połączenia z bazy zewnętrznej
    remote_params = get_remote_db_params(cursor_local, task['id_database'])
    if not remote_params:
        logger.error(f"Nie znaleziono konfiguracji bazy zewnętrznej ID={task['id_database']}")
        return

    # Nawiąż połączenie z bazą zewnętrzną
    conn_remote = connect_remote(remote_params)
    logger.info(f"Nawiązano połączenie z bazą zewnętrzną typu: {remote_params['db_type']}")

    # Tutaj można dodać dalszą logikę synchronizacji (compare/update)
    # np. import z lib.task_item

    logger.info("Synchronizacja zakończona.")
    conn_local.close()
    conn_remote.close()

if __name__ == "__main__":
    main()
