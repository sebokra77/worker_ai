import hashlib
import re
from typing import Any, Dict, List, Sequence, Tuple


def sanitize_identifier(name: str) -> str:
    """Waliduje nazwę identyfikatora SQL.

    Args:
        name (str): Nazwa identyfikatora do sprawdzenia.

    Returns:
        str: Ta sama nazwa przekazana w argumencie.

    Raises:
        ValueError: Gdy identyfikator zawiera niedozwolone znaki.
    """

    if not re.match(r"^[A-Za-z0-9_]+$", name):
        raise ValueError(f"Nieprawidłowa nazwa identyfikatora: {name}")
    return name


def calculate_hash(text: str, method: str) -> str:
    """Oblicza hash tekstu wskazanym algorytmem.

    Args:
        text (str): Tekst, który należy zhashować.
        method (str): Nazwa algorytmu dostępnego w ``hashlib``.

    Returns:
        str: Wartość heksadecymalna obliczonego skrótu.

    Raises:
        ValueError: Gdy przekazano nieobsługiwany algorytm hashujący.
    """

    try:
        hasher = hashlib.new(method.lower())
    except ValueError as error:  # noqa: B904
        raise ValueError(f"Nieobsługiwany algorytm hashujący: {method}") from error
    hasher.update((text or '').encode('utf-8'))
    return hasher.hexdigest()


def rows_to_dicts(cursor, rows: Sequence[Sequence[Any]]) -> List[Dict[str, Any]]:
    """Konwertuje wynik zapytania na listę słowników.

    Args:
        cursor: Oryginalny kursor użyty do pobrania danych.
        rows (Sequence[Sequence[Any]]): Dane zwrócone przez bazę.

    Returns:
        list[dict[str, Any]]: Lista słowników z kluczami jak aliasy kolumn.
    """

    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def extract_single_value(row: Any, key: str) -> Any:
    """Wydobywa pojedynczą wartość z dowolnej reprezentacji wiersza.

    Args:
        row (Any): Wiersz zwrócony z bazy danych.
        key (str): Nazwa kolumny lub aliasu do pobrania.

    Returns:
        Any: Wartość kolumny lub ``None``.
    """

    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, key):
        return getattr(row, key)
    if isinstance(row, (list, tuple)) and row:
        return row[0]
    return None


def append_task_error(cursor, id_task: int, message: str) -> None:
    """Dopisuje komunikat błędu do kolumny ``error_log``.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania.
        message (str): Treść komunikatu błędu.
    """

    sql = (
        "UPDATE task SET error_log = CASE "
        "WHEN error_log IS NULL OR error_log = '' THEN %s "
        "ELSE CONCAT(error_log, '\n', %s) END WHERE id_task = %s"
    )
    cursor.execute(sql, (message, message, id_task))


def append_task_description(cursor, id_task: int, message: str) -> None:
    """Dopisuje komunikat do kolumny ``description``.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania.
        message (str): Treść dopisywana do opisu zadania.
    """

    sql = (
        "UPDATE task SET description = CASE "
        "WHEN description IS NULL OR description = '' THEN %s "
        "ELSE CONCAT(description, '\n', %s) END WHERE id_task = %s"
    )
    cursor.execute(sql, (message, message, id_task))


def update_task_stage_and_markers(
    cursor,
    id_task: int,
    marker_max_id: int,
    stage: str,
    records_total: int | None,
) -> None:
    """Aktualizuje podstawowe znaczniki postępu w zadaniu.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania.
        marker_max_id (int): Ostatnia znana maksymalna wartość ID w źródle.
        stage (str): Nazwa etapu synchronizacji.
        records_total (int | None): Liczba rekordów do ustawienia w ``records_total``.
    """

    sql = (
        "UPDATE task SET marker_max_id = %s, sync_stage = %s"
        "{extra} WHERE id_task = %s"
    )
    extra = ''
    params: List[Any] = [marker_max_id, stage]
    if records_total is not None:
        extra = ', records_total = %s'
        params.append(records_total)
    params.append(id_task)
    cursor.execute(sql.format(extra=extra), tuple(params))


def build_fetch_query(
    db_type: str,
    table: str,
    id_column: str,
    text_column: str,
    batch_size: int,
    start_id: int,
) -> Tuple[str, Tuple[int, ...]]:
    """Buduje zapytanie pobierające partię rekordów.

    Args:
        db_type (str): Typ bazy danych źródła.
        table (str): Nazwa tabeli źródłowej.
        id_column (str): Nazwa kolumny z kluczem głównym.
        text_column (str): Nazwa kolumny tekstowej do pobrania.
        batch_size (int): Rozmiar partii.
        start_id (int): Wartość ID, od której rozpoczynamy pobieranie.

    Returns:
        tuple[str, tuple[int, ...]]: Zapytanie SQL wraz z krotką parametrów.
    """

    table = sanitize_identifier(table)
    id_column = sanitize_identifier(id_column)
    text_column = sanitize_identifier(text_column)

    if db_type == 'mssql':
        query = (
            f"SELECT TOP {batch_size} {id_column} AS remote_id, {text_column} AS text_value "
            f"FROM {table} WHERE {id_column} > ? ORDER BY {id_column} ASC"
        )
        params = (start_id,)
    elif db_type == 'sqlite':
        query = (
            f"SELECT {id_column} AS remote_id, {text_column} AS text_value "
            f"FROM {table} WHERE {id_column} > ? ORDER BY {id_column} ASC LIMIT {batch_size}"
        )
        params = (start_id,)
    else:
        query = (
            f"SELECT {id_column} AS remote_id, {text_column} AS text_value "
            f"FROM {table} WHERE {id_column} > %s ORDER BY {id_column} ASC LIMIT {batch_size}"
        )
        params = (start_id,)
    return query, params


def fetch_remote_batch(
    conn_local,
    conn_remote,
    task: Dict[str, Any],
    batch_size: int,
    remote_params: Dict[str, Any],
    logger,
) -> None:
    """Pobiera partię rekordów z bazy zewnętrznej i zapisuje je lokalnie.

    Args:
        conn_local: Połączenie z bazą lokalną MySQL.
        conn_remote: Połączenie z bazą zewnętrzną.
        task (dict[str, Any]): Słownik opisujący zadanie synchronizacji.
        batch_size (int): Maksymalna liczba rekordów do pobrania.
        remote_params (dict[str, Any]): Parametry źródłowej bazy danych.
        logger: Logger do zapisywania komunikatów.

    Raises:
        Exception: Przekazuje dalej wyjątki po zapisaniu ich w ``error_log``.
    """

    id_task = task['id_task']
    db_type = remote_params.get('db_type', 'mysql')
    table = sanitize_identifier(task['table_name'])
    id_column = sanitize_identifier(task['id_column_name'])
    text_column = sanitize_identifier(task['column_name'])
    hash_method = (task.get('hash_method') or 'sha256').lower()

    cursor_local = conn_local.cursor()
    cursor_remote = conn_remote.cursor()

    total_count = 0
    marker_max_id = 0

    try:
        # Walidacja istnienia kolumny klucza głównego w tabeli zewnętrznej
        if db_type == 'mssql':
            validation_query = (
                f"SELECT TOP 1 {id_column} AS remote_id, {text_column} AS text_value "
                f"FROM {table} ORDER BY {id_column} ASC"
            )
        else:
            validation_query = (
                f"SELECT {id_column} AS remote_id, {text_column} AS text_value "
                f"FROM {table} ORDER BY {id_column} ASC LIMIT 1"
            )
        cursor_remote.execute(validation_query)
        validation_row = cursor_remote.fetchone()
        if validation_row is not None:
            remote_id_value = extract_single_value(validation_row, 'remote_id')
            if remote_id_value is None:
                raise ValueError(
                    "Nie odnaleziono kolumny identyfikatora w tabeli źródłowej."
                )

        # Wyznaczenie łącznej liczby rekordów do pobrania
        count_query = f"SELECT COUNT(*) AS total_count FROM {table}"
        cursor_remote.execute(count_query)
        count_row = cursor_remote.fetchone()
        total_count = int(extract_single_value(count_row, 'total_count') or 0)

        # Pobranie maksymalnego ID ze źródła
        max_query = f"SELECT MAX({id_column}) AS max_id FROM {table}"
        cursor_remote.execute(max_query)
        max_row = cursor_remote.fetchone()
        marker_max_id = int(extract_single_value(max_row, 'max_id') or 0)

        update_task_stage_and_markers(cursor_local, id_task, marker_max_id, 'fetch', total_count)
        conn_local.commit()

        marker_id = int(task.get('marker_id') or 0)
        no_new_records = marker_max_id <= marker_id
        if no_new_records:
            msg = (
                "Brak nowych rekordów do importu (1) — aktualne dane są już zsynchronizowane "
                f"(marker_id={marker_id}, marker_max_id={marker_max_id})"
            )
            append_task_description(cursor_local, id_task, msg)
            print(msg)
            conn_local.commit()
        should_increment_new = (task.get('records_fetched') or 0) == 0
        current_marker = marker_id
        while not no_new_records and current_marker < marker_max_id:
            fetch_query, fetch_params = build_fetch_query(
                db_type,
                table,
                id_column,
                text_column,
                batch_size,
                current_marker,
            )
            cursor_remote.execute(fetch_query, fetch_params)

            rows = cursor_remote.fetchall()
            row_dicts = rows_to_dicts(cursor_remote, rows)
            if not row_dicts:
                msg = f"Brak nowych rekordów do importu (2) — zapytanie nie zwróciło danych " \
                      f"(current_marker={current_marker}, marker_max_id={marker_max_id})"
                append_task_description(cursor_local, id_task, msg)
                print(msg)
                conn_local.commit()
                break

            values_to_insert: List[Tuple[Any, ...]] = []
            for row in row_dicts:
                remote_id = row.get('remote_id')
                text_value = row.get('text_value')
                if remote_id is None:
                    continue
                # Zapewnienie ciągłości markerów nawet dla pustych tekstów
                text_value = text_value if text_value is not None else ''
                original_hash = calculate_hash(text_value, hash_method)
                values_to_insert.append((id_task, remote_id, text_value, original_hash))

            last_remote_id = int(row_dicts[-1]['remote_id'])
            inserted_count = len(values_to_insert)

            # Transakcja: insert + aktualizacja task
            conn_local.start_transaction()
            if values_to_insert:
                insert_sql = (
                    "INSERT INTO task_item (id_task, remote_id, text_original, original_hash, status, fetched_at) "
                    "VALUES (%s, %s, %s, %s, 'pending', NOW()) "
                    "ON DUPLICATE KEY UPDATE text_original = VALUES(text_original), "
                    "original_hash = VALUES(original_hash), fetched_at = VALUES(fetched_at)"
                )
                cursor_local.executemany(insert_sql, values_to_insert)

            records_fetched_increment = inserted_count
            records_new_increment = inserted_count if should_increment_new else 0

            update_sql = (
                "UPDATE task SET records_fetched = records_fetched + %s, "
                "records_new = records_new + %s, marker_id = %s WHERE id_task = %s"
            )
            cursor_local.execute(
                update_sql,
                (records_fetched_increment, records_new_increment, last_remote_id, id_task),
            )

            log_message = (
                f"Pobrano {inserted_count}, marker_id→{last_remote_id}, marker_max_id→{marker_max_id}."
            )
            append_task_description(cursor_local, id_task, log_message)

            conn_local.commit()

            logger.info(log_message)

            if should_increment_new and inserted_count > 0:
                should_increment_new = False
            current_marker = last_remote_id
            if len(row_dicts) < batch_size:
                break

        # Uaktualnienie liczników po zakończeniu cyklu
        cursor_local.execute(
            "SELECT COUNT(*) AS fetched_total FROM task_item WHERE id_task = %s",
            (id_task,),
        )
        local_total_row = cursor_local.fetchone()
        local_total = int(extract_single_value(local_total_row, 'fetched_total') or 0)
        records_fetched_value = local_total

        update_columns = "records_fetched = %s, records_total = %s"
        params: List[Any] = [records_fetched_value, total_count]
        if records_fetched_value == total_count:
            update_columns += ", sync_stage = 'done'"

        update_final_sql = f"UPDATE task SET {update_columns} WHERE id_task = %s"
        params.append(id_task)
        cursor_local.execute(update_final_sql, tuple(params))
        conn_local.commit()
    except Exception as error:  # noqa: BLE001
        conn_local.rollback()
        append_task_error(cursor_local, id_task, str(error))
        conn_local.commit()
        logger.exception("Błąd podczas pobierania partii rekordów")
        raise
    finally:
        cursor_local.close()
        cursor_remote.close()
