import mysql.connector
import pyodbc
import psycopg2
import sqlite3

def connect_remote(params):
    """Łączy się z bazą zewnętrzną wg typu db_type"""
    db_type = params.get('db_type')
    if db_type == 'mysql':
        return mysql.connector.connect(
            host=params['host'],
            user=params['db_user'],
            password=params['db_password'],
            database=params['db_name'],
            port=params.get('port', 3306)
        )
    elif db_type == 'mssql':
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={params['host']},{params['port']};DATABASE={params['db_name']};UID={params['db_user']};PWD={params['db_password']}"
        return pyodbc.connect(conn_str)
    elif db_type == 'pgsql':
        return psycopg2.connect(
            host=params['host'],
            user=params['db_user'],
            password=params['db_password'],
            dbname=params['db_name'],
            port=params.get('port', 5432)
        )
    elif db_type == 'sqlite':
        return sqlite3.connect(params['db_name'])
    else:
        raise ValueError(f"Nieobsługiwany typ bazy danych: {db_type}")
