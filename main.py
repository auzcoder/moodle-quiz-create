import os
import uuid
import asyncio
import shutil
import datetime
import logging
import tempfile
from typing import Optional

# Postgres & Env
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
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
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Jobs Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT,
                status TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Verification Codes Table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

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
            
        hashed_pw = get_password_hash(user.password)
        
        # Insert User (Unverified)
        cur.execute("""
            INSERT INTO users (full_name, email, phone, password_hash, is_verified)
            VALUES (%s, %s, %s, %s, FALSE)
            RETURNING id
        """, (user.full_name, user.email, user.phone, hashed_pw))
        
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
        # Background task would be better, but for simplicity:
        email_sent = send_verification_email(user.email, code)
        if not email_sent:
             logger.warning("Email sending failed")
             # don't fail registration, user can resend
        
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
        
        cur.execute("SELECT code, expires_at FROM verification_codes WHERE email = %s", (data.email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="Kod topilmadi yoki muddati tugagan")
            
        code, expires = row
        
        if code != data.code:
             raise HTTPException(status_code=400, detail="Noto'g'ri kod")
             
        if datetime.datetime.now() > expires:
             raise HTTPException(status_code=400, detail="Kod muddati tugagan")
             
        # Mark user verified
        cur.execute("UPDATE users SET is_verified = TRUE WHERE email = %s", (data.email,))
        
        # Delete code
        cur.execute("DELETE FROM verification_codes WHERE email = %s", (data.email,))
        
        conn.commit()
        cur.close()
        
        return {"message": "Email tasdiqlandi. Endi kirishingiz mumkin."}
        
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
        
        # Check cooldown (2 mins)
        cur.execute("SELECT created_at FROM verification_codes WHERE email = %s", (data.email,))
        row = cur.fetchone()
        
        if row:
            created_at = row[0]
            if datetime.datetime.now() < created_at + datetime.timedelta(minutes=2):
                 remaining = (created_at + datetime.timedelta(minutes=2) - datetime.datetime.now()).seconds
                 raise HTTPException(status_code=400, detail=f"Iltimos, {remaining} soniya kuting")
        
        code = str(random.randint(1000, 9999))
        expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
        
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
        logger.error(f"Resend error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

@app.post("/auth/login")
async def login(user: UserLogin):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT id, full_name, password_hash, is_verified FROM users WHERE email = %s", (user.email,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="Email yoki parol noto'g'ri")
            
        user_id, full_name, pw_hash, is_verified = row
        
        if not verify_password(user.password, pw_hash):
             raise HTTPException(status_code=400, detail="Email yoki parol noto'g'ri")
             
        if not is_verified:
             raise HTTPException(status_code=400, detail="Email tasdiqlanmagan. Iltimos avval tasdiqlang")
             
        # Generate Token
        token = create_access_token({"sub": user.email, "user_id": user_id, "name": full_name})
        
        return {"access_token": token, "token_type": "bearer", "user": {"full_name": full_name, "email": user.email}}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Server xatoligi")
    finally:
        conn.close()

# --- Helpers ---
def update_job_status(job_id: str, status: str, message: str = ""):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
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

def convert_to_gift(input_path: str, output_path: str):
    """
    Converts Word Doc/Docx -> Filtered HTML -> GIFT Format .txt
    Supports Windows (MS Word) and Linux (LibreOffice).
    """
    abs_input_path = os.path.abspath(input_path)
    # We will work inside a temporary directory to avoid OneDrive file locking/sync issues
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy input file to temp dir
        filename_ext = os.path.basename(abs_input_path)
        filename = os.path.splitext(filename_ext)[0]
        temp_input_path = os.path.join(temp_dir, filename_ext)
        shutil.copy2(abs_input_path, temp_input_path)
        
        base_dir = temp_dir
        
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
            new_text = original_text
            new_text = new_text.replace("ù", "")
            if "<" in new_text: new_text = new_text.replace("<", "&lt;")
            if ">" in new_text: new_text = new_text.replace(">", "&gt;")
            
            # GIFT Escaping
            if "{" in new_text: new_text = new_text.replace("{", "\\{")
            if "}" in new_text: new_text = new_text.replace("}", "\\}")
            if "=" in new_text: new_text = new_text.replace("=", "\\=")
            if "~" in new_text: new_text = new_text.replace("~", "\\~")
            
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
                        encoded_string = base64.b64encode(raw_data).decode("utf-8").replace("\n", "").replace("\r", "").replace("=", "\\=")
                        
                        mime_type = "image/png"
                        if image_full_path.lower().endswith((".jpg", ".jpeg")):
                            mime_type = "image/jpeg"
                        elif image_full_path.lower().endswith(".gif"):
                             mime_type = "image/gif"
                        
                        code_string = f'<img src\\="data:{mime_type};base64,{encoded_string}">'
                        img.replace_with(code_string)
                except Exception as e:
                    logger.warning(f"Could not encode image: {e}")

        # 3. Extract Q&A from Tables
        output_lines = []
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
                    
                block = []
                block.append(f"::{question_text}{{")
                block.append(f"={correct_answer}")
                for i in range(3, len(cells)):
                    alt_text = get_cell_text(cells[i])
                    if alt_text:
                        block.append(f"~{alt_text}")
                block.append("}")
                output_lines.append("\n".join(block))
                output_lines.append("")

        # Write final output to the real output path
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))

async def process_conversion(job_id: str, input_path: str, output_path: str, is_legacy: bool):
    try:
        update_job_status(job_id, "processing", "Konvertatsiya boshlandi...")
        
        # Always use the custom logic for both doc and docx
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, convert_to_gift, input_path, output_path)
            
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
async def read_root():
    return FileResponse('static/index.html')

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    job_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in [".doc", ".docx"]:
        raise HTTPException(status_code=400, detail="Faqat .doc va .docx fayllar qo'llab-quvvatlanadi")
    
    input_filename = f"{job_id}{ext}"
    input_path = os.path.join(UPLOAD_DIR, input_filename)
    output_filename = f"{job_id}.txt"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # Save uploaded file
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Create DB entry
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO jobs (id, filename, status, created_at) VALUES (%s, %s, %s, %s)", 
                  (job_id, file.filename, "queued", datetime.datetime.now()))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        conn.close()
    
    is_legacy = ext == ".doc"
    background_tasks.add_task(process_conversion, job_id, input_path, output_path, is_legacy)
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
