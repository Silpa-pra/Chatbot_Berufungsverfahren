import mysql.connector
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os
from contextlib import contextmanager

load_dotenv()


def get_db_connection():
    conn = mysql.connector.connect(
        host = "127.0.0.1",
        user = "root",
        password = os.getenv("DB_PASSWORD"),
        database = os.getenv("DB_NAME")
    )
    return conn

@contextmanager
def get_db_cursor(dictionary = True):
    """Context manager for database operations"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()