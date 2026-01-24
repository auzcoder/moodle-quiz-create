import os
import uuid
import asyncio
import shutil
import datetime
import logging
import tempfile
import base64
from typing import Optional

# Postgres & Env
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Header, Depends, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Configuration ---
load_dotenv()

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

# Database Config
DB_NAME = os.getenv("DB_NAME", "moodle_quiz_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Helper ---
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise e

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt

# ... (Previous imports)

# --- Configuration ---
load_dotenv()

# ... (Previous Config)

# Mail Config
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"

# Security Utils
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=7) # 7 days session
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Email Utils
def send_verification_email(to_email: str, code: str):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = "Tasdiqlash kodi / Verification Code"
        
        body = f"""
        <html>
            <body>
                <h2>Moodle Quiz Creator</h2>
                <p>Sizning tasdiqlash kodingiz / Your verification code:</p>
                <h1 style="color: #3b82f6; letter-spacing: 5px;">{code}</h1>
                <p>Ushbu kod 5 daqiqa davomida amal qiladi. / This code is valid for 5 minutes.</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(MAIL_FROM, to_email, text)
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False

# --- Database Setup ---
def init_db():
    print(f"--- DB INIT CHECK ---")
    print(f"Connecting to: {DB_NAME} as user: {DB_USER}")
    try:
        conn = get_db_connection()
        conn.autocommit = True # Enable autocommit for creating tables/columns
        cur = conn.cursor()
        
        # Helper to run safe alter
        def safe_alter(sql):
            try:
                cur.execute(sql)
                # print(f"Executed: {sql}") 
            except Exception as e:
                # print(f"Ignored: {e}")
                pass

        # Tariffs Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS tariffs (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                daily_limit INTEGER NOT NULL DEFAULT 5,
                duration_days INTEGER NOT NULL DEFAULT 30,
                price INTEGER DEFAULT 0,
                file_cost INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Jobs Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT,
                status TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER
            )
        ''')
        
        # Users Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                role INTEGER DEFAULT 2,
                tariff_id INTEGER REFERENCES tariffs(id),
                tariff_expires_at TIMESTAMP,
                balance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Idempotent Column Additions (Run individually)
        safe_alter("ALTER TABLE users ADD COLUMN IF NOT EXISTS role INTEGER DEFAULT 2")
        safe_alter("ALTER TABLE users ADD COLUMN IF NOT EXISTS tariff_id INTEGER REFERENCES tariffs(id)")
        safe_alter("ALTER TABLE users ADD COLUMN IF NOT EXISTS tariff_expires_at TIMESTAMP")
        safe_alter("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0")
        safe_alter("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_tariff_change_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        
        safe_alter("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30")
        safe_alter("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 0")
        safe_alter("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS file_cost INTEGER DEFAULT 0")
        
        safe_alter("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER")
        safe_alter("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cost INTEGER DEFAULT 0")
        
        # Payment Requests Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS payment_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                receipt_img TEXT NOT NULL,
                transaction_id TEXT,
                status TEXT DEFAULT 'pending',
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tariff_id INTEGER
            )
        ''')
        safe_alter("ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS transaction_id TEXT")
        safe_alter("ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS tariff_id INTEGER")
        safe_alter("ALTER TABLE payment_requests ADD COLUMN IF NOT EXISTS declared_amount INTEGER DEFAULT 0")

        # Transactions Table
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
        
        # Seed Default Tariff
        cur.execute("SELECT id FROM tariffs WHERE name = 'Free'")
        if not cur.fetchone():
             cur.execute("INSERT INTO tariffs (name, daily_limit, duration_days, price, file_cost) VALUES ('Free', 5, 30, 0, 0)")
        
        # VERIFY COLUMNS
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
        cols = [r[0] for r in cur.fetchall()]
        print(f"CURRENT USER COLUMNS: {cols}")
        
        cur.close()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        print(f"DB INIT ERROR: {e}")

# Initialize DB on startup
init_db()

# --- App Setup ---
app = FastAPI(title="Lux Doc Converter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ... (Rest of app setup)

# --- Models ---
class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VerifyCode(BaseModel):
    email: EmailStr
    code: str

class ResendCode(BaseModel):
    email: EmailStr

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    email: EmailStr
    code: str
    new_password: str

# --- Auth Endpoints ---

@app.post("/auth/register")
async def register(user: UserRegister):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Check existing
        cur.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Bu email allaqachon ro'yxatdan o'tgan")
        
        # Format Phone: Ensure 998 prefix, remove spaces
        raw_phone = user.phone.replace(" ", "").replace("+", "")
        if not raw_phone.startswith("998"):
             raw_phone = "998" + raw_phone
             
        # Optional: Validate length (998 + 9 digits = 12 chars)
        if len(raw_phone) != 12:
             raise HTTPException(status_code=400, detail="Telefon raqam noto'g'ri formatda")

        hashed_pw = get_password_hash(user.password)
        
        # Get Free Tariff
        cur.execute("SELECT id, duration_days FROM tariffs WHERE name = 'Free'")
        tariff_row = cur.fetchone()
        
        tariff_id = None
        expires_at = None
        
        if tariff_row:
            tariff_id = tariff_row[0]
            duration = tariff_row[1]
            expires_at = datetime.datetime.now() + datetime.timedelta(days=duration)
        
        # Determine Role
        role = 1 if user.email == "auz.offical@gmail.com" else 2
        
        # Insert User (Unverified)
        cur.execute("""
            INSERT INTO users (full_name, email, phone, password_hash, is_verified, role, tariff_id, tariff_expires_at)
            VALUES (%s, %s, %s, %s, FALSE, %s, %s, %s)
            RETURNING id
        """, (user.full_name, user.email, raw_phone, hashed_pw, role, tariff_id, expires_at))
        
        user_id = cur.fetchone()[0]
        
        # Generate Code
        code = str(random.randint(1000, 9999))
        expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
        
        # Upsert Code
        cur.execute("""
            INSERT INTO verification_codes (email, code, expires_at, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (email) DO UPDATE 
            SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at, created_at = NOW()
        """, (user.email, code, expires))
        
        conn.commit()
        cur.close()
        
        # Send Email
        email_sent = send_verification_email(user.email, code)
        if not email_sent:
             logger.warning("Email sending failed")
        
        return {"message": "Ro'yxatdan o'tish muvaffaqiyatli. Iltimos, emailingizni tekshiring va kodni kiriting."}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Register error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/verify")
async def verify(data: VerifyCode):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Check code
        cur.execute("SELECT code, expires_at FROM verification_codes WHERE email = %s", (data.email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="Kod topilmadi yoki muddati tugagan")
            
        code, expires = row
        
        if code != data.code:
             raise HTTPException(status_code=400, detail="Noto'g'ri kod")
             
        if datetime.datetime.now() > expires:
             raise HTTPException(status_code=400, detail="Kod muddati tugagan")
             
        # Verify User
        cur.execute("UPDATE users SET is_verified = TRUE WHERE email = %s", (data.email,))
        
        # Delete code
        cur.execute("DELETE FROM verification_codes WHERE email = %s", (data.email,))
        
        conn.commit()
        cur.close()
        
        return {"message": "Email muvaffaqiyatli tasdiqlandi"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Verify error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/resend-code")
async def resend_code(data: ResendCode):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Check user exists
        cur.execute("SELECT id FROM users WHERE email = %s", (data.email,))
        if not cur.fetchone():
             raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
             
        code = str(random.randint(1000, 9999))
        expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
        
        # Upsert Code
        cur.execute("""
            INSERT INTO verification_codes (email, code, expires_at, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (email) DO UPDATE 
            SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at, created_at = NOW()
        """, (data.email, code, expires))
        
        conn.commit()
        cur.close()
        
        send_verification_email(data.email, code)
        
        return {"message": "Yangi kod yuborildi"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Resend code error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/forgot-password")
async def forgot_password(data: ForgotPassword):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Check user exists
        cur.execute("SELECT id FROM users WHERE email = %s", (data.email,))
        if not cur.fetchone():
            # For security, maybe dont reveal? But for UX we will.
            raise HTTPException(status_code=404, detail="Bunday email topilmadi")
            
        code = str(random.randint(1000, 9999))
        expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
        
        # Upsert Code (Reuse verification_codes table)
        cur.execute("""
            INSERT INTO verification_codes (email, code, expires_at, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (email) DO UPDATE 
            SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at, created_at = NOW()
        """, (data.email, code, expires))
        
        conn.commit()
        cur.close()
        
        send_verification_email(data.email, code)
        
        return {"message": "Tasdiqlash kodi yuborildi"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/reset-password")
async def reset_password(data: ResetPassword):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT code, expires_at FROM verification_codes WHERE email = %s", (data.email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="Kod topilmadi yoki muddati tugagan")
            
        code, expires = row
        
        if code != data.code:
             raise HTTPException(status_code=400, detail="Noto'g'ri kod")
             
        if datetime.datetime.now() > expires:
             raise HTTPException(status_code=400, detail="Kod muddati tugagan")
             
        # Update Password
        new_hash = get_password_hash(data.new_password)
        cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (new_hash, data.email))
        
        # Delete code
        cur.execute("DELETE FROM verification_codes WHERE email = %s", (data.email,))
        
        conn.commit()
        cur.close()
        
        return {"message": "Parol muvaffaqiyatli yangilandi. Endi kirishingiz mumkin."}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/login")
async def login(user: UserLogin):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT u.id, u.full_name, u.password_hash, u.is_verified, u.role, t.daily_limit, t.name as tariff_name 
            FROM users u
            LEFT JOIN tariffs t ON u.tariff_id = t.id
            WHERE u.email = %s
        """, (user.email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="Email yoki parol noto'g'ri")
            
        user_id, full_name, pw_hash, is_verified, role, limit, tariff_name = row
        
        # DEBUG LOGGING
        print(f"LOGIN ATTEMPT: {user.email}, is_verified={is_verified} (type: {type(is_verified)})")
        
        if not verify_password(user.password, pw_hash):
             print("LOGIN FAILED: Password mismatch")
             raise HTTPException(status_code=400, detail="Email yoki parol noto'g'ri")
             
        if is_verified is None or not bool(is_verified):
             print("LOGIN FAILED: User not verified")
             raise HTTPException(status_code=400, detail="Email tasdiqlanmagan. Iltimos avval tasdiqlang")
             
        # Generate Token
        token = create_access_token({"sub": user.email, "user_id": user_id, "name": full_name, "role": role})
        
        return {
            "access_token": token, 
            "token_type": "bearer", 
            "user": {
                "full_name": full_name, 
                "email": user.email, 
                "role": role,
                "tariff": {"name": tariff_name, "limit": limit}
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

# --- Auth Dependencies ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        if user is None:
            raise credentials_exception
        return user
    finally:
        conn.close()

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    # if not current_user.get("is_active"): # Add active check if needed
    #      raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != 1:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

def update_job_status(job_id: str, status: str, message: str = ""):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Check Job Cost for Refund
        if status == 'error':
             # Get job cost and user
             cur.execute("SELECT user_id, cost FROM jobs WHERE id = %s", (job_id,))
             job = cur.fetchone()
             
             if job and job[1] > 0: # If cost > 0
                 user_id = job[0]
                 cost = job[1]
                 
                 # Refund Balance
                 cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (cost, user_id))
                 
                 # Record Refund Transaction
                 cur.execute("""
                    INSERT INTO transactions (user_id, amount, type, description)
                    VALUES (%s, %s, 'refund', %s)
                 """, (user_id, cost, f"Muvaffaqiyatsiz konvertatsiya uchun qaytarildi (#{job_id})"))
                 
                 logger.info(f"Refunded {cost} to user {user_id} for failed job {job_id}")

        cur.execute("UPDATE jobs SET status = %s, message = %s WHERE id = %s", (status, message, job_id))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
    finally:
        conn.close()

def get_job(job_id: str):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, filename, status, message, created_at FROM jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
        cur.close()
        
        if row:
            # Row is a tuple (id, filename, status, message, created_at)
            # created_at might be a datetime object returning from Postgres
            return {
                "id": row[0],
                "filename": row[1],
                "status": row[2],
                "message": row[3],
                "created_at": str(row[4]) # Convert datetime to string
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching job: {e}")
        return None
    finally:
        conn.close()

# --- Conversion Logic (Custom GIFT with Images) ---
import base64
import re
from bs4 import BeautifulSoup
import platform
import subprocess

def convert_to_gift(input_path: str, output_path: str, output_format: str = 'gift'):
    """
    Converts Word Doc/Docx -> Filtered HTML -> Extract Questions
    Supports Windows (MS Word) and Linux (LibreOffice).
    """
    abs_input_path = os.path.abspath(input_path)
    abs_input_path = os.path.abspath(input_path)
    
    # Create a local temp directory in the project folder to ensure Word can access it (avoiding AppData or Temp restrictions)
    project_root = os.path.dirname(os.path.abspath(__file__))
    temp_work_dir = os.path.join(project_root, "temp_conversion")
    os.makedirs(temp_work_dir, exist_ok=True)
    
    # Create a unique subdir for this job
    job_temp_dir = os.path.join(temp_work_dir, f"job_{uuid.uuid4()}")
    os.makedirs(job_temp_dir, exist_ok=True)

    try:
        # Copy input file to temp dir
        filename_ext = os.path.basename(abs_input_path)
        filename = os.path.splitext(filename_ext)[0]
        temp_input_path = os.path.join(job_temp_dir, filename_ext)
        shutil.copy2(abs_input_path, temp_input_path)
        
        base_dir = job_temp_dir
        
        # We target .htm or .html in the temp dir
        htm_path = os.path.join(base_dir, f"{filename}.htm")
        html_path = os.path.join(base_dir, f"{filename}.html")
        files_dir = os.path.join(base_dir, f"{filename}_files")
        
        current_os = platform.system()
        
        if current_os == "Windows":
            try:
                import pythoncom
                import win32com.client
                
                pythoncom.CoInitialize()
                word = None
                try:
                    # Use EnsureDispatch for better stability
                    try:
                        word = win32com.client.gencache.EnsureDispatch("Word.Application")
                    except:
                        word = win32com.client.Dispatch("Word.Application")
                        
                    word.Visible = False
                    word.DisplayAlerts = 0 
                    
                    # Open ReadOnly from temp path
                    doc = word.Documents.Open(FileName=temp_input_path, ReadOnly=True, Visible=False)
                    
                    # Handle Protected View if it occurs (though unlikely in temp)
                    if word.ProtectedViewWindows.Count > 0:
                         try:
                             pv = word.ProtectedViewWindows(1)
                             doc = pv.Edit()
                         except:
                             pass

                    # Use SaveAs2 for better compatibility
                    htm_path = os.path.normpath(htm_path)
                    doc.SaveAs2(FileName=htm_path, FileFormat=10) # 10 = wdFormatFilteredHTML
                    doc.Close(SaveChanges=False)
                except Exception as e:
                    logger.error(f"Error automating Word: {e}")
                    raise e
                finally:
                    if word:
                        try:
                            word.Quit()
                        except:
                            pass
                    pythoncom.CoUninitialize()
            except ImportError:
                logger.error("win32com not found. Please install pywin32.")
                raise Exception("Windows conversion requires 'pywin32' library.")

        else:
            # Linux / MacOS Logic (LibreOffice)
            logger.info("Running on non-Windows OS. Trying LibreOffice...")
            try:
                cmd = [
                    "libreoffice", 
                    "--headless", 
                    "--convert-to", 
                    "html", 
                    "--outdir", 
                    base_dir, 
                    temp_input_path
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                if os.path.exists(html_path):
                    htm_path = html_path
                    
            except Exception as e:
                logger.error(f"LibreOffice conversion failed: {e}")
                raise Exception("LibreOffice conversion failed. Ensure 'libreoffice' is installed.")

        if not os.path.exists(htm_path) and not os.path.exists(html_path):
            raise Exception("HTML file was not created.")
            
        actual_htm_path = htm_path if os.path.exists(htm_path) else html_path

        # Parse HTML
        with open(actual_htm_path, "rb") as f:
            soup = BeautifulSoup(f, "html.parser")

        # 1. Clean and Escape Text
        for text_node in soup.find_all(string=True):
            if text_node.parent.name in ['script', 'style', 'title', 'meta']:
                continue
            if text_node.parent.name == 'span' and 'white-space: nowrap' in str(text_node.parent.get('style', '')):
                 continue

            original_text = str(text_node)
            new_text = original_text.replace("ù", "")
            if "<" in new_text: new_text = new_text.replace("<", "&lt;")
            if ">" in new_text: new_text = new_text.replace(">", "&gt;")
            
            # Note: We delay GIFT/Hemis specific escaping to the formatter level ideally, 
            # but current logic does it here. For Hemis, {}~= might be fine, but GIFT needs escaping.
            # For now, let's keep basic cleaning here, but move format-specific escaping if we can.
            # Actually, the user's current code does GIFT escaping IN PLACE. 
            # We should probably run escaping only if format is GIFT, or unescape for Hemis.
            # To keep it simple, I will keep the cleaning but remove the explicit GIFT escaping from here
            # and move it to the format_gift function.
            
            if new_text != original_text:
                text_node.replace_with(new_text)

        # 2. Convert Images to Base64
        img_tags = soup.find_all("img")
        for img in img_tags:
            src = img.get("src")
            if not src: continue
            
            # Image paths are relative to base_dir (temp_dir)
            image_full_path = os.path.join(base_dir, src)
            if not os.path.exists(image_full_path):
                possible_name = os.path.basename(src)
                possible_path = os.path.join(files_dir, possible_name)
                if os.path.exists(possible_path):
                    image_full_path = possible_path

            if os.path.exists(image_full_path):
                try:
                    with open(image_full_path, "rb") as img_file:
                        raw_data = img_file.read()
                        # Encode Base64
                        encoded_string = base64.b64encode(raw_data).decode("utf-8").replace("\n", "").replace("\r", "")
                        
                        mime_type = "image/png"
                        if image_full_path.lower().endswith((".jpg", ".jpeg")):
                            mime_type = "image/jpeg"
                        elif image_full_path.lower().endswith(".gif"):
                             mime_type = "image/gif"
                        
                        # Generate clean HTML tag
                        # format_gift will automatically escape '=' to '\=' later if needed
                        # format_hemis will leave it as is
                        code_string = f'<img src="data:{mime_type};base64,{encoded_string}">'
                            
                        img.replace_with(code_string)
                except Exception as e:
                    logger.warning(f"Could not encode image: {e}")

        # 3. Extract Questions
        questions = []
        tables = soup.find_all("table")
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3: continue

                def get_cell_text(cell):
                    text = cell.get_text(separator=' ', strip=True)
                    text = re.sub(r'\s+', ' ', text)
                    return text

                question_text = get_cell_text(cells[1])
                correct_answer = get_cell_text(cells[2])
                
                if not question_text and not correct_answer: continue

                # Skip header rows
                q_lower = question_text.lower()
                if "savol" in q_lower or "question" in q_lower or "to'g'ri javob" in q_lower:
                    continue
                    
                distractors = []
                for i in range(3, len(cells)):
                    alt_text = get_cell_text(cells[i])
                    if alt_text:
                        distractors.append(alt_text)
                
                questions.append({
                    "question": question_text,
                    "correct": correct_answer,
                    "distractors": distractors
                })

        return questions

    except Exception as e:
        logger.error(f"Conversion process failed: {e}")
        raise e
    finally:
        # Cleanup
        try:
            if 'job_temp_dir' in locals() and os.path.exists(job_temp_dir):
                shutil.rmtree(job_temp_dir)
        except Exception as ignored:
            logger.warning(f"Failed to cleanup temp dir: {ignored}")

def format_gift(questions):
    output_lines = []
    for q in questions:
        # Escape for GIFT
        def escape_gift(text):
            t = text.replace("{", "\\{").replace("}", "\\}").replace("=", "\\=").replace("~", "\\~")
            return t
            
        block = []
        block.append(f"::{escape_gift(q['question'])}{{")
        block.append(f"={escape_gift(q['correct'])}")
        for d in q['distractors']:
            block.append(f"~{escape_gift(d)}")
        block.append("}")
        output_lines.append("\n".join(block))
        output_lines.append("")
    return "\n".join(output_lines)

def format_hemis(questions):
    output_lines = []
    for q in questions:
        # Hemis format:
        # Question
        # ====
        # #Correct
        # ====
        # Wrong
        # ====
        # Wrong
        #
        # ++++
        #
        
        block = []
        block.append(q['question'])
        block.append("====")
        block.append(f"#{q['correct']}")
        block.append("====")
        for i, d in enumerate(q['distractors']):
            block.append(d)
            if i < len(q['distractors']) - 1:
                block.append("====")
        
        # Add separator + blank lines
        block.append("")
        block.append("++++")
        block.append("")
        
        output_lines.append("\n".join(block))

    return "\n".join(output_lines)

async def process_conversion(job_id: str, input_path: str, output_path: str, is_legacy: bool, output_format: str = 'gift'):
    try:
        update_job_status(job_id, "processing", "Konvertatsiya boshlandi...")
        
        loop = asyncio.get_event_loop()
        # Parse questions
        questions = await loop.run_in_executor(None, convert_to_gift, input_path, output_path, output_format) # convert_to_gift now returns questions list
        
        # Format
        if output_format == 'hemis':
            content = format_hemis(questions)
        else:
            content = format_gift(questions)
            
        # Write Output
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        update_job_status(job_id, "completed", "Konvertatsiya muvaffaqiyatli yakunlandi")
    except Exception as e:
        logger.error(f"Conversion failed for {job_id}: {str(e)}")
        update_job_status(job_id, "error", str(e))

# --- Endpoints ---

@app.get("/stats")
async def get_stats():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Count only completed jobs
        cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
        row = cur.fetchone()
        count = row[0] if row else 0
        cur.close()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return {"count": 0}
    finally:
        conn.close()

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard")
async def dashboard():
    return FileResponse('templates/dashboard.html')

@app.get("/login")
async def login_page():
    return FileResponse('templates/auth/login.html')

@app.get("/register")
async def register_page():
    return FileResponse('templates/auth/register.html')

@app.get("/pass-restore")
async def pass_restore_page():
    return FileResponse('templates/auth/pass-restore.html')

@app.get("/profile")
async def profile_page():
    return FileResponse('templates/auth/profile.html')
    return FileResponse('templates/auth/pass-restore.html')

@app.get("/admin")
async def admin_dashboard():
    return FileResponse('templates/admin/dashboard.html')

# --- Admin API Models ---
class UserUpdate(BaseModel):
    full_name: str
    email: str
    phone: str
    role: int
    tariff_id: int

class TariffCreate(BaseModel):
    name: str
    daily_limit: int
    duration_days: int
    price: int
    file_cost: int
    is_active: bool

class TariffUpdate(BaseModel):
    name: str
    daily_limit: int
    duration_days: int
    price: int
    file_cost: int
    is_active: bool

# --- Admin API Endpoints ---
@app.get("/api/admin/users")
async def get_all_users():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Added balance
        cur.execute("SELECT id, full_name, email, phone, role, is_verified, tariff_id, balance, created_at FROM users ORDER BY id ASC")
        users = cur.fetchall()
        for u in users:
            u['created_at'] = str(u['created_at'])
        return users
    finally:
        conn.close()

@app.put("/api/admin/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # If tariff changed, update expiry
        # 1. Get new tariff duration
        cur.execute("SELECT duration_days FROM tariffs WHERE id = %s", (data.tariff_id,))
        t_row = cur.fetchone()
        
        if t_row:
            duration = t_row[0]
            new_expires = datetime.datetime.now() + datetime.timedelta(days=duration)
            cur.execute("""
                UPDATE users 
                SET full_name = %s, email = %s, phone = %s, role = %s, tariff_id = %s, tariff_expires_at = %s 
                WHERE id = %s
            """, (data.full_name, data.email, data.phone, data.role, data.tariff_id, new_expires, user_id))
        else:
             cur.execute("""
                UPDATE users 
                SET full_name = %s, email = %s, phone = %s, role = %s, tariff_id = %s 
                WHERE id = %s
             """, (data.full_name, data.email, data.phone, data.role, data.tariff_id, user_id))
             
        conn.commit()
        return {"message": "User updated"}
    finally:
        conn.close()

@app.get("/api/admin/tariffs")
async def get_tariffs():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Ensure columns exist
        try:
            cur.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS file_cost INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0")
            conn.commit()
        except:
            conn.rollback()

        cur.execute("SELECT * FROM tariffs ORDER BY id ASC")
        tariffs = cur.fetchall()
        for t in tariffs:
            t['created_at'] = str(t['created_at'])
        return tariffs
    finally:
        conn.close()

@app.post("/api/admin/tariffs")
async def create_tariff(data: TariffCreate):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO tariffs (name, daily_limit, duration_days, price, file_cost, is_active) VALUES (%s, %s, %s, %s, %s, %s)", 
                  (data.name, data.daily_limit, data.duration_days, data.price, data.file_cost, data.is_active))
        conn.commit()
        return {"message": "Tariff created"}
    finally:
        conn.close()

@app.put("/api/admin/tariffs/{tariff_id}")
async def update_tariff(tariff_id: int, data: TariffUpdate):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE tariffs SET name = %s, daily_limit = %s, duration_days = %s, price = %s, file_cost = %s, is_active = %s WHERE id = %s", 
                  (data.name, data.daily_limit, data.duration_days, data.price, data.file_cost, data.is_active, tariff_id))
        conn.commit()
        return {"message": "Tariff updated"}
    finally:
        conn.close()

@app.get("/api/transactions")
async def get_my_transactions(authorization: Optional[str] = Header(None)):
    if not authorization: return JSONResponse({}, status_code=401)
    conn = None
    try:
        _, token = authorization.split()
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY created_at DESC LIMIT 50", (user_id,))
        txs = cur.fetchall()
        for t in txs:
            t['created_at'] = str(t['created_at'])
        return txs
    finally:
        if conn: conn.close()

@app.get("/api/admin/transactions")
async def get_all_transactions():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT t.*, u.full_name, u.email 
            FROM transactions t 
            LEFT JOIN users u ON t.user_id = u.id 
            ORDER BY t.created_at DESC LIMIT 100
        """)
        txs = cur.fetchall()
        for t in txs:
            t['created_at'] = str(t['created_at'])
        return txs
    finally:
        conn.close()

@app.get("/api/me")
async def get_me(authorization: Optional[str] = Header(None)):
    if not authorization: return JSONResponse({}, status_code=401)
    conn = None
    try:
        try:
            scheme, token = authorization.split()
            if scheme.lower() != 'bearer': raise Exception("Invalid Scheme")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("user_id")
        except Exception as e:
            logger.error(f"Auth Token Error: {e}")
            return JSONResponse({"detail": "Invalid Token"}, status_code=401)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # User Info + Tariff + Expiry
        # We explicitly list columns. If checking migration issues, select * is riskier if we depend on keys.
        # But explicit keys are better.
        cur.execute("""
            SELECT u.id, u.full_name, u.email, u.phone, u.role, u.tariff_expires_at, u.balance,
                   t.name as tariff_name, t.daily_limit, t.price, t.file_cost
            FROM users u
            LEFT JOIN tariffs t ON u.tariff_id = t.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()
        
        if not user: return JSONResponse({}, status_code=404)
        
        # Calculate Monthly Usage
        now = datetime.datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        cur.execute("""
            SELECT u.last_tariff_change_at 
            FROM users u WHERE id = %s
        """, (user.get('id'),))
        last_change_row = cur.fetchone()
        last_change = last_change_row['last_tariff_change_at'] if last_change_row else None

        # Effective Start Date: Max(StartOfMonth, LastTariffChange)
        start_date = start_of_month
        if last_change and last_change > start_of_month:
            start_date = last_change

        cur.execute("""
            SELECT COUNT(*) as count FROM jobs 
            WHERE user_id = %s AND created_at >= %s AND status != 'error'
        """, (user.get('id'), start_date))
        
        row = cur.fetchone()
        used_month = row['count'] if row else 0
        user['used_today'] = used_month # Monthly usage
        user['tariff_expires_at'] = str(user['tariff_expires_at']) if user['tariff_expires_at'] else None
        
        # Basic null handling
        if user['daily_limit'] is None: user['daily_limit'] = 0
        if user['file_cost'] is None: user['file_cost'] = 0
        if user['balance'] is None: user['balance'] = 0
        
        return user
    except Exception as e:
        logger.error(f"Error in /api/me: {e}")
        import traceback
        traceback.print_exc() # Print to console
        return JSONResponse({"detail": "Internal Server Error", "error": str(e)}, status_code=500)
    finally:
        if conn: conn.close()

from fastapi import Header

@app.post("/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...), 
    format: str = Form("gift"),
    authorization: Optional[str] = Header(None),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    if not authorization: raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = None
    try:
        _, token = authorization.split()
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get User & Tariff Info
        cur.execute("""
            SELECT u.tariff_expires_at, u.balance, t.daily_limit, t.file_cost
            FROM users u
            LEFT JOIN tariffs t ON u.tariff_id = t.id
            WHERE u.id = %s
        """, (user_id,))
        row = cur.fetchone()
        
        if not row: raise HTTPException(status_code=400, detail="Foydalanuvchi topilmadi")
             
        expires_at, balance, daily_limit, file_cost = row
        
        # Defaults
        if daily_limit is None: daily_limit = 0
        if file_cost is None: file_cost = 0
        if balance is None: balance = 0
        
        # Logic: 
        # 1. If Tariff Active AND Limit Not Reached -> Free
        # 2. ELSE -> Pay from Balance
        
        is_free_upload = False
        
        # Check Tariff Validity
        # Check Monthly Limit
        now = datetime.datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Check Effective Usage (Reset if tariff changed)
        cur.execute("SELECT last_tariff_change_at FROM users WHERE id = %s", (user_id,))
        last_change_row = cur.fetchone()
        last_change = last_change_row[0] if last_change_row else None
        
        effective_start = start_of_month
        if last_change and last_change > start_of_month:
            effective_start = last_change
            
        cur.execute("SELECT COUNT(*) FROM jobs WHERE user_id = %s AND created_at >= %s AND status != 'error'", (user_id, effective_start))
        effective_usage = cur.fetchone()[0]

        # Check Expiry
        # If exp date exists and is in past -> Expired
        if expires_at and expires_at < now:
             # Expired: Fallback to Free/Pay-per-file if implemented, or just block
             # For now, if expired, usage limit logic might not matter if we treat it as no tariff.
             pass 
             
        # Check Limit
        if daily_limit > 0 and effective_usage >= daily_limit:
             pass # Limit reached, so is_free_upload remains False
        
        # If tariff is active and not expired and limit not reached, it's a free upload
        if expires_at and now <= expires_at and (daily_limit == 0 or effective_usage < daily_limit):
            is_free_upload = True
        
        if not is_free_upload:
            # Check Balance
            if balance < file_cost:
                raise HTTPException(status_code=403, detail=f"Mablag' yetarli emas! Fayl narxi: {file_cost} so'm. Hisobingizda: {balance} so'm")
            
            # Deduct Balance & Record Transaction
            new_balance = balance - file_cost
            cur.execute("UPDATE users SET balance = %s WHERE id = %s", (new_balance, user_id))
            cur.execute("""
                INSERT INTO transactions (user_id, amount, type, description, created_at)
                VALUES (%s, %s, 'usage', %s, NOW())
            """, (user_id, -file_cost, f"Fayl konvertatsiyasi: {file.filename}"))
            
        # Proceed with Upload
        job_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1].lower()
        
        if ext not in [".doc", ".docx"]:
            raise HTTPException(status_code=400, detail="Faqat .doc va .docx fayllar")
        
        input_filename = f"{job_id}{ext}"
        input_path = os.path.join(UPLOAD_DIR, input_filename)
        output_filename = f"{job_id}.txt"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        cur.execute("INSERT INTO jobs (id, filename, status, created_at, user_id, cost) VALUES (%s, %s, %s, %s, %s, %s)", 
                  (job_id, file.filename, "queued", datetime.datetime.now(), user_id, file_cost if not is_free_upload else 0))
        conn.commit()
    
        background_tasks.add_task(process_conversion, job_id, input_path, output_path, False, format)
        return {"job_id": job_id, "status": "queued"}
        
    except HTTPException as he:
        if conn: conn.rollback()
        raise he
    except Exception as e:
        conn.close()
    
    is_legacy = ext == ".doc"
    background_tasks.add_task(process_conversion, job_id, input_path, output_path, is_legacy, format)
    
    return {"job_id": job_id, "message": "Fayl yuklandi va konvertatsiya boshlandi"}

@app.get("/status/{job_id}")
async def check_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Topshiriq topilmadi")
    return job

@app.get("/download/{job_id}")
async def download_file(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Topshiriq topilmadi")
        
    if job['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Fayl hali tayyor emas")
        
    output_filename = f"{job_id}.txt"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    if not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail="Natija fayli topilmadi")
        
    return FileResponse(output_path, media_type='text/plain', filename=f"{os.path.splitext(job['filename'])[0]}.txt")

# --- Payment Endpoints ---

class PaymentRequest(BaseModel):
    transaction_id: str
    image: str # Base64 string
    tariff_id: Optional[int] = None
    amount: Optional[int] = 0

@app.post("/api/pay")
async def create_payment_request(
    payload: PaymentRequest,
    current_user: dict = Depends(get_current_active_user)
):
    try:
        # Decode Base64
        if "," in payload.image:
            header, encoded = payload.image.split(",", 1)
        else:
            encoded = payload.image
            
        file_data = base64.b64decode(encoded)
        filename = f"receipt_{uuid.uuid4()}.png" 
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        with open(file_path, "wb") as f:
            f.write(file_data)
            
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO payment_requests (user_id, receipt_img, transaction_id, status, tariff_id, declared_amount)
            VALUES (%s, %s, %s, 'pending', %s, %s)
            RETURNING id
        """, (current_user["id"], filename, payload.transaction_id, payload.tariff_id, payload.amount))
        conn.commit()
        
        # message construction
        msg = "To'lov cheki yuborildi. Admin tasdiqlashini kuting."
        if payload.tariff_id:
             cur.execute("SELECT name FROM tariffs WHERE id = %s", (payload.tariff_id,))
             t = cur.fetchone()
             if t:
                 msg = f"To'lov yuborildi. Admin tasdiqlashi bilan '{t[0]}' tarifi AVTOMATIK faollashadi."

        cur.close()
        conn.close()
        return {"status": "success", "message": msg}
        
    except Exception as e:
        logger.error(f"Payment upload failed: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")

@app.get("/api/admin/payments")
async def get_payment_requests(current_user: dict = Depends(get_current_admin_user)):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT p.*, u.full_name, u.email, t.name as tariff_name, t.price as tariff_price, p.declared_amount
            FROM payment_requests p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN tariffs t ON p.tariff_id = t.id
            ORDER BY p.created_at DESC
        """)
        payments = cur.fetchall()
        cur.close()
        return payments
    except Exception as e:
        logger.error(f"Error fetching payments: {e}")
        return []
    finally:
        conn.close()

class PaymentDecision(BaseModel):
    status: str 
    amount: int = 0
    note: Optional[str] = None
    
@app.post("/api/admin/payments/{id}/decide")
async def decide_payment(
    id: int, 
    decision: PaymentDecision,
    current_user: dict = Depends(get_current_admin_user)
):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT user_id, status, tariff_id FROM payment_requests WHERE id = %s", (id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="To'lov topilmadi")
        
        user_id = row['user_id']
        current_status = row['status']
        requested_tariff_id = row['tariff_id']

        if current_status != 'pending':
            raise HTTPException(status_code=400, detail="Bu to'lov allaqachon ko'rib chiqilgan")

        cur.execute("""
            UPDATE payment_requests 
            SET status = %s, admin_note = %s
            WHERE id = %s
        """, (decision.status, decision.note, id))
        
        if decision.status == 'approved' and decision.amount > 0:
            # 1. Credit Balance
            cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s RETURNING balance", (decision.amount, user_id))
            updated_user = cur.fetchone()
            current_balance = updated_user['balance']

            cur.execute("""
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (%s, %s, 'credit', 'Payment Approved via Receipt')
            """, (user_id, decision.amount))
            
            # 2. Check for Auto-Activation of Tariff
            if requested_tariff_id:
                cur.execute("SELECT * FROM tariffs WHERE id = %s", (requested_tariff_id,))
                tariff = cur.fetchone()
                
                if tariff and tariff['is_active'] and current_balance >= tariff['price']:
                    # Auto-Purchase
                    new_balance = current_balance - tariff['price']
                    expires_at = datetime.datetime.now() + datetime.timedelta(days=tariff['duration_days'])
                    
                    cur.execute("""
                        UPDATE users 
                        SET balance = %s, tariff_id = %s, tariff_expires_at = %s, last_tariff_change_at = NOW()
                        WHERE id = %s
                    """, (new_balance, tariff['id'], expires_at, user_id))
                    
                    cur.execute("""
                        INSERT INTO transactions (user_id, amount, type, description)
                        VALUES (%s, %s, 'debit', %s)
                    """, (user_id, -tariff['price'], f"Auto-Activated: {tariff['name']}"))
            
        conn.commit()
        cur.close()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        logger.error(f"Payment decision failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/tariffs/buy/{id}")
async def buy_tariff(id: int, current_user: dict = Depends(get_current_active_user)):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get Tariff
        cur.execute("SELECT * FROM tariffs WHERE id = %s", (id,))
        tariff = cur.fetchone()
        
        if not tariff:
            raise HTTPException(status_code=404, detail="Tarif topilmadi")
            
        if not tariff['is_active']:
             raise HTTPException(status_code=400, detail="Bu tarif aktiv emas")
             
        # Check Balance
        if current_user['balance'] < tariff['price']:
             raise HTTPException(status_code=400, detail="Balans yetarli emas")
             
        # Process Purchase
        new_balance = current_user['balance'] - tariff['price']
        expires_at = datetime.datetime.now() + datetime.timedelta(days=tariff['duration_days'])
        
        # 1. Deduct Balance & Update Tariff
        cur.execute("""
            UPDATE users 
            SET balance = %s, tariff_id = %s, tariff_expires_at = %s, last_tariff_change_at = NOW()
            WHERE id = %s
        """, (new_balance, id, expires_at, current_user['id']))
        
        # 2. Record Transaction
        cur.execute("""
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (%s, %s, 'debit', %s)
        """, (current_user['id'], -tariff['price'], f"Tarif sotib olindi: {tariff['name']}"))
        
        conn.commit()
        cur.close()
        
        return {
            "status": "success", 
            "message": f"{tariff['name']} tarifi muvaffaqiyatli sotib olindi",
            "new_balance": new_balance,
            "tariff": tariff['name'],
            "expires_at": expires_at.isoformat()
        }
        
    except HTTPException as he:
        conn.rollback()
        raise he
    except Exception as e:
        conn.rollback()
        logger.error(f"Tarif purchase failed: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
