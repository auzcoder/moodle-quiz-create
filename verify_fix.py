import os
import shutil
from main import convert_to_gift
import logging

# Setup logging to see output
logging.basicConfig(level=logging.INFO)

def test_fix():
    # Use the known problematic file
    input_file = "uploads/2fae06ed-c35d-4377-84c6-2800878e4e6d.docx"
    output_file = "test_output_gift.txt"
    
    abs_input = os.path.abspath(input_file)
    abs_output = os.path.abspath(output_file)
    
    print(f"Testing conversion of: {abs_input}")
    
    try:
        convert_to_gift(abs_input, abs_output)
        print("Conversion successful!")
        
        if os.path.exists(abs_output):
            print(f"Output file created: {abs_output}")
            with open(abs_output, 'r', encoding='utf-8') as f:
                print("First 5 lines of output:")
                for _ in range(5):
                    print(f.readline().strip())
        else:
            print("Error: Output file not found!")
            
    except Exception as e:
        print(f"Conversion FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fix()
