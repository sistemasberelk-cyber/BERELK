
import sqlite3
import os

db_path = 'nexpos.db'
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found.")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"Tables found: {[t[0] for t in tables]}")
        
        for table_name in tables:
            table = table_name[0]
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"Table '{table}': {count} rows")
            except Exception as e:
                print(f"Error counting table {table}: {e}")
                
        conn.close()
    except Exception as e:
        print(f"Error connecting to database: {e}")
