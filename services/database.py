"""
Database Service - Supports both PostgreSQL (production) and SQLite (development)

Uses DATABASE_URL environment variable to connect to PostgreSQL.
Falls back to SQLite if DATABASE_URL is not set.
"""

import json
import os
from datetime import datetime
from urllib.parse import urlparse

# Check if PostgreSQL is available (via DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    USE_POSTGRES = True
    print(f"🐘 Usando PostgreSQL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'configured'}")
else:
    import sqlite3
    USE_POSTGRES = False
    DB_NAME = "redaxion.db"
    print(f"📁 Usando SQLite: {DB_NAME}")


def get_connection():
    """Get a database connection."""
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor()
        # PostgreSQL syntax
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                status TEXT,
                client TEXT,
                email TEXT,
                color TEXT,
                columnas TEXT,
                files TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                audio_url TEXT,
                service_type TEXT,
                metadata TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS discount_codes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER,
                active INTEGER DEFAULT 1,
                max_uses INTEGER,
                uses_count INTEGER DEFAULT 0,
                expiry_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert initial discount codes (PostgreSQL ON CONFLICT syntax)
        try:
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count)
                VALUES ('REDAXION10D', 10, 1, NULL, 0)
                ON CONFLICT (code) DO NOTHING
            ''')
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count)
                VALUES ('REDAXION_DRJR', 15, 1, NULL, 0)
                ON CONFLICT (code) DO NOTHING
            ''')
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count)
                VALUES ('DESCUENTO80', 80, 1, NULL, 0)
                ON CONFLICT (code) DO NOTHING
            ''')
            print("🏷️ Códigos de descuento inicializados")
        except Exception as e:
            print(f"⚠️ Error creando códigos iniciales: {e}")
            
    else:
        # SQLite syntax
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS discount_codes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER,
                active INTEGER DEFAULT 1,
                max_uses INTEGER,
                uses_count INTEGER DEFAULT 0,
                expiry_date TIMESTAMP,
                created_at TIMESTAMP
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
        
        # Insert initial discount codes (SQLite INSERT OR IGNORE)
        try:
            c.execute('''
                INSERT OR IGNORE INTO discount_codes (code, discount_percent, active, max_uses, uses_count, created_at)
                VALUES ('REDAXION10D', 10, 1, NULL, 0, datetime('now'))
            ''')
            c.execute('''
                INSERT OR IGNORE INTO discount_codes (code, discount_percent, active, max_uses, uses_count, created_at)
                VALUES ('REDAXION_DRJR', 15, 1, NULL, 0, datetime('now'))
            ''')
            c.execute('''
                INSERT OR IGNORE INTO discount_codes (code, discount_percent, active, max_uses, uses_count, created_at)
                VALUES ('DESCUENTO80', 80, 1, NULL, 0, datetime('now'))
            ''')
            print("🏷️ Códigos de descuento inicializados")
        except Exception as e:
            print(f"⚠️ Error creando códigos iniciales: {e}")
    
    conn.commit()
    conn.close()


def create_order(data: dict):
    """Creates a new order record."""
    conn = get_connection()
    c = conn.cursor()
    try:
        files_json = json.dumps(data.get("files", []))
        metadata_json = json.dumps(data.get("metadata", {}))
        
        if USE_POSTGRES:
            c.execute('''
                INSERT INTO orders (id, status, client, email, color, columnas, files, created_at, audio_url, service_type, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        else:
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
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM orders WHERE id = %s', (orden_id,))
    else:
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
    conn = get_connection()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute('UPDATE orders SET status = %s WHERE id = %s', (status, orden_id))
    else:
        c.execute('UPDATE orders SET status = ? WHERE id = ?', (status, orden_id))
    conn.commit()
    conn.close()


def update_order_files(orden_id: str, files_list: list):
    """Updates the files list of an order."""
    conn = get_connection()
    c = conn.cursor()
    files_json = json.dumps(files_list)
    if USE_POSTGRES:
        c.execute('UPDATE orders SET files = %s WHERE id = %s', (files_json, orden_id))
    else:
        c.execute('UPDATE orders SET files = ? WHERE id = ?', (files_json, orden_id))
    conn.commit()
    conn.close()
    

def get_orders_by_email(email: str):
    """Retrieves all orders for a specific email."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM orders WHERE email = %s ORDER BY created_at DESC', (email,))
    else:
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


def get_latest_pending_exam_order():
    """Get the most recent pending exam order for fallback processing."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('''
            SELECT * FROM orders 
            WHERE status = 'pending' AND service_type = 'exam'
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
    else:
        c = conn.cursor()
        c.execute('''
            SELECT * FROM orders 
            WHERE status = 'pending' AND service_type = 'exam'
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
    
    row = c.fetchone()
    conn.close()
    
    if row:
        r = dict(row)
        if r.get("files"):
            try:
                r["files"] = json.loads(r["files"])
            except:
                r["files"] = []
        if r.get("metadata"):
            try:
                r["metadata"] = json.loads(r["metadata"])
            except:
                r["metadata"] = {}
        else:
            r["metadata"] = {}
        return r
    return None


# --- Discount Codes ---

def create_discount_code(code: str, discount_percent: int, max_uses: int = None, expiry_date: str = None):
    """Create a new discount code."""
    conn = get_connection()
    c = conn.cursor()
    try:
        if USE_POSTGRES:
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count, expiry_date, created_at)
                VALUES (%s, %s, 1, %s, 0, %s, %s)
            ''', (code.upper(), discount_percent, max_uses, expiry_date, datetime.now()))
        else:
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count, expiry_date, created_at)
                VALUES (?, ?, 1, ?, 0, ?, ?)
            ''', (code.upper(), discount_percent, max_uses, expiry_date, datetime.now()))
        conn.commit()
        print(f"✅ Código de descuento creado: {code.upper()} ({discount_percent}%)")
        return True
    except Exception as e:
        print(f"⚠️ Código {code} ya existe o error: {e}")
        return False
    finally:
        conn.close()


def validate_discount_code(code: str) -> dict:
    """
    Validate a discount code and return discount info.
    Returns: {"valid": True, "discount_percent": X} or {"valid": False, "reason": "..."}
    """
    if not code:
        return {"valid": False, "reason": "Código vacío"}
    
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM discount_codes WHERE code = %s', (code.upper(),))
    else:
        c = conn.cursor()
        c.execute('SELECT * FROM discount_codes WHERE code = ?', (code.upper(),))
    
    row = c.fetchone()
    conn.close()
    
    if not row:
        return {"valid": False, "reason": "Código no encontrado"}
    
    row = dict(row)
    
    # Check if active
    if not row.get("active"):
        return {"valid": False, "reason": "Código inactivo"}
    
    # Check max uses
    if row.get("max_uses") is not None:
        if row.get("uses_count", 0) >= row.get("max_uses"):
            return {"valid": False, "reason": "Código agotado"}
    
    # Check expiry
    if row.get("expiry_date"):
        try:
            expiry = datetime.fromisoformat(str(row["expiry_date"]))
            if datetime.now() > expiry:
                return {"valid": False, "reason": "Código expirado"}
        except:
            pass
    
    return {
        "valid": True,
        "discount_percent": row.get("discount_percent", 0)
    }


def increment_code_usage(code: str):
    """Increment the usage count for a discount code."""
    conn = get_connection()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute('UPDATE discount_codes SET uses_count = uses_count + 1 WHERE code = %s', (code.upper(),))
    else:
        c.execute('UPDATE discount_codes SET uses_count = uses_count + 1 WHERE code = ?', (code.upper(),))
    conn.commit()
    conn.close()


def get_all_discount_codes():
    """Get all discount codes for admin view."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
    else:
        c = conn.cursor()
    
    c.execute('SELECT * FROM discount_codes ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def deactivate_discount_code(code: str):
    """Deactivate a discount code."""
    conn = get_connection()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute('UPDATE discount_codes SET active = 0 WHERE code = %s', (code.upper(),))
    else:
        c.execute('UPDATE discount_codes SET active = 0 WHERE code = ?', (code.upper(),))
    conn.commit()
    conn.close()
