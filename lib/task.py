from typing import Any, Dict


def get_next_task(cursor):
    """Pobiera najstarsze zadanie ze statusem new/in_progress/resync"""
    sql = """
        SELECT * FROM task
        WHERE status IN ('new','sync','resync')
        ORDER BY id_task ASC
        LIMIT 1
    """
    cursor.execute(sql)
    return cursor.fetchone()

def get_next_task_to_ai(cursor):
    """Pobiera najstarsze zadanie ze statusem new/in_progress/resync"""
    sql = """
        SELECT * FROM task
        WHERE status IN ('ai')
        ORDER BY id_task ASC
        LIMIT 1
    """
    cursor.execute(sql)
    return cursor.fetchone()


def update_task_ai_progress(cursor, id_task: int):
    """Aktualizuje postęp zadania po przetwarzaniu rekordów przez AI.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania, dla którego należy przeliczyć postęp.

    Returns:
        dict: Zbiór danych pomocniczych zawierających liczby rekordów i postęp procentowy.
    """

    # Pobierz liczbę rekordów oznaczonych jako zmienione i niezmienione
    sql_counts = """
        SELECT
            SUM(CASE WHEN status = 'unchanged' THEN 1 ELSE 0 END) AS unchanged_count,
            SUM(CASE WHEN status = 'changed' THEN 1 ELSE 0 END) AS changed_count
        FROM task_item
        WHERE id_task = %s
    """
    cursor.execute(sql_counts, (id_task,))
    counts_row = cursor.fetchone() or {}

    unchanged_count = int(counts_row.get('unchanged_count') or 0)
    changed_count = int(counts_row.get('changed_count') or 0)
    processed_total = unchanged_count + changed_count

    # Odczytaj łączną liczbę rekordów zadania
    cursor.execute("SELECT records_total FROM task WHERE id_task = %s", (id_task,))
    task_row = cursor.fetchone() or {}
    records_total = int(task_row.get('records_total') or 0)

    progress_value = 0.0
    if records_total:
        progress_value = round((processed_total / records_total) * 100, 2)

    # Przygotuj dane aktualizacji dla tabeli task
    update_values = [processed_total, progress_value, id_task]
    sql_update = "UPDATE task SET records_processed = %s, ai_progress = %s WHERE id_task = %s"

    new_status = None
    if records_total and processed_total >= records_total:
        new_status = 'export'
        sql_update = (
            "UPDATE task SET records_processed = %s, ai_progress = %s, status = %s "
            "WHERE id_task = %s"
        )
        update_values = [processed_total, progress_value, new_status, id_task]

    cursor.execute(sql_update, tuple(update_values))

    return {
        'unchanged_count': unchanged_count,
        'changed_count': changed_count,
        'processed_total': processed_total,
        'records_total': records_total,
        'progress_value': progress_value,
        'new_status': new_status,
    }

def get_remote_db_params(cursor, id_database_connection):
    """Pobiera parametry połączenia z tabeli database_connection"""
    sql = "SELECT * FROM database_connection WHERE id_database_connection=%s"
    cursor.execute(sql, (id_database_connection,))
    return cursor.fetchone()


def update_task_sync_progress(conn, id_task: int) -> Dict[str, Any]:
    """Aktualizuje postęp synchronizacji po imporcie danych.

    Args:
        conn: Połączenie z bazą danych MySQL.
        id_task (int): Identyfikator zadania wymagającego podsumowania.

    Returns:
        dict: Informacje o zliczonych rekordach oczekujących, obliczonym
        progresie oraz wynikowym statusie zadania.
    """

    cursor = conn.cursor(dictionary=True)
    try:
        # Zlicz liczbę rekordów oczekujących na dalsze etapy przetwarzania
        cursor.execute(
            "SELECT COUNT(*) AS pending_count FROM task_item WHERE id_task = %s AND status = 'pending'",
            (id_task,),
        )
        pending_row = cursor.fetchone() or {}
        pending_count = int(pending_row.get('pending_count') or 0)

        # Pobierz aktualne liczniki zadania, aby policzyć procent synchronizacji
        cursor.execute(
            "SELECT records_fetched, records_total, records_processed, status FROM task WHERE id_task = %s",
            (id_task,),
        )
        task_row = cursor.fetchone() or {}
        records_fetched = int(task_row.get('records_fetched') or 0)
        records_total = int(task_row.get('records_total') or 0)
        records_processed = int(task_row.get('records_processed') or 0)
        current_status = task_row.get('status')

        sync_progress = 0.0
        if records_total:
            sync_progress = round((records_fetched / records_total) * 100, 2)

        # Ustal docelowy status w zależności od liczników z zadania
        target_status = current_status
        if records_total and records_fetched == records_total:
            target_status = 'ai'
        if records_total and records_processed == records_total:
            target_status = 'export'

        # Przygotuj zapytanie aktualizujące postęp i ewentualnie status
        update_columns = ["sync_progress = %s"]
        params: list[Any] = [sync_progress]
        if target_status and target_status != current_status:
            update_columns.append("status = %s")
            params.append(target_status)

        update_sql = f"UPDATE task SET {', '.join(update_columns)} WHERE id_task = %s"
        params.append(id_task)
        cursor.execute(update_sql, tuple(params))
        conn.commit()

        return {
            'pending_count': pending_count,
            'sync_progress': sync_progress,
            'status': target_status,
        }
    finally:
        cursor.close()
