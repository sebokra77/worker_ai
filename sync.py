#!/usr/bin/env python3
import sys
from lib.load_config import load_env
from lib.db_utils import log_error_and_print, setup_logger
from lib.db_local import connect_local
from lib.db_remote import connect_remote
from lib.task import get_next_task, get_remote_db_params, update_task_sync_progress
from lib.task_item import fetch_remote_batch, resynch_remote_batch

def main():
    # Załaduj konfigurację i logger
    try:
        print("Wczytywanie konfiguracji ",end="")
        cfg = load_env()
    except ValueError as error:
        print(f"Błąd konfiguracji środowiska w pliku .env: {error}")
        sys.exit(1)
    print("\033[32mOK\033[0m") 

    logger = setup_logger('sync', 'logs/sync.log')
    
    # Połączenie z bazą lokalną
    print("Łącznie z DB local : ", end="")
    conn_local = connect_local(cfg)
    if not conn_local:
        print(" Error")
        log_error_and_print(logger, "Nie udało się połączyć z bazą lokalną.")
        sys.exit(1)
    print("\033[32mOK\033[0m") 
    
    cursor_local = conn_local.cursor(dictionary=True)

    # Pobierz zadanie do wykonania
    print("Pobieranie taska : ", end="")
    task = get_next_task(cursor_local)
    #print(task)
    if not task:
        logger.info("Brak zadań do synchronizacji.")
        print(f"\033[33mbrak zadań do synchronizacji\033[0m")
        return
    print("\033[32mOK\033[0m") 
    logger.info(f"Pobrano zadanie ID={task['id_task']} z bazy {task['id_database_connection']}")

    # Pobierz parametry połączenia z bazy zewnętrznej
    remote_params = get_remote_db_params(cursor_local, task['id_database_connection'])
    if not remote_params:
        log_error_and_print(
            logger,
            "Nie znaleziono konfiguracji bazy zewnętrznej ID=%s",
            task['id_database_connection'],
        )
        return

    # Nawiąż połączenie z bazą zewnętrzną
    print("Łącznie z DB remote : ", end="")
    conn_remote = connect_remote(remote_params)
    logger.info(f"Nawiązano połączenie z bazą zewnętrzną typu: {remote_params['db_type']}")
    print("OK")

    print("Rozpoczynam synchronizację ...")
    stage = task.get('sync_stage')

    if stage in {"new", "fetch"}:
        try:
            fetch_remote_batch(conn_local, conn_remote, task, cfg['BATCH_SIZE'], remote_params, logger)
        except Exception as error:  # noqa: BLE001
            log_error_and_print(
                logger,
                "Synchronizacja zakończona błędem: %s",
                error,
            )
        else:
            summary = update_task_sync_progress(conn_local, task['id_task'])
            logger.info(
                "Podsumowanie zadania ID=%s: pending=%s, postęp=%.2f%%, status=%s",
                task['id_task'],
                summary['pending_count'],
                summary['sync_progress'],
                summary['status'],
            )
            print(
                "Synchronizacja zakończona. Oczekujące rekordy: "
                f"{summary['pending_count']}, postęp: {summary['sync_progress']:.2f}%, "
                f"status: {summary['status']}"
            )
    elif stage in {"resynch"}:
        try:
            resynch_remote_batch(conn_local, conn_remote, task, cfg['BATCH_SIZE'], remote_params, logger)
            fetch_remote_batch(conn_local, conn_remote, task, cfg['BATCH_SIZE'], remote_params, logger)
        except Exception as error:  # noqa: BLE001
            log_error_and_print(
                logger,
                "Synchronizacja zakończona błędem: %s",
                error,
            )
        else:
            summary = update_task_sync_progress(conn_local, task['id_task'])
            logger.info(
                "Podsumowanie zadania ID=%s: pending=%s, postęp=%.2f%%, status=%s",
                task['id_task'],
                summary['pending_count'],
                summary['sync_progress'],
                summary['status'],
            )
            print(
                "Synchronizacja zakończona. Oczekujące rekordy: "
                f"{summary['pending_count']}, postęp: {summary['sync_progress']:.2f}%, "
                f"status: {summary['status']}"
            )
    else:
        logger.info(
            "Pominięto pobieranie rekordów dla zadania ID=%s na etapie %s.",
            task.get('id_task'),
            stage,
        )
        print(f"\033[33mbrak zadań do przetworzenia\033[0m")

    cursor_local.close()
    conn_local.close()
    conn_remote.close()

if __name__ == "__main__":
    main()

