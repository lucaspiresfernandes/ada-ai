from database import DATABASE_NAME
import sqlite3


def constructDatabase():
    with sqlite3.connect(DATABASE_NAME) as con:
        cursor = con.cursor()
        cursor.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5 (context, date)")
        con.commit()


constructDatabase()
