#!/usr/bin/env python3
# Process a folder of AliExpress invoice PDFs and create a spreadsheet
#
# usage:
# python aggregate_aliexpress_invoices.py /path/to/folder [output.xlsx]
#
# author:
# Mark Cowley, 2025-12-01

import os
import sys
import glob
import pandas as pd
from datetime import datetime
from aliexpress2json import extract_invoice_data

def process_folder(folder_path, output_file=None):
    """Process all PDF files in a folder and create a spreadsheet."""
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        sys.exit(1)
    
    # Find all PDF files
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    pdf_files = [f for f in pdf_files if os.path.isfile(f)]
    
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    
    all_items = []
    errors = []
    
    # Process each PDF
    for pdf_path in sorted(pdf_files):
        filename = os.path.basename(pdf_path)
        print(f"Processing: {filename}...", end=" ")
        
        try:
            data = extract_invoice_data(pdf_path)
            
            if not data.get("items"):
                print(f"WARNING: No items found")
                errors.append(f"{filename}: No items found")
                continue
            
            # Add all items to the list
            all_items.extend(data["items"])
            print(f"✓ {len(data['items'])} item(s)")
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            errors.append(f"{filename}: {str(e)}")
            continue
    
    if not all_items:
        print("\nNo items found in any PDF files.")
        if errors:
            print("\nErrors encountered:")
            for error in errors:
                print(f"  - {error}")
        sys.exit(1)
    
    # Create DataFrame
    df = pd.DataFrame(all_items)
    
    # Sort by invoice date (oldest to newest), then by invoice number for consistency
    if "Invoice Date" in df.columns:
        # Convert to datetime for proper sorting
        df["Invoice Date"] = pd.to_datetime(df["Invoice Date"], errors="coerce")
        # Sort by date, then by invoice number
        sort_columns = ["Invoice Date"]
        if "Invoice Number" in df.columns:
            sort_columns.append("Invoice Number")
        df = df.sort_values(sort_columns, na_position="last")
        # Convert back to string format for display
        df["Invoice Date"] = df["Invoice Date"].dt.strftime("%Y-%m-%d")
    
    # Determine output file
    if not output_file:
        output_file = os.path.join(folder_path, "aliexpress_transactions.xlsx")
    
    # Save to Excel
    df.to_excel(output_file, sheet_name="transactions", index=False)
    
    print(f"\n✓ Spreadsheet created: {output_file}")
    print(f"  Total items: {len(df)}")
    print(f"  Total invoices: {df['Invoice Number'].nunique()}")
    
    if errors:
        print(f"\n⚠ {len(errors)} error(s) encountered:")
        for error in errors:
            print(f"  - {error}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aggregate_aliexpress_invoices.py /path/to/folder [output.xlsx]")
        sys.exit(1)
    
    folder_path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    process_folder(folder_path, output_file)

