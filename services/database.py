import sqlite3
import json
import os
from datetime import datetime

DB_NAME = "redaxion.db"

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            status TEXT,
            client TEXT,
            email TEXT,
            color TEXT,
            columnas TEXT,
            files TEXT,
            created_at TIMESTAMP,
            audio_url TEXT,
            service_type TEXT,
            metadata TEXT
        )
    ''')
    
    # Migration: Add columns if they don't exist (for existing DBs)
    try:
        c.execute('ALTER TABLE orders ADD COLUMN service_type TEXT')
    except sqlite3.OperationalError:
        pass
        
    try:
        c.execute('ALTER TABLE orders ADD COLUMN metadata TEXT')
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def create_order(data: dict):
    """Creates a new order record."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        files_json = json.dumps(data.get("files", []))
        metadata_json = json.dumps(data.get("metadata", {}))
        
        c.execute('''
            INSERT INTO orders (id, status, client, email, color, columnas, files, created_at, audio_url, service_type, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data["id"],
            data["status"],
            data["client"],
            data["email"],
            data.get("color", ""),
            data.get("columnas", ""),
            files_json,
            datetime.now(),
            data.get("audio_url", ""),
            data.get("service_type", ""),
            metadata_json
        ))
        conn.commit()
    except Exception as e:
        print(f"DB Error creating order: {e}")
        raise e
    finally:
        conn.close()

def get_order(orden_id: str):
    """Retrieves an order by ID."""
    conn = sqlite3.connect(DB_NAME)
    # Return dict-like objects
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id = ?', (orden_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        row_dict = dict(row)
        # Parse files json back to list
        if row_dict.get("files"):
            try:
                row_dict["files"] = json.loads(row_dict["files"])
            except:
                row_dict["files"] = []
                
        # Parse metadata json back to dict
        if row_dict.get("metadata"):
            try:
                row_dict["metadata"] = json.loads(row_dict["metadata"])
            except:
                row_dict["metadata"] = {}
        else:
            row_dict["metadata"] = {}
            
        return row_dict
    return None

def update_order_status(orden_id: str, status: str):
    """Updates the status of an order."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ? WHERE id = ?', (status, orden_id))
    conn.commit()
    conn.close()

def update_order_files(orden_id: str, files_list: list):
    """Updates the files list of an order."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    files_json = json.dumps(files_list)
    c.execute('UPDATE orders SET files = ? WHERE id = ?', (files_json, orden_id))
    conn.commit()
    conn.close()
    
def get_orders_by_email(email: str):
    """Retrieves all orders for a specific email."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE email = ? ORDER BY created_at DESC', (email,))
    rows = c.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        r = dict(row)
        if r.get("files"):
            try:
                r["files"] = json.loads(r["files"])
            except:
                r["files"] = []
        results.append(r)
    return results
