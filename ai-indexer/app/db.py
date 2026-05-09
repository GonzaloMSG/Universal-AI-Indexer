import sqlite3
import json
from typing import List, Dict, Any, Optional
from app.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Workspaces table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Documents FTS5 table
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
            file_path, 
            object_name, 
            block_type, 
            statement_type, 
            text, 
            line_start UNINDEXED, 
            line_end UNINDEXED, 
            metadata_json UNINDEXED,
            workspace_id UNINDEXED
        )
    ''')

    # Embeddings table
    # Link it to the rowid of the documents FTS table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS embeddings (
            doc_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
