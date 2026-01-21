import os
import sys
import base64
import win32com.client
from bs4 import BeautifulSoup
import time
import re

# ==========================================
# SOZLAMALAR (SETTINGS)
# ==========================================
DOCX_FILE_PATH = r"C:\Users\auzof\Desktop\Projects\macros\word\60540100-Matematika.docx"

def convert_word_to_custom_text(docx_path):
    """
    1. Converts Word -> Filtered HTML (for image formulas).
    2. Parses the HTML Table.
    3. Formats as:
       ::Question{
       =Correct
       ~Wrong1
       ~Wrong2
       }
    4. Images are embedded as <img src="data:..."> strings.
    """
    abs_docx_path = os.path.abspath(docx_path)
    if not os.path.exists(abs_docx_path):
        print(f"Error: File not found: {abs_docx_path}")
        return

    base_dir = os.path.dirname(abs_docx_path)
    filename = os.path.splitext(os.path.basename(abs_docx_path))[0]
    htm_path = os.path.join(base_dir, f"{filename}.htm")
    files_dir = os.path.join(base_dir, f"{filename}_files")
    
    # Output file
    output_filename = f"{filename}_converted.txt"
    output_path = os.path.join(base_dir, output_filename)

    print(f"Processing: {abs_docx_path}")

    # ==================================================================================
    # STEP 1: Formula & Document Conversion (Word -> HTML)
    # ==================================================================================
    print(" - Step 1: Converting Word to HTML (preserving formulas)...")
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # wdAlertsNone
        
        doc = word.Documents.Open(abs_docx_path)
        doc.SaveAs(htm_path, FileFormat=10) # 10 = wdFormatFilteredHTML
        doc.Close(SaveChanges=False)
        print("   Success: Document converted to HTML.")
    except Exception as e:
        print(f"   Error automating Word: {e}")
        return
    finally:
        if word:
            try:
                word.Quit()
            except:
                pass

    # ==================================================================================
    # STEP 2: Logic & Extraction
    # ==================================================================================
    print(" - Step 2: Extracting Rows and Images...")
    
    if not os.path.exists(htm_path):
        print("   Error: HTML file was not created.")
        return

    # Open as binary to let BS4 detect encoding (often UTF-8 or CP1252)
    with open(htm_path, "rb") as f:
        soup = BeautifulSoup(f, "html.parser")

    # --- 2a. Pre-process text (Escaping special chars & Cleaning) ---
    print("   Escaping text characters and cleaning...")
    # We iterate over all text nodes in the HTML soup *before* extracting the table.
    # This ensures that all content inside the table cells behaves correctly.
    for text_node in soup.find_all(string=True):
        if text_node.parent.name in ['script', 'style', 'title', 'meta']:
            continue
        
        # Skip our internally generated image placeholder spans if they already exist (though they shouldn't yet)
        if text_node.parent.name == 'span' and 'white-space: nowrap' in str(text_node.parent.get('style', '')):
             continue

        original_text = str(text_node)
        new_text = original_text
        
        # 1. CLEANING GARBAGE
        new_text = new_text.replace("ù", "") 

        # 2. HTML ENTITIES (Must be done first often, but here order is flexible)
        # Requirement: < -> &lt;, > -> &gt;
        # Note: We replace literal < with &lt;. BS4 might double-escape if we aren't careful, 
        # but replace_with on a string usually handles it. 
        # Actually BS4 automatically escapes < and > in text nodes to &lt; and &gt; when outputting HTML.
        # But for .get_text(), we want the literal string "&lt;" to appear in the text output file, 
        # so the Moodle importer sees the characters "&", "l", "t", ";".
        # If we just leave "<", Moodle might interpret it as a tag start.
        if "<" in new_text: new_text = new_text.replace("<", "&lt;")
        if ">" in new_text: new_text = new_text.replace(">", "&gt;")

        # 3. GIFT FORMAT ESCAPING
        # Requirement: { -> \{, } -> \}, = -> \=, ~ -> \~
        if "\\" in new_text:
             # Prevent double escaping if run multiple times? No, just simple replace.
             pass 
        
        if "{" in new_text: new_text = new_text.replace("{", "\\{")
        if "}" in new_text: new_text = new_text.replace("}", "\\}")
        if "=" in new_text: new_text = new_text.replace("=", "\\=")
        if "~" in new_text: new_text = new_text.replace("~", "\\~")
        
        # Apply changes if any
        if new_text != original_text:
            text_node.replace_with(new_text)

    # --- 2b. Convert Images to Base64 Strings ---
    print("   Converting images to Base64 strings...")
    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("src")
        if not src:
            continue
        
        # Check path
        image_full_path = os.path.join(base_dir, src)
        if not os.path.exists(image_full_path):
             # Try files dir fallback
            possible_name = os.path.basename(src)
            possible_path = os.path.join(files_dir, possible_name)
            if os.path.exists(possible_path):
                image_full_path = possible_path

        if os.path.exists(image_full_path):
            try:
                with open(image_full_path, "rb") as img_file:
                    raw_data = img_file.read()
                    # Encode and strip any internal newlines to guarantee single-line
                    # Also escape '=' characters in the base64 string itself (e.g. padding characters)
                    # to prevent Moodle from interpreting them as GIFT control characters.
                    encoded_string = base64.b64encode(raw_data).decode("utf-8").replace("\n", "").replace("\r", "").replace("=", "\\=")
                    
                    mime_type = "image/png"
                    if image_full_path.lower().endswith((".jpg", ".jpeg")):
                        mime_type = "image/jpeg"
                    elif image_full_path.lower().endswith(".gif"):
                         mime_type = "image/gif"
                    
                    # Create the code string. 
                    # Removing span wrapper as per user request.
                    # Escaping = in src attribute (src\=) is critical for GIFT.
                    code_string = f'<img src\\="data:{mime_type};base64,{encoded_string}">'
                    
                    # We replace the <img> tag with a simple string node (containing code).
                    # When 'get_text()' is called, it returns this string as-is.
                    img.replace_with(code_string)
            except Exception as e:
                print(f"   Warning: Could not encode image: {e}")
        else:
            # If image missing, maybe replace with placeholder or ignore
            pass

    # --- 2c. Iterate Tables and Extract Q&A ---
    print("   Processing Tables...")
    output_lines = []
    
    tables = soup.find_all("table")
    if not tables:
        print("   Warning: No tables found in document.")
    
    total_questions = 0
    
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            
            # User Format:
            # Col 1: ID (Skip)
            # Col 2: Question
            # Col 3: Correct Answer
            # Col 4+: Alternative Answers
            
            if len(cells) < 3:
                continue

            # Function to extract clean text + embedded image strings
            def get_cell_text(cell):
                # separator=' ' helps ensure block elements don't run together unexpectedly
                # strip=True removes leading/trailing whitespace
                text = cell.get_text(separator=' ', strip=True)
                # Cleanup extra spaces
                text = re.sub(r'\s+', ' ', text)
                return text

            question_text = get_cell_text(cells[1])
            correct_answer = get_cell_text(cells[2])
            
            # If question or answer is empty, skip (maybe empty row)
            if not question_text and not correct_answer:
                continue

            # Build the block
            # ::Question{
            block = []
            block.append(f"::{question_text}{{")
            
            # =Correct
            block.append(f"={correct_answer}")
            
            # ~Alternatives
            for i in range(3, len(cells)):
                alt_text = get_cell_text(cells[i])
                if alt_text: # Only add if not empty
                    block.append(f"~{alt_text}")
            
            # }
            block.append("}")
            
            # Add block to output with separation
            output_lines.append("\n".join(block))
            output_lines.append("") # Empty line after each question
            
            total_questions += 1

    # ==================================================================================
    # STEP 3: Save to TXT
    # ==================================================================================
    print(f"   Writing {total_questions} questions to file...")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n[DONE] Successfully created:\n{output_path}")

if __name__ == "__main__":
    target_file = None
    if DOCX_FILE_PATH and os.path.exists(DOCX_FILE_PATH):
        target_file = DOCX_FILE_PATH
    elif len(sys.argv) > 1:
        target_file = sys.argv[1]

    if target_file:
        convert_word_to_custom_text(target_file)
    else:
        print("Usage: python word_to_base64.py <path_to_docx>")
        path = input("Drag & Drop file: ").strip().strip('"')
        if path:
            convert_word_to_custom_text(path)
