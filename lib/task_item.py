import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


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


def fetch_pending_task_items(
    cursor,
    id_task: int,
    chunk_size: int = 10,
    max_items: int = 20,
) -> List[Dict[str, Any]]:
    """Pobiera oczekujące rekordy ``task_item`` w niewielkich porcjach.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania, dla którego wyszukujemy rekordy.
        chunk_size (int): Rozmiar pojedynczej partii zapytań do bazy.
        max_items (int): Maksymalna liczba rekordów zwracana przez funkcję.

    Returns:
        list[dict[str, Any]]: Lista rekordów zawierających podstawowe dane tekstowe.
    """

    items: List[Dict[str, Any]] = []
    last_id = 0

    # Pętla pobiera dane partiami, aby ograniczyć liczbę jednoczesnych rekordów w pamięci
    while len(items) < max_items:
        sql = (
            "SELECT id_task_item, remote_id, text_original "
            "FROM task_item "
            "WHERE id_task = %s AND status = 'pending' AND id_task_item > %s "
            "ORDER BY id_task_item ASC LIMIT %s"
        )
        cursor.execute(sql, (id_task, last_id, chunk_size))
        batch = cursor.fetchall()
        if not batch:
            break
        items.extend(batch)
        last_id = batch[-1]['id_task_item']
        if len(batch) < chunk_size:
            break

    return items[:max_items]


def build_correction_prompt(records: Iterable[Dict[str, Any]]) -> str:
    """Buduje treść promptu dla modelu AI poprawiającego teksty.

    Args:
        records (Iterable[dict[str, Any]]): Lista rekordów z danymi tekstowymi.

    Returns:
        str: Gotowa treść promptu przekazywana do modelu AI.
    """

    lines: List[str] = [
        "<PROMPT>",
        "Popraw poniższe zdania pod względem ortograficznym, interpunkcyjnym i stylistycznym.",
        "Nie zmieniaj znaczenia zdań. Zwróć wynik w formacie JSON w postaci listy obiektów:",
        "[",
        "  {\"remote_id\":1,\"text_corrected\":\"...\"},",
        "  {\"remote_id\":2,\"text_corrected\":\"...\"}",
        "]",
        "",
        "Zdania:",
    ]

    # Doklejanie poszczególnych tekstów do sekcji "Zdania"
    for record in records:
        remote_id = record.get('remote_id')
        if remote_id is None:
            remote_id = record.get('id_task_item')
        text_value = (record.get('text_original') or '').replace('\r', ' ').replace('\n', ' ').strip()
        lines.append(f"{remote_id}. {text_value}")

    lines.append("</PROMPT>")
    return "\n".join(lines)


def parse_json_response(response_text: str) -> List[Dict[str, Any]]:
    """Waliduje i konwertuje odpowiedź modelu AI na strukturę Python.

    Args:
        response_text (str): Odpowiedź tekstowa zwrócona przez model AI.

    Returns:
        list[dict[str, Any]]: Zweryfikowana lista rekordów do dalszego przetwarzania.

    Raises:
        ValueError: Gdy odpowiedź nie jest poprawnym JSON-em lub nie spełnia wymagań.
    """

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as error:  # noqa: B904
        raise ValueError('Odpowiedź modelu AI nie jest poprawnym JSON-em.') from error

    if not isinstance(parsed, list):
        raise ValueError('Odpowiedź modelu AI powinna być listą obiektów JSON.')

    normalised: List[Dict[str, Any]] = []
    for idx, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise ValueError(f'Element #{idx} w odpowiedzi nie jest obiektem JSON.')
        normalised.append(item)

    return normalised


def update_task_items_from_json(
    cursor,
    id_task: int,
    response_items: Iterable[Dict[str, Any]],
) -> int:
    """Aktualizuje rekordy ``task_item`` na podstawie danych z modelu AI.

    Args:
        cursor: Kursor połączenia z bazą lokalną.
        id_task (int): Identyfikator zadania powiązanego z rekordami.
        response_items (Iterable[dict[str, Any]]): Dane przekazane z modelu AI.

    Returns:
        int: Liczba zaktualizowanych rekordów.

    Raises:
        ValueError: Gdy rekord odpowiedzi nie zawiera wymaganych pól.
    """

    updated = 0
    sql = (
        "UPDATE task_item SET text_corrected = %s, status = 'processed', "
        "processed_at = NOW() WHERE id_task = %s AND remote_id = %s"
    )

    # Iterujemy po danych z modelu, walidując minimalny zestaw pól
    for item in response_items:
        remote_id = item.get('remote_id', item.get('id'))
        text_corrected = item.get('text_corrected')
        if remote_id is None:
            raise ValueError('Element odpowiedzi nie zawiera pola remote_id/id.')
        if text_corrected is None:
            raise ValueError('Element odpowiedzi nie zawiera pola text_corrected.')

        cursor.execute(sql, (text_corrected, id_task, remote_id))
        if cursor.rowcount:
            updated += 1

    return updated


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


def resynch_remote_batch(
    conn_local,
    conn_remote,
    task: Dict[str, Any],
    batch_size: int,
    remote_params: Dict[str, Any],
    logger,
) -> None:
    """Porównuje dane zdalne z lokalnymi i aktualizuje zmienione rekordy.

    Args:
        conn_local: Połączenie z bazą lokalną MySQL.
        conn_remote: Połączenie z bazą zewnętrzną.
        task (dict[str, Any]): Informacje o zadaniu synchronizacji.
        batch_size (int): Maksymalna liczba rekordów pobieranych w jednej partii.
        remote_params (dict[str, Any]): Parametry połączenia z bazą zewnętrzną.
        logger: Logger do zapisywania komunikatów diagnostycznych.
    """

    id_task = task['id_task']
    db_type = remote_params.get('db_type', 'mysql')
    table = sanitize_identifier(task['table_name'])
    id_column = sanitize_identifier(task['id_column_name'])
    text_column = sanitize_identifier(task['column_name'])
    hash_method = (task.get('hash_method') or 'sha256').lower()

    cursor_local = conn_local.cursor()
    cursor_remote = conn_remote.cursor()

    updated_total = 0
    # W resynchronizacji korzystamy z istniejącego markera wyliczonego przy pobieraniu
    marker_max_id = int(task.get('marker_max_id') or 0)
    # Postęp w ramach paczek przechowujemy w kolumnie ``marker_id``
    current_marker = int(task.get('marker_id') or 0)
    if current_marker >= marker_max_id:
        # Jeżeli poprzedni proces ukończył zakres to rozpoczynamy od zera
        current_marker = 0

    try:
        while current_marker < marker_max_id:
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

            valid_rows = [row for row in row_dicts if row.get('remote_id') is not None]
            if not valid_rows:
                if not row_dicts:
                    break
                current_marker += batch_size
                continue

            remote_ids = [int(row['remote_id']) for row in valid_rows]
            placeholders = ','.join(['%s'] * len(remote_ids))
            select_sql = (
                f"SELECT remote_id, text_original FROM task_item "
                f"WHERE id_task = %s AND remote_id IN ({placeholders})"
            )
            params_local = (id_task,) + tuple(remote_ids)
            cursor_local.execute(select_sql, params_local)
            local_rows = cursor_local.fetchall()
            local_map = {int(row[0]): row[1] for row in local_rows}

            updates: List[Tuple[Any, ...]] = []
            for row in valid_rows:
                remote_id = int(row['remote_id'])
                text_value = row.get('text_value')
                remote_text = text_value if text_value is not None else ''
                local_text = local_map.get(remote_id)
                local_text = local_text if local_text is not None else ''
                if remote_text != local_text:
                    original_hash = calculate_hash(remote_text, hash_method)
                    updates.append((remote_text, original_hash, id_task, remote_id))

            last_remote_id = int(valid_rows[-1]['remote_id'])

            conn_local.start_transaction()
            log_message = None
            if updates:
                update_sql = (
                    "UPDATE task_item SET text_original = %s, original_hash = %s, fetched_at = NOW() "
                    "WHERE id_task = %s AND remote_id = %s"
                )
                cursor_local.executemany(update_sql, updates)
                update_task_sql = (
                    "UPDATE task SET records_updated = records_updated + %s, marker_id = %s WHERE id_task = %s"
                )
                cursor_local.execute(update_task_sql, (len(updates), last_remote_id, id_task))
                log_message = (
                    "Resynchronizacja: zaktualizowano {count} rekordów (zakres_remote_id {first}-{last})."
                    .format(count=len(updates), first=remote_ids[0], last=remote_ids[-1])
                )
                append_task_description(cursor_local, id_task, log_message)
                updated_total += len(updates)
            else:
                # Aktualizujemy marker nawet przy braku zmian w partii
                cursor_local.execute(
                    "UPDATE task SET marker_id = %s WHERE id_task = %s",
                    (last_remote_id, id_task),
                )

            conn_local.commit()
            if log_message:
                logger.info(log_message)

            current_marker = last_remote_id
            if len(valid_rows) < batch_size:
                break

        summary_message = (
            f"Resynchronizacja zakończona. Zaktualizowano {updated_total} rekordów."
        )
        append_task_description(cursor_local, id_task, summary_message)
        # Aktualizacja statusu zadania po zakończeniu resynchronizacji
        cursor_local.execute(
            "UPDATE task SET sync_stage = 'done', marker_id = %s WHERE id_task = %s",
            (marker_max_id, id_task),
        )
        conn_local.commit()
        logger.info(summary_message)
    except Exception as error:  # noqa: BLE001
        conn_local.rollback()
        append_task_error(cursor_local, id_task, str(error))
        conn_local.commit()
        logger.exception("Błąd podczas resynchronizacji rekordów")
        raise
    finally:
        cursor_local.close()
        cursor_remote.close()


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
            update_sql = (
                "UPDATE task SET records_fetched = records_fetched + %s, "
                "marker_id = %s WHERE id_task = %s"
            )
            cursor_local.execute(
                update_sql,
                (records_fetched_increment, last_remote_id, id_task),
            )

            log_message = (
                f"Pobrano {inserted_count}, marker_id→{last_remote_id}, marker_max_id→{marker_max_id}."
            )
            append_task_description(cursor_local, id_task, log_message)

            conn_local.commit()

            logger.info(log_message)
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
