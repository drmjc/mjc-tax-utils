#!/usr/bin/env python3
# Process a folder of AliExpress invoice PDFs and create a spreadsheet
#
# usage:
#   python aggregate_aliexpress_invoices.py /path/to/folder [output.xlsx]
#   python aggregate_aliexpress_invoices.py --by-fy /path/to/folder [output_dir]
#
# options:
#   --by-fy          Create one XLSX per financial year (FY spans Jul 1 - Jun 30)
#
# author:
# Mark Cowley, 2025-12-01

import os
import sys
import glob
import argparse
import pandas as pd
from datetime import datetime
from aliexpress2json import extract_invoice_data

def get_financial_year(date_str):
    """Determine the financial year (Jul 1 - Jun 30) for a given date.
    Returns the year at the END of the interval.
    E.g., Jul 1 2024 - Jun 30 2025 -> FY2025
    """
    try:
        date = pd.to_datetime(date_str)
        year = date.year
        # If month is Jan-Jun, FY ends in current year
        if date.month < 7:
            fy = year
        else:
            # If month is Jul-Dec, FY ends in next year
            fy = year + 1
        return fy
    except Exception:
        return None

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

def process_folder_by_fy(folder_path, output_dir=None):
    """Process all PDF files in a folder and create separate spreadsheets per financial year."""
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        sys.exit(1)
    
    if not output_dir:
        output_dir = folder_path
    
    os.makedirs(output_dir, exist_ok=True)
    
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
    
    # Convert invoice date to datetime
    if "Invoice Date" in df.columns:
        df["Invoice Date"] = pd.to_datetime(df["Invoice Date"], errors="coerce")
    
    # Add Financial Year column
    df["Financial Year"] = df["Invoice Date"].apply(lambda x: get_financial_year(x) if pd.notna(x) else None)
    
    # Group by financial year and create separate Excel files
    fy_groups = df.groupby("Financial Year", sort=True)
    
    print("\nCreating per-financial-year spreadsheets:")
    
    for fy, fy_df in fy_groups:
        if pd.isna(fy):
            print(f"  Skipping items with invalid dates")
            continue
        
        fy = int(fy)
        fy_df = fy_df.copy()
        
        # Sort by date, then by invoice number
        sort_columns = ["Invoice Date"]
        if "Invoice Number" in fy_df.columns:
            sort_columns.append("Invoice Number")
        fy_df = fy_df.sort_values(sort_columns, na_position="last")
        
        # Convert date back to string for display
        fy_df["Invoice Date"] = fy_df["Invoice Date"].dt.strftime("%Y-%m-%d")
        
        # Drop the Financial Year column before saving
        fy_df = fy_df.drop(columns=["Financial Year"])
        
        # Create output filename: AliExpress Transactions FY2025.xlsx
        output_file = os.path.join(output_dir, f"AliExpress Transactions FY{fy}.xlsx")
        fy_df.to_excel(output_file, sheet_name="transactions", index=False)
        
        print(f"  ✓ FY{fy} ({fy_df['Invoice Date'].min()} to {fy_df['Invoice Date'].max()})")
        print(f"    {output_file}")
        print(f"    Total items: {len(fy_df)}, Total invoices: {fy_df['Invoice Number'].nunique()}")
    
    if errors:
        print(f"\n⚠ {len(errors)} error(s) encountered:")
        for error in errors:
            print(f"  - {error}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process AliExpress invoice PDFs and create a spreadsheet",
        prog="aggregate_aliexpress_invoices.py"
    )
    
    parser.add_argument(
        "folder",
        help="Path to folder containing AliExpress invoice PDFs"
    )
    
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file or directory (default: aliexpress_transactions.xlsx in folder)"
    )
    
    parser.add_argument(
        "--by-fy",
        action="store_true",
        help="Create one XLSX per financial year (FY spans Jul 1 - Jun 30)"
    )
    
    args = parser.parse_args()
    
    if args.by_fy:
        process_folder_by_fy(args.folder, args.output)
    else:
        process_folder(args.folder, args.output)

