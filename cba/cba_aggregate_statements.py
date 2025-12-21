#!/usr/bin/env python3
"""
Aggregate CBA statement TSV files into Excel spreadsheets.

Usage:
    python cba_aggregate_statements.py /path/to/folder [output.xlsx]
    python cba_aggregate_statements.py --fy /path/to/folder [output_dir]

Options:
    --fy          Create one XLSX per financial year (FY spans Jul 1 - Jun 30)
                  Each file will have one tab per account/card number

Author:
    Mark Cowley, 2025-01-17
"""

import os
import sys
import glob
import argparse
import re
import pandas as pd
from datetime import datetime


def extract_value_date(transaction_str):
    """Extract 'Value Date: DD/MM/YYYY' from transaction string.
    Returns (cleaned_transaction, value_date) tuple.
    """
    if not transaction_str or not isinstance(transaction_str, str):
        return transaction_str, None
    
    # Pattern: "Value Date: DD/MM/YYYY" or "Value Date:DD/MM/YYYY"
    pattern = r'Value Date:\s*(\d{1,2}/\d{1,2}/\d{4})'
    match = re.search(pattern, transaction_str, re.IGNORECASE)
    
    if match:
        value_date = match.group(1)
        # Remove the Value Date part from transaction
        cleaned_transaction = re.sub(pattern, '', transaction_str, flags=re.IGNORECASE).strip()
        # Clean up any extra spaces
        cleaned_transaction = re.sub(r'\s+', ' ', cleaned_transaction).strip()
        return cleaned_transaction, value_date
    
    return transaction_str, None


def get_financial_year(date_str):
    """Determine the financial year (Jul 1 - Jun 30) for a given date.
    Returns the year at the END of the interval.
    E.g., Jul 1 2024 - Jun 30 2025 -> FY2025
    """
    try:
        # Handle DD/MM/YYYY format
        if '/' in str(date_str):
            parts = str(date_str).split('/')
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                date = pd.Timestamp(year=year, month=month, day=day)
            else:
                date = pd.to_datetime(date_str, errors='coerce')
        else:
            date = pd.to_datetime(date_str, errors='coerce')
        
        if pd.isna(date):
            return None
        
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


def read_tsv_file(tsv_path):
    """Read a TSV file and return a DataFrame with account/card identifier."""
    try:
        df = pd.read_csv(tsv_path, sep='\t', dtype=str)
        
        # Determine account/card identifier
        account_id = None
        account_type = None
        
        if 'Account Number' in df.columns:
            # Bank statement
            account_id = df['Account Number'].iloc[0] if len(df) > 0 else None
            account_type = 'Account'
        elif 'Card Number' in df.columns:
            # Credit card statement
            account_id = df['Card Number'].iloc[0] if len(df) > 0 else None
            account_type = 'Card'
        
        if account_id:
            # Normalize account/card number (remove extra spaces)
            account_id = ' '.join(account_id.split())
        
        return df, account_id, account_type
    except Exception as e:
        print(f"Error reading {tsv_path}: {e}", file=sys.stderr)
        return None, None, None


def process_folder(folder_path, output_file=None):
    """Process all TSV files in a folder and create a spreadsheet with one tab per account/card."""
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}", file=sys.stderr)
        sys.exit(1)
    
    # Find all TSV files
    tsv_files = glob.glob(os.path.join(folder_path, "*.tsv"))
    tsv_files = [f for f in tsv_files if os.path.isfile(f)]
    
    if not tsv_files:
        print(f"No TSV files found in {folder_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(tsv_files)} TSV file(s)")
    
    # Group data by account/card number
    account_data = {}  # {account_id: list of DataFrames}
    errors = []
    
    # Process each TSV file
    for tsv_path in sorted(tsv_files):
        filename = os.path.basename(tsv_path)
        print(f"Processing: {filename}...", end=" ")
        
        df, account_id, account_type = read_tsv_file(tsv_path)
        
        if df is None:
            print(f"ERROR: Could not read file")
            errors.append(f"{filename}: Could not read file")
            continue
        
        # If DataFrame is empty (no transactions), skip silently (don't print error)
        if len(df) == 0:
            continue
        
        if account_id is None:
            print(f"ERROR: Could not identify account/card")
            errors.append(f"{filename}: Could not identify account/card")
            continue
        
        # Add source file column
        df['Source File'] = filename
        
        # Group by account/card
        if account_id not in account_data:
            account_data[account_id] = []
        account_data[account_id].append(df)
        
        print(f"✓ {len(df)} transaction(s) - {account_type}: {account_id}")
    
    if not account_data:
        print("\nNo valid data found in any TSV files.", file=sys.stderr)
        if errors:
            print("\nErrors encountered:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output file
    if not output_file:
        output_file = os.path.join(folder_path, "cba_statements.xlsx")
    
    # Create Excel file with one sheet per account/card
    print(f"\nCreating Excel file: {output_file}")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for account_id, dfs in sorted(account_data.items()):
            # Combine all DataFrames for this account
            combined_df = pd.concat(dfs, ignore_index=True)
            
            # Extract Value Date from Transaction column if present
            # Do this BEFORE converting Date to datetime for sorting
            # Actual Date should be in column 2 (after Date, before Account/Card Number)
            if 'Transaction' in combined_df.columns:
                value_dates = []
                cleaned_transactions = []
                # Get Date column values to use as fallback (as strings, before datetime conversion)
                date_values = combined_df['Date'].tolist() if 'Date' in combined_df.columns else [None] * len(combined_df)
                
                for idx, trans in enumerate(combined_df['Transaction']):
                    cleaned_trans, value_date = extract_value_date(trans)
                    cleaned_transactions.append(cleaned_trans)
                    # If no Value Date found in transaction, use the Date column value
                    if value_date is None and idx < len(date_values):
                        value_date = date_values[idx]
                    # Ensure Actual Date is in DD/MM/YYYY format
                    if value_date:
                        # Try to parse and reformat to ensure DD/MM/YYYY format
                        try:
                            # Parse the date (could be DD/MM/YYYY or other formats)
                            date_obj = pd.to_datetime(value_date, format='%d/%m/%Y', errors='coerce')
                            if pd.isna(date_obj):
                                # Try other common formats
                                date_obj = pd.to_datetime(value_date, errors='coerce')
                            if not pd.isna(date_obj):
                                value_date = date_obj.strftime('%d/%m/%Y')
                        except:
                            # If parsing fails, keep original value
                            pass
                    value_dates.append(value_date)
                combined_df['Transaction'] = cleaned_transactions
                # Insert Value Date in column 2 (after Date, before Account/Card Number)
                # Find the position after Date column (column 1)
                cols = list(combined_df.columns)
                date_idx = cols.index('Date') if 'Date' in cols else 0
                # Insert Value Date after Date (column 2)
                combined_df.insert(date_idx + 1, 'Value Date', value_dates)
            
            # Convert Date to datetime for sorting
            if 'Date' in combined_df.columns:
                combined_df['Date'] = pd.to_datetime(combined_df['Date'], format='%d/%m/%Y', errors='coerce')
                combined_df = combined_df.sort_values('Date', na_position='last')
                # Convert back to string format
                combined_df['Date'] = combined_df['Date'].dt.strftime('%d/%m/%Y')
            
            # Create sheet name (Excel sheet names have limitations)
            # Remove spaces and limit to 31 characters
            sheet_name = account_id.replace(' ', '_')[:31]
            
            # Convert Amount and Balance columns to numeric before writing
            if 'Amount' in combined_df.columns:
                combined_df['Amount'] = pd.to_numeric(combined_df['Amount'], errors='coerce')
            if 'Balance' in combined_df.columns:
                combined_df['Balance'] = pd.to_numeric(combined_df['Balance'], errors='coerce')
            
            # Write to sheet
            combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Format Amount and Balance columns as Currency
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            # Find column indices for Amount and Balance
            for col_idx, col_name in enumerate(combined_df.columns, start=1):
                if col_name == 'Amount' or col_name == 'Balance':
                    # Apply currency format to all data rows (skip header)
                    for row_idx in range(2, len(combined_df) + 2):  # Start from row 2 (after header)
                        cell = worksheet.cell(row=row_idx, column=col_idx)
                        # Only format if cell has a numeric value
                        if cell.value is not None and not pd.isna(cell.value):
                            # Set currency format: $#,##0.00
                            cell.number_format = '$#,##0.00'
            
            print(f"  ✓ {account_id}: {len(combined_df)} transaction(s)")
    
    print(f"\n✓ Spreadsheet created: {output_file}")
    print(f"  Total accounts/cards: {len(account_data)}")
    
    if errors:
        print(f"\n⚠ {len(errors)} error(s) encountered:")
        for error in errors:
            print(f"  - {error}")


def process_folder_by_fy(folder_path, output_dir=None):
    """Process all TSV files and create one XLSX per financial year, with one tab per account/card."""
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}", file=sys.stderr)
        sys.exit(1)
    
    if not output_dir:
        output_dir = folder_path
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all TSV files
    tsv_files = glob.glob(os.path.join(folder_path, "*.tsv"))
    tsv_files = [f for f in tsv_files if os.path.isfile(f)]
    
    if not tsv_files:
        print(f"No TSV files found in {folder_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(tsv_files)} TSV file(s)")
    
    # Group data by financial year, then by account/card number
    # Structure: {fy: {account_id: list of DataFrames}}
    fy_account_data = {}  # {fy: {account_id: [dfs]}}
    errors = []
    
    # Process each TSV file
    for tsv_path in sorted(tsv_files):
        filename = os.path.basename(tsv_path)
        print(f"Processing: {filename}...", end=" ")
        
        df, account_id, account_type = read_tsv_file(tsv_path)
        
        if df is None:
            print(f"ERROR: Could not read file")
            errors.append(f"{filename}: Could not read file")
            continue
        
        # If DataFrame is empty (no transactions), skip silently (don't print error)
        if len(df) == 0:
            continue
        
        if account_id is None:
            print(f"ERROR: Could not identify account/card")
            errors.append(f"{filename}: Could not identify account/card")
            continue
        
        # Add source file column
        df['Source File'] = filename
        
        # Convert Date to datetime for financial year calculation
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
            df['Financial Year'] = df['Date'].apply(get_financial_year)
        else:
            df['Financial Year'] = None
        
        # Group by financial year and account
        for fy in df['Financial Year'].unique():
            if pd.isna(fy):
                continue
            
            fy = int(fy)
            fy_df = df[df['Financial Year'] == fy].copy()
            
            if fy not in fy_account_data:
                fy_account_data[fy] = {}
            if account_id not in fy_account_data[fy]:
                fy_account_data[fy][account_id] = []
            
            # Drop Financial Year column before storing
            fy_df = fy_df.drop(columns=['Financial Year'])
            fy_account_data[fy][account_id].append(fy_df)
        
        print(f"✓ {len(df)} transaction(s) - {account_type}: {account_id}")
    
    if not fy_account_data:
        print("\nNo valid data found in any TSV files.", file=sys.stderr)
        if errors:
            print("\nErrors encountered:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    
    # Create Excel file per financial year
    print("\nCreating per-financial-year spreadsheets:")
    
    for fy in sorted(fy_account_data.keys()):
        account_data = fy_account_data[fy]
        
        # Create output filename
        output_file = os.path.join(output_dir, f"CBA Statements FY{fy}.xlsx")
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            for account_id, dfs in sorted(account_data.items()):
                # Combine all DataFrames for this account
                combined_df = pd.concat(dfs, ignore_index=True)
                
                # Extract Value Date from Transaction column if present
                # Do this BEFORE converting Date to datetime for sorting
                # Value Date should be in column 2 (after Date, before Account/Card Number)
                if 'Transaction' in combined_df.columns:
                    value_dates = []
                    cleaned_transactions = []
                    # Get Date column values to use as fallback (as strings, before datetime conversion)
                    date_values = combined_df['Date'].tolist() if 'Date' in combined_df.columns else [None] * len(combined_df)
                    
                    for idx, trans in enumerate(combined_df['Transaction']):
                        cleaned_trans, value_date = extract_value_date(trans)
                        cleaned_transactions.append(cleaned_trans)
                        # If no Value Date found in transaction, use the Date column value
                        if value_date is None and idx < len(date_values):
                            value_date = date_values[idx]
                        # Ensure Value Date is in DD/MM/YYYY format
                        if value_date:
                            # Try to parse and reformat to ensure DD/MM/YYYY format
                            try:
                                # Parse the date (could be DD/MM/YYYY or other formats)
                                date_obj = pd.to_datetime(value_date, format='%d/%m/%Y', errors='coerce')
                                if pd.isna(date_obj):
                                    # Try other common formats
                                    date_obj = pd.to_datetime(value_date, errors='coerce')
                                if not pd.isna(date_obj):
                                    value_date = date_obj.strftime('%d/%m/%Y')
                            except:
                                # If parsing fails, keep original value
                                pass
                        value_dates.append(value_date)
                    combined_df['Transaction'] = cleaned_transactions
                    # Insert Actual Date in column 2 (after Date, before Account/Card Number)
                    # Find the position after Date column (column 1)
                    cols = list(combined_df.columns)
                    date_idx = cols.index('Date') if 'Date' in cols else 0
                    # Insert Actual Date after Date (column 2)
                    combined_df.insert(date_idx + 1, 'Actual Date', value_dates)
                
                # Sort by date
                if 'Date' in combined_df.columns:
                    combined_df['Date'] = pd.to_datetime(combined_df['Date'], errors='coerce')
                    combined_df = combined_df.sort_values('Date', na_position='last')
                    # Convert back to string format
                    combined_df['Date'] = combined_df['Date'].dt.strftime('%d/%m/%Y')
                
                # Convert Amount and Balance columns to numeric before writing
                if 'Amount' in combined_df.columns:
                    combined_df['Amount'] = pd.to_numeric(combined_df['Amount'], errors='coerce')
                if 'Balance' in combined_df.columns:
                    combined_df['Balance'] = pd.to_numeric(combined_df['Balance'], errors='coerce')
                
                # Create sheet name (Excel sheet names have limitations)
                sheet_name = account_id.replace(' ', '_')[:31]
                
                # Write to sheet
                combined_df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # Format Amount and Balance columns as Currency
                workbook = writer.book
                worksheet = writer.sheets[sheet_name]
                
                # Find column indices for Amount and Balance
                for col_idx, col_name in enumerate(combined_df.columns, start=1):
                    if col_name == 'Amount' or col_name == 'Balance':
                        # Apply currency format to all data rows (skip header)
                        for row_idx in range(2, len(combined_df) + 2):  # Start from row 2 (after header)
                            cell = worksheet.cell(row=row_idx, column=col_idx)
                            # Only format if cell has a numeric value
                            if cell.value is not None and not pd.isna(cell.value):
                                # Set currency format: $#,##0.00
                                cell.number_format = '$#,##0.00'
        
        # Calculate date range for this FY
        all_dates = []
        for dfs in account_data.values():
            for df in dfs:
                if 'Date' in df.columns:
                    dates = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
                    all_dates.extend(dates.dropna().tolist())
        
        date_range = ""
        if all_dates:
            min_date = min(all_dates).strftime('%d/%m/%Y')
            max_date = max(all_dates).strftime('%d/%m/%Y')
            date_range = f" ({min_date} to {max_date})"
        
        total_transactions = sum(len(df) for dfs in account_data.values() for df in dfs)
        
        print(f"  ✓ FY{fy}{date_range}")
        print(f"    {output_file}")
        print(f"    Total accounts/cards: {len(account_data)}, Total transactions: {total_transactions}")
    
    if errors:
        print(f"\n⚠ {len(errors)} error(s) encountered:")
        for error in errors:
            print(f"  - {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aggregate CBA statement TSV files into Excel spreadsheets",
        prog="cba_aggregate_statements.py"
    )
    
    parser.add_argument(
        "folder",
        help="Path to folder containing TSV files"
    )
    
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file or directory (default: cba_statements.xlsx in folder, or folder for --fy)"
    )
    
    parser.add_argument(
        "--fy",
        action="store_true",
        help="Create one XLSX per financial year (FY spans Jul 1 - Jun 30). Each file will have one tab per account/card number."
    )
    
    args = parser.parse_args()
    
    if args.fy:
        process_folder_by_fy(args.folder, args.output)
    else:
        process_folder(args.folder, args.output)

