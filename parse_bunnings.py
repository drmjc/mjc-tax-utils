import PyPDF2
import csv
import os
import sys
import re

"""
This script extracts the items data from Bunnings invoices (PDF) into a spreadsheet, to assist with tax returns.

1. login to your Powerpass account (https://trade.bunnings.com.au/powerpass)
2. select 1 or more invoices to download into a PDF file(s). Save these all in one folder
3. Download this script into the folder with your PDF files
4. create your virtual environment & install PyPDF2
    python3 -m venv path/to/venv
    source path/to/venv/bin/activate
    python3 -m pip install PyPDF2
5. run `python3 parse_bunnings.py "my bunnings invoices.pdf"`
6. if you have lots of PDF files, then run the script on all of the PDF files in a given folder:
    `for pdf in *pdf; do python3 parse_bunnings.py "${pdf}"; done`

# output
It creates a CSV file with the same name as the PDF file (s/pdf/csv/) and with the same headings as the items table in the PDF file. 
It also adds the invoice date as a column.

Limitations
1. it skips invoices that are 'adjustments', ie refunds, as the PDF format is slighly different (there's never a Discount column)
2. sometimes the description wraps across two lines, and messes up the delimiters, so in these cases the Description will be slighly truncated (see add_space_after_seventh_char)
3. i'm not sure if this works with a regular Bunnings account?

Author
Mark Cowley, 2025-01-07

LICENSE: MIT

"""
def replace_EACH(text):
    # in some cases, there is not a space separating two fields
    # Use regular expression to find patterns like '1EACH', '2EACH', etc.
    pattern = re.compile(r'(\d)EACH')
    # Replace the pattern with '1 EACH', '2 EACH', etc.
    return pattern.sub(r'\1 EACH', text)

def replace_PROMO(text):
    # in some cases, there is not a space separating two fields
    # Use regular expression to find patterns like '3.25PROMO', etc.
    pattern = re.compile(r'(\d)PROMO')
    # Replace the pattern with '3.25 PROMO', etc.
    return pattern.sub(r'\1 PROMO', text)

def is_float(value):
    # check that a number is valid, including those with commas, eg 1,234.56
    try:
        # Remove commas from the string
        value = value.replace(',', '')
        float(value)
        return True
    except ValueError:
        return False

def add_space_after_seventh_char(s):
    # If a Description wraps across 2 lines, the first value is often a 7 character string, with no space, then the 'Your price'
    # eg "CBM774542.37" which should be "CBM7745 42.37"
    if len(s) > 7:
        return s[:7] + ' ' + s[7:]
    return s

def extract_table_from_pdf(pdf_path):
    # Automatically name the output CSV file based on the input PDF file name
    csv_path = os.path.splitext(pdf_path)[0] + '.csv'
    
    headings = ["Invoice Date", "Item", "Quantity", "Unit", "Description", "Your Price", "Discount", "Amount ex GST", "GST", "Total Price"]
    # Open the PDF file
    with open(pdf_path, 'rb') as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        num_pages = len(reader.pages)
        
        # Initialize a list to hold the table rows
        table_rows = []
        invoice_date = None
        
        table_rows.append(headings)
        
        # Iterate through each page
        for page_num in range(num_pages):
            page = reader.pages[page_num]
            text = page.extract_text()
            
            # Split the text into lines
            lines = text.split('\n')
            i = 0
            
            while i < len(lines):
                line = lines[i]
                if 'invoice date' in line.lower():
                    invoice_date = line.split()[-1]  # Save the invoice date as a variable
                if 'adjustment date' in line.lower():
                    print(f"Skipping page: is a refund/tax adjustment")
                    break

                line = replace_EACH(line)
                line = replace_PROMO(line)

                if 'EACH' in line:
                    columns = line.split()  # Split on spaces
                    
                    # Check if the last three columns are all numbers...
                    # if they are not, then the description wraps onto 2 lines,
                    # which should be concatenated
                    if len(columns) >= 3 and not all(is_float(col) for col in columns[-3:]):
                        if i + 1 < len(lines):
                            # usually there's a missing space delimiter between the first 2 fields
                            line += ' ' + add_space_after_seventh_char(lines[i + 1])
                            columns = line.split()
                            i += 1  # Skip the next line as it has been concatenated
                    
                    # Ensure there are at least 9 columns
                    if len(columns) >= 1:
                        # Replace "NETT" with "0%" in the 4th last column
                        if len(columns) >= 4 and columns[-4] in ["NETT", "PROMO"]:
                            columns[-4] = "0%"
                        # when 'add_space_after_seventh_char()' doesn't fix the line wrapping, just replace these values; they're always the same anyway.
                        columns[-5] = columns[-1]
                        # craete a Description by joining all the middle columns
                        row = columns[:3] + [' '.join(columns[3:-5])] + columns[-5:]
                        if invoice_date:
                            row.insert(0, invoice_date)  # Insert invoice date as the first column
                        table_rows.append(row)
                i += 1
    
    # Write the table rows to a CSV file
    with open(csv_path, 'w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(table_rows)

    print(f"Table rows from {pdf_path} have been extracted to {csv_path}.")

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 script.py <input_pdf_file>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    extract_table_from_pdf(pdf_path)

if __name__ == "__main__":
    main()
