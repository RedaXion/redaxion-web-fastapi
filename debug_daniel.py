import os
import sys
from services import database

# Print environment info
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
print(f"Using Postgres: {database.USE_POSTGRES}")

# Find Daniel's order
print("\nSearching for orders for 'Daniel'...")
try:
    conn = database.get_connection()
    c = conn.cursor()
    
    if database.USE_POSTGRES:
        c.execute("SELECT id, email, client, status, created_at, service_type FROM orders WHERE client ILIKE '%Daniel Rodriguez%' OR email ILIKE '%daniel%'")
    else:
        c.execute("SELECT id, email, client, status, created_at, service_type FROM orders WHERE client LIKE '%Daniel Rodriguez%' OR email LIKE '%daniel%'")
        
    rows = c.fetchall()
    
    if not rows:
        print("No orders found for Daniel Rodriguez.")
    else:
        for row in rows:
            print(f"DTO: {dict(row) if hasattr(row, 'keys') else row}")
            
    conn.close()
except Exception as e:
    print(f"Error querying DB: {e}")
