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
        
        # Users table for authentication
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                email_verified INTEGER DEFAULT 0
            )
        ''')
        
        # Migration: Add user_id to orders if not exists
        try:
            c.execute('ALTER TABLE orders ADD COLUMN user_id TEXT')
            conn.commit()
            print("✅ Columna user_id agregada a orders")
        except Exception:
            conn.rollback()  # Clear failed transaction state
        
        # Migration: Add paid_amount to orders if not exists
        try:
            c.execute('ALTER TABLE orders ADD COLUMN paid_amount INTEGER DEFAULT 0')
            conn.commit()
            print("✅ Columna paid_amount agregada a orders")
        except Exception:
            conn.rollback()  # Clear failed transaction state
        
        # Migration: Add discount_code and discount_percent to orders if not exists
        try:
            c.execute('ALTER TABLE orders ADD COLUMN discount_code TEXT')
            conn.commit()
        except Exception:
            conn.rollback()
        try:
            c.execute('ALTER TABLE orders ADD COLUMN discount_percent INTEGER DEFAULT 0')
            conn.commit()
            print("✅ Columnas discount_code y discount_percent agregadas a orders")
        except Exception:
            conn.rollback()  # Clear failed transaction state
        
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
                VALUES ('JAIMESOTO_RX15', 20, 1, NULL, 0)
                ON CONFLICT (code) DO NOTHING
            ''')
            c.execute('''
                INSERT INTO discount_codes (code, discount_percent, active, max_uses, uses_count)
                VALUES ('DAVID', 30, 1, NULL, 0)
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
        
        # Users table for authentication
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP,
                email_verified INTEGER DEFAULT 0
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
        
        # Migration: Add user_id to orders for user authentication
        try:
            c.execute('ALTER TABLE orders ADD COLUMN user_id TEXT')
            print("✅ Columna user_id agregada a orders")
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
                VALUES ('JAIMESOTO_RX15', 20, 1, NULL, 0, datetime('now'))
            ''')
            c.execute('''
                INSERT OR IGNORE INTO discount_codes (code, discount_percent, active, max_uses, uses_count, created_at)
                VALUES ('DAVID', 30, 1, NULL, 0, datetime('now'))
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
                INSERT INTO orders (id, status, client, email, color, columnas, files, created_at, audio_url, service_type, metadata, paid_amount, discount_code, discount_percent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                metadata_json,
                data.get("paid_amount", 0),
                data.get("discount_code", ""),
                data.get("discount_percent", 0)
            ))
        else:
            c.execute('''
                INSERT INTO orders (id, status, client, email, color, columnas, files, created_at, audio_url, service_type, metadata, paid_amount, discount_code, discount_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                metadata_json,
                data.get("paid_amount", 0),
                data.get("discount_code", ""),
                data.get("discount_percent", 0)
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
    try:
        if USE_POSTGRES:
            c.execute('UPDATE discount_codes SET active = 0 WHERE code = %s', (code.upper(),))
        else:
            c.execute('UPDATE discount_codes SET active = 0 WHERE code = ?', (code.upper(),))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Error desactivando código {code}: {e}")
        conn.rollback()
    finally:
        conn.close()


def activate_discount_code(code: str):
    """Activate a discount code."""
    conn = get_connection()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute('UPDATE discount_codes SET active = 1 WHERE code = %s', (code.upper(),))
    else:
        c.execute('UPDATE discount_codes SET active = 1 WHERE code = ?', (code.upper(),))
    conn.commit()
    conn.close()


# === Analytics Functions ===

def init_analytics_tables():
    """Create analytics tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()
    
    if USE_POSTGRES:
        c.execute('''
            CREATE TABLE IF NOT EXISTS page_views (
                id SERIAL PRIMARY KEY,
                path TEXT,
                referrer TEXT,
                user_agent TEXT,
                ip_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT,
                referrer TEXT,
                user_agent TEXT,
                ip_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    conn.commit()
    conn.close()


def record_page_view(path: str, referrer: str = None, user_agent: str = None, ip_hash: str = None):
    """Record a page view for analytics."""
    conn = get_connection()
    c = conn.cursor()
    try:
        if USE_POSTGRES:
            c.execute('''
                INSERT INTO page_views (path, referrer, user_agent, ip_hash)
                VALUES (%s, %s, %s, %s)
            ''', (path, referrer, user_agent, ip_hash))
        else:
            c.execute('''
                INSERT INTO page_views (path, referrer, user_agent, ip_hash, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (path, referrer, user_agent, ip_hash))
        conn.commit()
    except Exception as e:
        print(f"Error recording page view: {e}")
    finally:
        conn.close()


def get_analytics_summary():
    """Get summary analytics for the admin dashboard."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
    else:
        c = conn.cursor()
    
    # Total page views
    c.execute('SELECT COUNT(*) as total FROM page_views')
    total_views = c.fetchone()
    total_views = dict(total_views)['total'] if total_views else 0
    
    # Views by page
    c.execute('''
        SELECT path, COUNT(*) as count 
        FROM page_views 
        GROUP BY path 
        ORDER BY count DESC 
        LIMIT 10
    ''')
    views_by_page = [dict(row) for row in c.fetchall()]
    
    # Views last 7 days (daily)
    if USE_POSTGRES:
        c.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM page_views 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
    else:
        c.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM page_views 
            WHERE created_at >= date('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
    views_by_day = []
    for row in c.fetchall():
        r = dict(row)
        if r.get("date"):
            r["date"] = str(r["date"])
        views_by_day.append(r)
    
    conn.close()
    
    return {
        'total_views': total_views,
        'views_by_page': views_by_page,
        'views_by_day': views_by_day
    }


def get_sales_summary():
    """Get sales summary for the admin dashboard."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
    else:
        c = conn.cursor()
    
    # Total orders by status
    c.execute('''
        SELECT status, COUNT(*) as count 
        FROM orders 
        GROUP BY status
    ''')
    orders_by_status = {row['status']: row['count'] for row in [dict(r) for r in c.fetchall()]}
    
    # Completed orders (paid + completed)
    completed_count = orders_by_status.get('completed', 0) + orders_by_status.get('paid', 0)
    
    # Orders by service type with actual revenue (using paid_amount if available)
    try:
        c.execute('''
            SELECT service_type, COUNT(*) as count, COALESCE(SUM(paid_amount), 0) as revenue
            FROM orders 
            WHERE status IN ('paid', 'completed', 'processing')
            GROUP BY service_type
        ''')
        orders_by_type = [dict(row) for row in c.fetchall()]
        has_paid_amount = True
    except Exception as e:
        # paid_amount column doesn't exist yet - use legacy query
        print(f"⚠️ paid_amount column not available, using legacy calculation: {e}")
        c.execute('''
            SELECT service_type, COUNT(*) as count
            FROM orders 
            WHERE status IN ('paid', 'completed', 'processing')
            GROUP BY service_type
        ''')
        orders_by_type = [dict(row) for row in c.fetchall()]
        has_paid_amount = False
    
    # Calculate total from actual paid amounts or estimate
    revenue_by_type = []
    total_revenue = 0
    for item in orders_by_type:
        service = item.get('service_type', 'transcription') or 'transcription'
        count = item.get('count', 0)
        revenue = item.get('revenue', 0) or 0 if has_paid_amount else 0
        
        # Fallback: if paid_amount is 0 (old orders) or column doesn't exist, estimate using base price
        if revenue == 0 and count > 0:
            if service == 'exam' or service == 'meeting':
                revenue = count * 1000  # Legacy estimate
            else:
                revenue = count * 3000  # Legacy estimate
            
        total_revenue += revenue
        revenue_by_type.append({
            'service_type': service,
            'count': count,
            'revenue': revenue
        })
    
    # Orders last 30 days (by day)
    if USE_POSTGRES:
        c.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM orders 
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            AND status IN ('paid', 'completed', 'processing')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
    else:
        c.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM orders 
            WHERE created_at >= date('now', '-30 days')
            AND status IN ('paid', 'completed', 'processing')
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
    orders_by_day = []
    for row in c.fetchall():
        r = dict(row)
        if r.get("date"):
            r["date"] = str(r["date"])
        orders_by_day.append(r)
    
    conn.close()
    
    return {
        'total_orders': sum(orders_by_status.values()),
        'completed_orders': completed_count,
        'orders_by_status': orders_by_status,
        'orders_by_type': orders_by_type,
        'revenue_by_type': revenue_by_type,
        'total_revenue': total_revenue,
        'orders_by_day': orders_by_day
    }


def calculate_estimated_costs(sales_summary: dict):
    """
    Calculate estimated costs based on API usage.
    
    Costs:
    - AssemblyAI: ~$0.00025/second of audio (~$0.015/minute)
    - OpenAI GPT-4: ~$0.03/1K input tokens, $0.06/1K output tokens
    - Average audio produces ~150 words/minute, ~200 tokens/minute
    - Each transcription has ~3 GPT passes
    - Each exam has ~2 GPT passes with ~500 tokens per question
    """
    
    transcription_count = 0
    exam_count = 0
    meeting_count = 0
    
    for item in sales_summary.get('orders_by_type', []):
        service = item.get('service_type', 'transcription') or 'transcription'
        count = item.get('count', 0)
        
        if service == 'transcription':
            transcription_count = count
        elif service == 'exam':
            exam_count = count
        elif service == 'meeting':
            meeting_count = count
    
    # Estimated costs per service
    # Transcription: avg 30 min audio = $0.45 AssemblyAI + ~$2 GPT = ~$2.50
    # Meeting: avg 45 min audio = $0.675 AssemblyAI + ~$3 GPT = ~$3.70
    # Exam: ~$0.50 GPT per exam (no audio)
    
    transcription_cost = transcription_count * 2.50
    meeting_cost = meeting_count * 3.70
    exam_cost = exam_count * 0.50
    
    total_api_cost = transcription_cost + meeting_cost + exam_cost
    
    # Other costs (hosting ~$5/month estimated)
    hosting_cost = 5.0
    
    total_costs = total_api_cost + hosting_cost
    
    # Revenue and margins
    total_revenue = sales_summary.get('total_revenue', 0)
    iva = total_revenue * 0.19  # 19% IVA Chile
    revenue_after_iva = total_revenue - iva
    
    net_profit = revenue_after_iva - total_costs
    margin_percent = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    return {
        'api_costs': {
            'transcription': round(transcription_cost, 2),
            'meeting': round(meeting_cost, 2),
            'exam': round(exam_cost, 2),
            'total_api': round(total_api_cost, 2)
        },
        'hosting_cost': round(hosting_cost, 2),
        'total_costs': round(total_costs, 2),
        'revenue': {
            'gross': total_revenue,
            'iva': round(iva, 2),
            'after_iva': round(revenue_after_iva, 2)
        },
        'net_profit': round(net_profit, 2),
        'margin_percent': round(margin_percent, 1)
    }


def get_recent_orders(limit: int = 20):
    """Get most recent orders for admin view."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('''
            SELECT id, status, client, email, service_type, created_at
            FROM orders 
            ORDER BY created_at DESC 
            LIMIT %s
        ''', (limit,))
    else:
        c = conn.cursor()
        c.execute('''
            SELECT id, status, client, email, service_type, created_at
            FROM orders 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
    
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_discount_codes_stats():
    """Get discount codes usage statistics for admin dashboard."""
    conn = get_connection()
    
    if USE_POSTGRES:
        c = conn.cursor(cursor_factory=RealDictCursor)
    else:
        c = conn.cursor()
    
    c.execute('''
        SELECT code, discount_percent, uses_count, active
        FROM discount_codes
        ORDER BY uses_count DESC
    ''')
    
    rows = c.fetchall()
    conn.close()
    
    codes = [dict(row) for row in rows]
    total_uses = sum(code.get('uses_count', 0) or 0 for code in codes)
    
    return {
        'codes': codes,
        'total_uses': total_uses
    }


# === User Authentication Functions ===

def create_user(user_id: str, email: str, password_hash: str, name: str):
    """Create a new user account."""
    conn = get_connection()
    c = conn.cursor()
    try:
        if USE_POSTGRES:
            c.execute('''
                INSERT INTO users (id, email, password_hash, name, created_at)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, email.lower(), password_hash, name, datetime.now()))
        else:
            c.execute('''
                INSERT INTO users (id, email, password_hash, name, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, email.lower(), password_hash, name, datetime.now()))
        conn.commit()
        print(f"👤 Usuario creado: {email}")
        return True
    except Exception as e:
        print(f"⚠️ Error creando usuario: {e}")
        return False
    finally:
        conn.close()


def get_user_by_email(email: str):
    """Get user by email address."""
    conn = get_connection()
    
    if USE_POSTGRES:
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM users WHERE email = %s', (email.lower(),))
    else:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email.lower(),))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_user_by_id(user_id: str):
    """Get user by ID."""
    conn = get_connection()
    
    if USE_POSTGRES:
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    else:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_orders_by_user_id(user_id: str):
    """Get all orders for a specific user ID."""
    conn = get_connection()
    
    if USE_POSTGRES:
        from psycopg2.extras import RealDictCursor
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC', (user_id,))
    else:
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    
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
        if r.get("metadata"):
            try:
                r["metadata"] = json.loads(r["metadata"])
            except:
                r["metadata"] = {}
        results.append(r)
    return results


def link_orders_to_user(email: str, user_id: str):
    """Link all existing orders with this email to the user ID."""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        if USE_POSTGRES:
            c.execute('UPDATE orders SET user_id = %s WHERE email = %s AND user_id IS NULL', 
                     (user_id, email.lower()))
        else:
            c.execute('UPDATE orders SET user_id = ? WHERE email = ? AND user_id IS NULL', 
                     (user_id, email.lower()))
        
        rows_updated = c.rowcount
        conn.commit()
        if rows_updated > 0:
            print(f"🔗 {rows_updated} órdenes vinculadas al usuario {email}")
    except Exception as e:
        print(f"⚠️ Error vinculando órdenes: {e}")
    finally:
        conn.close()


def update_order_user_id(orden_id: str, user_id: str):
    """Update the user_id of an order."""
    conn = get_connection()
    c = conn.cursor()
    
    if USE_POSTGRES:
        c.execute('UPDATE orders SET user_id = %s WHERE id = %s', (user_id, orden_id))
    else:
        c.execute('UPDATE orders SET user_id = ? WHERE id = ?', (user_id, orden_id))
    
    conn.commit()
    conn.close()
