# test_db.py
from db_utils import get_db_connection

print("Attempting to connect to the database...")
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    print("✅ Connection successful.")

    print("\nQuerying the 'full_procedure_view'...")
    cursor.execute("SELECT * FROM full_procedure_view LIMIT 1;")
    result = cursor.fetchone()

    if result:
        print("✅ Query successful! Found the view.")
    else:
        print("🟡 Query ran, but the view is empty.")

except Exception as e:
    print(f"❌ An error occurred: {e}")

finally:
    if 'conn' in locals() and conn.is_connected():
        cursor.close()
        conn.close()
        print("\nConnection closed.")