import sqlite3

DATABASE_NAME = "memories.db"


def addToMemory(context: str, date: str):
    with sqlite3.connect(DATABASE_NAME) as con:
        cursor = con.cursor()
        cursor.execute(
            f"INSERT INTO memories (context, date) VALUES (?, ?)", (context, date,))
        con.commit()


def queryMemory(context: str, date: str | None = None):
    with sqlite3.connect(DATABASE_NAME) as con:
        cursor = con.cursor()
        cond = f"context: \"{context}\""
        if date:
            cond += f" AND date: \"{date}\""
        cursor.execute(
            f"SELECT * FROM memories WHERE memories MATCH ?", (cond,))
        memories = cursor.fetchall()
        return memories
