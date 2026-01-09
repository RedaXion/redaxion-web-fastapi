import sqlite3
import os
import uuid
import time
from services import database

# Monkeypatch to use test DB
TEST_DB = "test_redaxion.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

database.DB_NAME = TEST_DB
database.USE_POSTGRES = False

def get_test_connection():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn

database.get_connection = get_test_connection
database.init_comments_table = lambda: None

# 1. Initialize DB (to ensure new column exists)
print(f"Initializing Test DB: {TEST_DB}...")
database.init_db()

# 2. Create a test order
orden_id = str(uuid.uuid4())
print(f"Creating test order {orden_id}...")
database.create_order({
    "id": orden_id,
    "status": "processing",
    "client": "Test User",
    "email": "test@example.com",
    "files": [],
    "metadata": {}
})

# 3. Simulate Logic Check (First Run)
print("\n--- Run 1: Should send email ---")
order = database.get_order(orden_id)
# Verify email_sent column exists and is 0
print(f"Initial email_sent value: {order.get('email_sent')}")

email_sent = order.get("email_sent", 0)
if not email_sent:
    print("✅ Logic: Sending email...")
    # Simulate sending
    time.sleep(0.1)
    # Mark as sent
    database.mark_order_email_sent(orden_id)
    print("Marked as sent.")
else:
    print("❌ Error: Should have sent email")

# 4. Simulate Logic Check (Second Run - Retry)
print("\n--- Run 2: Should NOT send email ---")
order = database.get_order(orden_id)
print(f"Current email_sent value: {order.get('email_sent')}")

email_sent = order.get("email_sent", 0)
if not email_sent:
    print("❌ Error: Should NOT send email again")
else:
    print("✅ Logic: Email already sent. Omitiendo.")

# Cleanup
print("\nTest finished.")
