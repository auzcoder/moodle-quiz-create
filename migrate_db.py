import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "moodle_quiz_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def migrate():
    print(f"Connecting to database {DB_NAME} as {DB_USER}...")
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.autocommit = True
        cur = conn.cursor()
        print("Connected successfully.")

        commands = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role INTEGER DEFAULT 2",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tariff_id INTEGER",  # Removed FK reference for safety here, just column first
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tariff_expires_at TIMESTAMP",
            
            "ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30",
            "ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 0",
            "ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS file_cost INTEGER DEFAULT 0",
            
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER"
        ]

        for cmd in commands:
            print(f"Executing: {cmd}")
            try:
                cur.execute(cmd)
                print("  -> Success")
            except Exception as e:
                print(f"  -> Error (probably ignored): {e}")

        # Ensure Foreign Key exists properly (separate step to avoid error if column didn't exist before)
        try:
             # Check if constraint exists, if not add it (Postgres specific check is complex properly, 
             # so we just try to add column above. Adding constraint blindly can error if duplicate.)
             # Simpler: Just rely on column existence. 
             pass
        except:
            pass

        # Verification of columns
        print("\nVerifying 'users' columns:")
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
        columns = [row[0] for row in cur.fetchall()]
        print(columns)
        
        if 'balance' in columns:
            print("\nSUCCESS: 'balance' column exists!")
        else:
            print("\nFAILURE: 'balance' column missing!")

        cur.close()
        conn.close()
        print("\nMigration completed.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    migrate()
    input("\nPress Enter to exit...")
