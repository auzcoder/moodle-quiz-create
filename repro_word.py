import os
import sys
import pythoncom
import win32com.client
import time
import shutil
import tempfile

def test_word_conversion(input_path):
    abs_input_path = os.path.abspath(input_path)
    filename = os.path.splitext(os.path.basename(abs_input_path))[0]
    
    # Create a temp dir
    temp_dir = tempfile.mkdtemp()
    temp_input_path = os.path.join(temp_dir, os.path.basename(abs_input_path))
    temp_output_path = os.path.join(temp_dir, f"{filename}.htm")
    
    print(f"Original Input: {abs_input_path}")
    print(f"Temp Input: {temp_input_path}")
    
    shutil.copy2(abs_input_path, temp_input_path)
    
    word = None
    try:
        pythoncom.CoInitialize()
        # Use EnsureDispatch
        try:
            word = win32com.client.gencache.EnsureDispatch("Word.Application")
        except:
            word = win32com.client.Dispatch("Word.Application")
            
        word.Visible = False
        word.DisplayAlerts = 0 
        
        print("Opening document (from temp)...")
        doc = word.Documents.Open(FileName=temp_input_path, ReadOnly=True, Visible=False)
        
        # Check Protected View again just in case moving it helped or not
        if word.ProtectedViewWindows.Count > 0:
             print("Protected View detected (even in temp). Enabling editing...")
             pv = word.ProtectedViewWindows(1)
             doc = pv.Edit()

        print("Saving as Filtered HTML...")
        doc.SaveAs2(FileName=temp_output_path, FileFormat=10)
        print("SaveAs2 success!")
        
        doc.Close(SaveChanges=False)
        print("Success!")
        
        # Verify output exists
        if os.path.exists(temp_output_path):
            print(f"Output generated at: {temp_output_path}")
        else:
            print("Output file NOT found.")

    except Exception as e:
        print(f"ERROR MAIN: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if word:
            try:
                word.Quit()
            except:
                pass
        pythoncom.CoUninitialize()
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_word_conversion(sys.argv[1])
    else:
        print("Please provide a file path")
