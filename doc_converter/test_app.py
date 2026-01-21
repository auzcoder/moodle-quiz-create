
import os
import time
import shutil
import sys
from fastapi.testclient import TestClient
from main import app, DB_FILE, OUTPUT_DIR
import win32com.client
import pythoncom

client = TestClient(app)

# Ensure clean state
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    from main import init_db
    init_db()

def create_dummy_docx(filename):
    pythoncom.CoInitialize()
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Add()
    
    range_ = doc.Range(0, 0)
    table = doc.Tables.Add(range_, NumRows=2, NumColumns=4)
    
    table.Cell(2, 2).Range.Text = "What is 2+2?"
    table.Cell(2, 3).Range.Text = "4"
    table.Cell(2, 4).Range.Text = "5"
    
    folder = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(folder, filename)
    
    if os.path.exists(path):
        os.remove(path)
        
    doc.SaveAs(path)
    doc.Close()
    word.Quit()

def test_upload_and_conversion():
    filename = "test_gift.docx"
    try:
        create_dummy_docx(filename)
    except Exception as e:
        print(f"SKIPPING: Could not create docx (no Word installed?): {e}")
        return
    
    try:
        with open(filename, "rb") as f:
            response = client.post("/upload", files={"file": (filename, f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        job_id = data["job_id"]
        
        # Poll for status
        status_data = None
        for _ in range(20):
            response = client.get(f"/status/{job_id}")
            status_data = response.json()
            if status_data["status"] == "completed":
                break
            elif status_data["status"] == "error":
                raise Exception(f"Conversion failed: {status_data['message']}")
            time.sleep(1)
            
        assert status_data["status"] == "completed", f"Status not completed: {status_data}"
        
        # Download
        response = client.get(f"/download/{job_id}")
        assert response.status_code == 200, "Download failed"
        content = response.content.decode("utf-8")
        
        print(f"DEBUG CONTENT: {content}")

        assert "::What is 2+2?{" in content, "Missing Question format"
        assert "=4" in content, "Missing correct answer"
        assert "~5" in content, "Missing distractor"
        assert "}" in content, "Missing closing brace"
        
        print("Success!")
        
    finally:
        # Cleanup
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass

if __name__ == "__main__":
    try:
        test_upload_and_conversion()
        print("Test Script Finished Successfully.")
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()

