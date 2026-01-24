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

        # Create Transactions Table
        try:
             cur.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    amount INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
             print("Created table 'transactions' (if not exists)")
        except Exception as e:
             print(f"Error creating transactions table: {e}")

        # Create Payment Requests Table
        try:
             cur.execute('''
                CREATE TABLE IF NOT EXISTS payment_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    receipt_img TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    amount INTEGER DEFAULT 0,
                    admin_note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
             print("Created table 'payment_requests' (if not exists)")
        except Exception as e:
             print(f"Error creating payment_requests table: {e}")

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

        # Verify Tables
        print("\n--- Verifying Tables ---")
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [row[0] for row in cur.fetchall()]
        print(f"Tables found: {tables}")
        
        if 'transactions' in tables:
            print("SUCCESS: 'transactions' table EXISTS.")
            # Verify columns of transactions
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'transactions'")
            cols = [row[0] for row in cur.fetchall()]
            print(f"Columns in transactions: {cols}")
        else:
            print("FAILURE: 'transactions' table does NOT exist!")

        cur.close()
        conn.close()
        print("\nCheck completed.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    migrate()
    input("\nPress Enter to exit...")
