import os
import uuid
import asyncio
import shutil
import sqlite3
import datetime
import logging
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Configuration ---
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
DB_FILE = "jobs.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            filename TEXT,
            status TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

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

# --- Models ---
class JobStatus(BaseModel):
    id: str
    filename: str
    status: str
    message: Optional[str] = None
    created_at: str

# --- Helpers ---
def update_job_status(job_id: str, status: str, message: str = ""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = ?, message = ? WHERE id = ?", (status, message, job_id))
    conn.commit()
    conn.close()

def get_job(job_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, filename, status, message, created_at FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "filename": row[1],
            "status": row[2],
            "message": row[3],
            "created_at": row[4]
        }
    return None

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
    base_dir = os.path.dirname(abs_input_path)
    filename = os.path.splitext(os.path.basename(abs_input_path))[0]
    
    # We target .htm or .html
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
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0 
                
                # Open ReadOnly to minimize errors
                doc = word.Documents.Open(FileName=abs_input_path, ReadOnly=True, Visible=False)
                
                # Use SaveAs2 for better compatibility
                # Ensure path is normalized
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
        # Requires: sudo apt install libreoffice (on Ubuntu/Debian)
        logger.info("Running on non-Windows OS. Trying LibreOffice...")
        try:
            # --convert-to html:HTML (generic HTML) --outdir ...
            # LibreOffice usually outputs .html
            cmd = [
                "libreoffice", 
                "--headless", 
                "--convert-to", 
                "html", 
                "--outdir", 
                base_dir, 
                abs_input_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # LibreOffice typically saves as .html, let's normalize check
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
            
            question_text = get_cell_text(cells[1])
            correct_answer = get_cell_text(cells[2])
            
            if not question_text and not correct_answer: continue

            # Skip header rows
            # Check for common header terms in Uzbek or English (Column 2)
            q_lower = question_text.lower()
            if "savol" in q_lower or "question" in q_lower or "to'g'ri javob" in q_lower:
                continue
                
            # Note: We intentionally ignore Column 1 (cells[0]) as per user request.

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

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    # Cleanup HTM files (Optional, maybe keep for debug?)
    # try:
    #     os.remove(htm_path)
    #     shutil.rmtree(files_dir, ignore_errors=True)
    # except:
    #     pass

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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO jobs (id, filename, status, created_at) VALUES (?, ?, ?, ?)", 
              (job_id, file.filename, "queued", datetime.datetime.now()))
    conn.commit()
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
