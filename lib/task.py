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
