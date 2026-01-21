@echo off
cd /d "%~dp0"

if exist "..\venv\Scripts\activate.bat" (
    call "..\venv\Scripts\activate.bat"
) else (
    echo Virtual environment not found in parent directory. Creating one...
    python -m venv ..\venv
    call "..\venv\Scripts\activate.bat"
)

echo Installing requirements...
pip install -r requirements.txt

echo Starting server...
echo Access the app at http://127.0.0.1:8000
uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
