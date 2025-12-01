import os
import re
import fitz  # PyMuPDF
import logging

# Configure logging
logging.basicConfig(filename='rename_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

def extract_date_from_pdf(pdf_path):
    """Extracts the first date in YYYY/MM/DD format found in the PDF text."""
    try:
        with fitz.open(pdf_path) as doc:
            text = "".join(page.get_text() for page in doc)
        match = re.search(r'\d{4}/\d{2}/\d{2}', text)
        return match.group(0) if match else None
    except Exception as e:
        logging.error(f"Error reading {pdf_path}: {e}")
        return None

def rename_invoices(folder_path):
    """Renames all PDF files in the folder to 'YYYY-MM-DD AliExpress <invoice_number>.pdf'."""
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            # Skip files already renamed (start with YYYY-MM-DD)
            if re.match(r'^\d{4}-\d{2}-\d{2}', filename):
                logging.info(f"Skipping already renamed file: {filename}")
                print(f"Skipping: {filename}")
                continue

            old_path = os.path.join(folder_path, filename)
            invoice_number = filename.split('_')[0]
            invoice_date = extract_date_from_pdf(old_path)

            if invoice_date:
                formatted_date = invoice_date.replace('/', '-')
                new_filename = f"{formatted_date} AliExpress {invoice_number}.pdf"
                new_path = os.path.join(folder_path, new_filename)
                try:
                    os.rename(old_path, new_path)
                    logging.info(f"Renamed: {filename} -> {new_filename}")
                    print(f"Renamed: {filename} -> {new_filename}")
                except Exception as e:
                    logging.error(f"Failed to rename {filename}: {e}")
            else:
                logging.warning(f"No date found in {filename}. Skipping.")
                print(f"No date found in {filename}. Skipping.")

# Example usage:
rename_invoices('.')
