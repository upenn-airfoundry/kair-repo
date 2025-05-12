# Disclaimer: This script is meant to be temporary and is not fully checked!
import os
import sys
import argparse
from pathlib import Path
import requests
import time

project_root = os.path.dirname(os.path.abspath(__file__))

sys.path.append(os.path.join(project_root, 's2orc-doc2json'))
sys.path.append(os.path.join(project_root, 'grobid'))

from doc2json.grobid2json.process_pdf import process_pdf_file
from doc2json.grobid2json.grobid.grobid_client import GrobidClient

def is_grobid_running():
    """Check if Grobid server is running"""
    try:
        response = requests.get('http://localhost:8070/api/isalive')
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False

def setup_grobid():
    """Setup and start Grobid server"""
    if not is_grobid_running():
        print("Starting Grobid server...")
        grobid_path = os.path.join(project_root, 'grobid')
        os.system(f"cd {grobid_path} && ./gradlew run")
        
        print("Waiting for Grobid server to start...")
        for _ in range(30):  # Wait up to 30 seconds
            if is_grobid_running():
                print("Grobid server is running!")
                break
            time.sleep(1)
        else:
            raise Exception("Failed to start Grobid server after 30 seconds")
    
    return GrobidClient()

def process_pdf_to_json(input_pdf, output_dir, temp_dir=None):
    """
    Process a PDF file and convert it to JSON format
    
    Args:
        input_pdf (str): Path to input PDF file
        output_dir (str): Directory to save output JSON
        temp_dir (str, optional): Directory for temporary files
    """
    if temp_dir is None:
        temp_dir = "temp"
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    grobid_client = setup_grobid()
    
    try:
        result = process_pdf_file(
            input_file=input_pdf,
            output_dir=output_dir,
            temp_dir=temp_dir
        )
        print(f"Successfully processed {input_pdf}")
        print(f"Output saved to {output_dir}")
        return result
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PDF to JSON using Grobid and s2orc-doc2json")
    parser.add_argument("-i", "--input", required=True, help="Input PDF file path")
    parser.add_argument("-o", "--output", required=True, help="Output directory for JSON files")
    parser.add_argument("-t", "--temp", help="Temporary directory for processing")
    
    args = parser.parse_args()
    
    process_pdf_to_json(args.input, args.output, args.temp)