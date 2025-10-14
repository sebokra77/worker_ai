#!/usr/bin/env python3
import sys
from lib.load_config import load_env
from lib.db_utils import setup_logger
from lib.db_local import connect_local
from lib.db_remote import connect_remote
from lib.task import get_next_task, get_remote_db_params
from lib.task_item import fetch_remote_batch

def main():
    # Załaduj konfigurację i logger
    try:
        print("Wczytywanie konfiguracji ",)
        cfg = load_env()
    except ValueError as error:
        print(f"Błąd konfiguracji środowiska w pliku .env: {error}")
        sys.exit(1)
    logger = setup_logger('sync', 'logs/sync.log')
    print("Łącznie z DB ...")
    logger.info("=== Rozpoczęcie synchronizacji ===")

    # Połączenie z bazą lokalną
    print("Łącznie z DB local ...", end="")
    conn_local = connect_local(cfg)
    if not conn_local:
        logger.error("Nie udało się połączyć z bazą lokalną.")
        print(" Error")
        sys.exit(1)
    print(" OK")
    
    cursor_local = conn_local.cursor(dictionary=True)

    # Pobierz zadanie do wykonania
    print("Pobieranie taska ...")
    task = get_next_task(cursor_local)
    #print(task)
    if not task:
        logger.info("Brak zadań do synchronizacji.")
        print("Brak zadań do synchronizacji.")
        return

    logger.info(f"Pobrano zadanie ID={task['id_task']} z bazy {task['id_database_connection']}")

    # Pobierz parametry połączenia z bazy zewnętrznej
    remote_params = get_remote_db_params(cursor_local, task['id_database_connection'])
    if not remote_params:
        logger.error(f"Nie znaleziono konfiguracji bazy zewnętrznej ID={task['id_database_connection']}")
        print(f"Nie znaleziono konfiguracji bazy zewnętrznej ID={task['id_database_connection']}")
        return

    # Nawiąż połączenie z bazą zewnętrzną
    print("Łącznie z DB remote : ", end="")
    conn_remote = connect_remote(remote_params)
    logger.info(f"Nawiązano połączenie z bazą zewnętrzną typu: {remote_params['db_type']}")
    print("OK")

    print("Rozpoczynam synchronizację ...")
    # Pobierz i zapisz partię rekordów do task_item
    try:
        fetch_remote_batch(conn_local, conn_remote, task, cfg['BATCH_SIZE'], remote_params, logger)
    except Exception as error:  # noqa: BLE001
        logger.error("Synchronizacja zakończona błędem: %s", error)
        print(f"Synchronizacja zakończona błędem")
    else:
        logger.info("Synchronizacja zakończona.")
        print(f"Synchronizacja zakończona.")
    finally:
        cursor_local.close()
        conn_local.close()
        conn_remote.close()

if __name__ == "__main__":
    main()

