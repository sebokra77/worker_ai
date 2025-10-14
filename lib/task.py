def get_next_task(cursor):
    """Pobiera najstarsze zadanie ze statusem new/in_progress/resync"""
    sql = """
        SELECT * FROM task
        WHERE status IN ('new','in_progress','resync')
        ORDER BY id_task ASC
        LIMIT 1
    """
    cursor.execute(sql)
    return cursor.fetchone()

def get_remote_db_params(cursor, id_database):
    """Pobiera parametry połączenia z tabeli database_connection"""
    sql = "SELECT * FROM database_connection WHERE id_database=%s"
    cursor.execute(sql, (id_database,))
    return cursor.fetchone()
