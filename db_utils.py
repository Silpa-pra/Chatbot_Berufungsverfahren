import mysql.connector
from urllib.parse import quote_plus
from dotenv import load_dotenv
import os

load_dotenv()


def get_db_connection():
    conn = mysql.connector.connect(
        host = "127.0.0.1",
        user = "root",
        password = os.getenv("DB_PASSWORD"),
        database = os.getenv("DB_NAME")
    )
    return conn