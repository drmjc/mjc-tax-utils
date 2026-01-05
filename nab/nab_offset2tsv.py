#!/usr/bin/env python3
"""
Convert a NAB Offset Account statement PDF into a TSV with columns:
Date<TAB>Account Number<TAB>Transaction<TAB>Amount<TAB>Balance

Usage:
    python3 nab/nab_offset2tsv.py input.pdf [--out output.tsv] [--debug]
See also:
nab_offset2tsv.sh, a wrapper script that runs the script with the correct virtual environment

"""
import sys
import re
import argparse
from typing import Optional, Tuple

try:
    import fitz
except Exception:
    fitz = None


def extract_text_from_page(page) -> str:
    """Extract text from a PDF page, skipping image blocks."""
    if fitz is None:
        return ''
    pdata = page.get_text('dict')
    lines = []
    for block in pdata.get('blocks', []):
        # block 'type' == 0 is text, 1 is image
        if block.get('type', 0) != 0:
            continue
        for line in block.get('lines', []):
            parts = []
            for span in line.get('spans', []):
                text = span.get('text', '')
                if text:
                    parts.append(text.rstrip())
            if parts:
                lines.append(' '.join(parts).rstrip())
    return '\n'.join(lines)


def extract_first_page_info(pdf_path: str, debug: bool = False) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Extract from first page:
    - Account Number
    - Statement Period (to determine year)
    
    Also validates that this is a NAB Offset Account statement.
    
    Returns: (account_number, period_string, year)
    Raises: ValueError if not a NAB Offset statement
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available; please install it in the venv')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        raise ValueError('PDF has no pages')
    
    first_page = doc[0]
    text = extract_text_from_page(first_page)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Validate that this is a NAB statement
    text_lower = ' '.join(lines).lower()
    if 'national australia bank' not in text_lower and 'nab' not in text_lower:
        doc.close()
        raise ValueError('This does not appear to be a NAB statement. Could not find "National Australia Bank" or "NAB".')
    
    # Check for Offset account
    if 'offset' not in text_lower:
        if debug:
            print('Warning: Could not find "Offset" in statement, but proceeding', file=sys.stderr)
    
    account_number = None
    period_string = None
    year = None
    
    # Extract account number - look for "Account number" text followed by account number with hyphens (e.g., 25-643-7740)
    # Also look for BSB number pattern
    for i, line in enumerate(lines):
        # Look for "Account number" text, then get the account number from the next line
        if re.search(r'(?i)account\s+number', line):
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Look for account number pattern with hyphens (e.g., 25-643-7740)
                acc_match = re.search(r'(\d+-\d+-\d+)', next_line)
                if acc_match:
                    account_number = acc_match.group(1)
                    if debug:
                        print(f'Found account number (via "Account number" text): {account_number}', file=sys.stderr)
                    break
        
        # Also check for BSB number pattern
        if re.search(r'(?i)bsb\s+number', line):
            # Check current line for BSB
            m = re.search(r'(\d{3}[- ]?\d{3})', line)
            if m:
                # Account number might be on next line or in the same line
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Look for account number pattern (with hyphens or 6-9 digits)
                    acc_match = re.search(r'(\d+-\d+-\d+|\d{6,9})', next_line)
                    if acc_match:
                        account_number = f"{m.group(1)} {acc_match.group(1)}"
                    else:
                        account_number = m.group(1)
                else:
                    account_number = m.group(1)
                if debug:
                    print(f'Found account number (via BSB): {account_number}', file=sys.stderr)
                break
    
    # Fallback: if we haven't found it yet, look for any account number pattern with hyphens
    if not account_number:
        for i, line in enumerate(lines):
            acc_match = re.search(r'(\d+-\d+-\d+)', line)
            if acc_match:
                account_number = acc_match.group(1)
                if debug:
                    print(f'Found account number (fallback, with hyphens): {account_number}', file=sys.stderr)
                break
    
    # Extract statement period and year
    # Look for "Statement start(s)" and "Statement end(s)" (handles both singular and plural)
    start_date = None
    end_date = None
    for i, line in enumerate(lines):
        if re.search(r'(?i)statement start', line):  # Matches both "start" and "starts"
            # Date might be on same line or next line
            # Pattern: "Statement start 17 May 2024" or "Statement start" followed by "17 May 2024"
            m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})', line)
            if m:
                start_date = m.group(1)
            elif i + 1 < len(lines):
                start_line = lines[i + 1]
                m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})', start_line)
                if m:
                    start_date = m.group(1)
        if re.search(r'(?i)statement end', line):  # Matches both "end" and "ends"
            # Date might be on same line or next line
            # Pattern: "Statement end 20 November 2024" or "Statement end" followed by "20 November 2024"
            m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})', line)
            if m:
                end_date = m.group(1)
            elif i + 1 < len(lines):
                end_line = lines[i + 1]
                # Pattern: "20 November 2024"
                m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})', end_line)
                if m:
                    end_date = m.group(1)
    
    if start_date and end_date:
        period_string = f"{start_date} - {end_date}"
        # Extract year from start date
        year_match = re.search(r'(\d{4})', start_date)
        if year_match:
            year = int(year_match.group(1))
        if debug:
            print(f'Found period: {period_string}, year: {year}', file=sys.stderr)
    
    doc.close()
    
    if not account_number:
        print('Warning: Could not find account number on first page', file=sys.stderr)
    
    if not period_string or year is None:
        raise ValueError(f'Could not find statement period on first page of {pdf_path}')
    
    return account_number or '', period_string, year


def parse_date_dd_mmm_yyyy(date_str: str, current_year: int, last_month: Optional[int], month_map: dict) -> Optional[str]:
    """
    Parse date in "DD MMM YYYY" or "DD MMM" format and convert to "DD/MM/YYYY".
    Handles year transitions (e.g., Dec -> Jan increments year).
    """
    # Try full date first: "17 May 2024"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})\s*$', date_str.strip())
    if m:
        day = int(m.group(1))
        mon_str = m.group(2).lower()[:3]
        year = int(m.group(3))
        month_num = month_map.get(mon_str)
        if month_num is None:
            return None
        return f"{day:02d}/{month_num:02d}/{year}"
    
    # Try date without year: "17 May"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})\s*$', date_str.strip())
    if not m:
        return None
    
    day = int(m.group(1))
    mon_str = m.group(2).lower()[:3]
    
    month_num = month_map.get(mon_str)
    if month_num is None:
        return None
    
    # Detect year transition: if current month < last month, we've rolled over
    year = current_year
    if last_month is not None and month_num < last_month:
        year = current_year + 1
    
    return f"{day:02d}/{month_num:02d}/{year}"


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount string, handling 'Nil' and empty values."""
    if not amount_str or not amount_str.strip():
        return None
    
    cleaned = amount_str.strip()
    if cleaned.lower() in ('nil', 'nill', 'nil.'):
        return 0.0
    
    # Remove $, commas, and parentheses
    cleaned = cleaned.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
    
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_balance_with_dr_cr(balance_str: str) -> Tuple[Optional[float], bool]:
    """
    Parse balance string, handling DR/CR suffixes.
    Returns (amount, is_debit).
    If ends in DR, it's a debit (should be negative).
    If ends in CR, it's a credit (should be positive).
    """
    if not balance_str or not balance_str.strip():
        return None, False
    
    cleaned = balance_str.strip()
    if cleaned.lower() in ('nil', 'nill', 'nil.'):
        return 0.0, False
    
    # Check for DR/CR suffix
    is_debit = False
    if cleaned.upper().endswith(' DR'):
        is_debit = True
        cleaned = cleaned[:-3].strip()
    elif cleaned.upper().endswith('DR'):
        is_debit = True
        cleaned = cleaned[:-2].strip()
    elif cleaned.upper().endswith(' CR'):
        cleaned = cleaned[:-3].strip()
    elif cleaned.upper().endswith('CR'):
        cleaned = cleaned[:-2].strip()
    
    # Remove $, commas, and parentheses
    cleaned = cleaned.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
    
    try:
        amount = float(cleaned)
        return amount, is_debit
    except ValueError:
        return None, False


def is_footer_line(line: str) -> bool:
    """Check if a line is a footer (contains 'Statement number' and 'National Australia Bank')."""
    line_lower = line.lower()
    return 'statement number' in line_lower and 'national australia bank' in line_lower


def clean_transaction_name(name: str) -> str:
    """Remove trailing dots and embedded amounts from transaction name."""
    # Special case: Long offset account interest messages should be simplified to "Interest Charged"
    # Pattern: "By Depositing Your Savings In A Linked 100% Offset Account... Interest Charged"
    if 'By Depositing Your Savings In A Linked' in name and 'Interest Charged' in name:
        # Extract just "Interest Charged" from the end
        match = re.search(r'Interest Charged\s*$', name, re.IGNORECASE)
        if match:
            return 'Interest Charged'
    
    # Remove footer/header text that got mixed into transaction names
    # Pattern: "Loan Repayment ... NAB Offset Home Loan ... From A/C"
    # Should become: "Loan Repayment ... From A/C"
    if 'nab offset home loan' in name.lower() and 'from a/c' in name.lower():
        # Find the part before "NAB Offset" and the part starting with "From A/C"
        # Match more flexibly - "NAB Offset Home Loan" followed by any text until "From A/C"
        match = re.search(r'^(.*?)\s+NAB\s+Offset\s+Home\s+Loan.*?(From\s+A/C\s+.*?)$', name, re.IGNORECASE | re.DOTALL)
        if match:
            before = match.group(1).strip()
            after = match.group(2).strip()
            name = f"{before} {after}"
        else:
            # Fallback: remove everything from "NAB Offset" to just before "From A/C"
            name = re.sub(r'\s+NAB\s+Offset\s+Home\s+Loan.*?(?=\s+From\s+A/C)', '', name, flags=re.IGNORECASE | re.DOTALL)
    
    # Pattern 2: "Transaction ... NAB Classic Banking ... Ref: ..."
    # Should become: "Transaction ... Ref: ..."
    if 'nab classic banking' in name.lower() and 'ref:' in name.lower():
        # Find the part before "NAB Classic Banking" and the part starting with "Ref:"
        # Use split to separate, then find Ref: in the second part
        parts = re.split(r'\s+NAB\s+Classic\s+Banking', name, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) == 2:
            before = parts[0].strip()
            after_part = parts[1]
            # Find "Ref:" in the after part, removing any parenthetical content before it
            # Remove any content in parentheses between "NAB Classic Banking" and "Ref:"
            after_part = re.sub(r'\([^)]*\)', '', after_part)  # Remove all parenthetical content
            ref_match = re.search(r'Ref:\s+.*?$', after_part, re.IGNORECASE | re.DOTALL)
            if ref_match:
                after = ref_match.group(0).strip()
                name = f"{before} {after}"
            else:
                # If no Ref: found, just remove the NAB Classic Banking part
                name = before
    
    # Remove special characters and patterns that appear between transaction name and Ref:
    # Pattern like "(√ê0Z√ß√ü1)" or similar garbage characters that appear before "Ref:"
    # If "Ref:" is present, remove any parenthetical content between the transaction name and "Ref:"
    if 'ref:' in name.lower():
        # Find the position of "Ref:" and remove any parentheses before it
        ref_pos = name.lower().find('ref:')
        if ref_pos > 0:
            before_ref = name[:ref_pos]
            after_ref = name[ref_pos:]
            # Remove all parenthetical content from before_ref (including non-ASCII characters)
            # Match parentheses with any content inside, including special characters
            before_ref = re.sub(r'\([^)]*\)', '', before_ref)
            # Also remove any standalone parenthetical patterns that might have unmatched parentheses
            # Remove patterns like "(..." where ... contains non-printable or garbage characters
            before_ref = re.sub(r'\([^a-zA-Z0-9\s)]*\)', '', before_ref)
            name = before_ref + after_ref
    
    # Remove trailing dots
    cleaned = re.sub(r'\.+$', '', name.strip())
    # Remove amounts at the end (pattern: dots followed by number with comma/decimal)
    cleaned = re.sub(r'\.{3,}\s*[\d,]+\.?\d*\s*$', '', cleaned)
    # Also remove any excessive dots in the middle (more than 3 consecutive dots)
    cleaned = re.sub(r'\.{4,}', ' ', cleaned)
    # Remove standalone numbers at the end that look like amounts
    cleaned = re.sub(r'\s+[\d,]+\.\d{2}\s*$', '', cleaned)
    # Remove balance patterns (numbers with commas, decimals, and CR/DR) that got mixed into description
    cleaned = re.sub(r'\s+[\d,]+\.[\d,]+\s+(CR|DR)\s+', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+[\d,]+\.[\d,]+\s+(CR|DR)$', '', cleaned, flags=re.IGNORECASE)
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def parse_transactions(pdf_path: str, account_number: str, year: int, debug: bool = False) -> list:
    """
    Parse transactions from all pages.
    Returns list of [date, transaction, amount, balance] rows.
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        return []
    
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    rows = []
    current_year = year
    last_month = None
    running_balance = None  # Track running balance
    processed_dates = set()  # Track dates we've already processed to avoid duplicates
    
    # Extract opening balance from first page if available
    first_page = doc[0]
    first_page_text = extract_text_from_page(first_page)
    first_page_lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
    for i, line in enumerate(first_page_lines):
        line_lower = line.lower()
        if 'opening balance' in line_lower and i + 1 < len(first_page_lines):
            # Next line should have the balance amount
            balance_line = first_page_lines[i + 1]
            balance_match = re.search(r'[\$]?\s*([\d,]+\.\d{2})\s*(DR|CR|Dr|Cr)', balance_line, re.IGNORECASE)
            if balance_match:
                balance_amt = parse_amount(balance_match.group(1))
                is_debit = balance_match.group(2).upper() == 'DR'
                if balance_amt is not None:
                    running_balance = -balance_amt if is_debit else balance_amt
                    if debug:
                        print(f'DEBUG: Found opening balance: {running_balance}', file=sys.stderr)
                    break
    
    # Date patterns: "DD MMM YYYY" or "DD MMM"
    date_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3,})\s*$')
    date_with_year_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})\s*$')
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = extract_text_from_page(page)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # Skip footer lines
        lines = [l for l in lines if not is_footer_line(l)]
        
        # Skip header and find table start
        table_started = False
        header_found = False
        i = 0
        
        while i < len(lines):
            line = lines[i]
            line_lower = line.lower()
            
            # Look for table header: "Date", "Particulars", "Debits", "Credits", "Balance"
            if not header_found:
                if 'date' in line_lower and 'particulars' in line_lower:
                    header_found = True
                    table_started = True
                    # Skip header lines
                    i += 1
                    continue
                elif line_lower.strip() == 'date':
                    # Check if next lines have particulars, debits, credits, balance
                    if i + 4 < len(lines):
                        next_lines = [lines[i+j].lower() for j in range(1, 5)]
                        if ('particulars' in ' '.join(next_lines) and 
                            ('debits' in ' '.join(next_lines) or 'credits' in ' '.join(next_lines)) and
                            'balance' in ' '.join(next_lines)):
                            header_found = True
                            table_started = True
                            # Skip header rows
                            i += 5
                            continue
            
            if not table_started:
                i += 1
                continue
            
            # Skip lines with lots of stars
            if '****' in line and line.count('*') > 10:
                i += 1
                continue
            
            # Skip informational messages and page boundary markers
            # BUT: "Brought forward" on its own line should be skipped, but transactions after it should be collected
            # So we only skip "Brought forward" if it's a standalone line (not part of transaction collection)
            if any(skip_term in line_lower for skip_term in [
                'if a charge is incorrect',
                'if you have any queries',
                'carried forward',
                'transaction details',
                'transaction details (continued)'
            ]):
                i += 1
                continue
            
            # Skip "Brought forward" only if it's a standalone line (not followed immediately by a transaction)
            # This allows transactions after "Brought forward" to be collected in the date collection logic
            if line_lower.strip() == 'brought forward':
                i += 1
                continue
            
            # Parse transaction rows
            # Check if this line starts with a date (DD MMM YYYY or DD MMM)
            date_with_year_match = date_with_year_pattern.match(line)
            date_match = date_pattern.match(line)
            
            # Also check if line starts with a date pattern (even if followed by text)
            date_at_start_with_year = re.match(r'^(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})\s+(.+)', line)
            date_at_start = re.match(r'^(\d{1,2}\s+[A-Za-z]{3,})\s+(.+)', line)
            
            formatted_date = None
            transaction_start_on_same_line = None
            
            if date_with_year_match or date_at_start_with_year:
                # Date with year: extract year and update current_year
                if date_at_start_with_year:
                    date_str_with_year = date_at_start_with_year.group(1)
                    transaction_start_on_same_line = date_at_start_with_year.group(2).strip()
                else:
                    date_str_with_year = date_with_year_match.group(1)
                year_match = re.search(r'(\d{4})', date_str_with_year)
                extracted_year = None
                if year_match:
                    extracted_year = int(year_match.group(1))
                    current_year = extracted_year
                # Extract just DD MMM part
                date_str = re.match(r'^(\d{1,2}\s+[A-Za-z]{3,})', date_str_with_year).group(1)
                # If we extracted a year, use it directly instead of inferring
                if extracted_year is not None:
                    # Parse the date components manually to use the extracted year
                    day = int(re.match(r'^(\d{1,2})', date_str).group(1))
                    mon_str = re.search(r'([A-Za-z]{3,})', date_str).group(1).lower()[:3]
                    month_num = month_map.get(mon_str)
                    if month_num:
                        formatted_date = f"{day:02d}/{month_num:02d}/{extracted_year}"
                    else:
                        formatted_date = parse_date_dd_mmm_yyyy(date_str, current_year, last_month, month_map)
                else:
                    formatted_date = parse_date_dd_mmm_yyyy(date_str, current_year, last_month, month_map)
            elif date_match or date_at_start:
                if date_at_start:
                    date_str = date_at_start.group(1)
                    transaction_start_on_same_line = date_at_start.group(2).strip()
                else:
                    date_str = date_match.group(1)
                formatted_date = parse_date_dd_mmm_yyyy(date_str, current_year, last_month, month_map)
            
            if formatted_date:
                # Skip if we've already processed this date
                if formatted_date in processed_dates:
                    if debug:
                        print(f'DEBUG: Skipping already processed date {formatted_date}', file=sys.stderr)
                    i += 1
                    continue
                
                # Mark this date as processed
                processed_dates.add(formatted_date)
                
                # Update current_year and last_month
                date_parts = formatted_date.split('/')
                if len(date_parts) == 3:
                    current_year = int(date_parts[2])
                    last_month = int(date_parts[1])
                
                # Collect all lines for this day until we hit the next date or final balance
                # This may span multiple pages, so we need to continue collecting across pages
                collected_lines = []
                day_end_balance = None
                day_end_balance_is_debit = False
                
                # Collect from current page, then continue on next pages if needed
                current_page_idx = page_idx
                j = i + 1
                page_boundary_seen = False
                lines_processed_on_current_page = 0  # Track how many lines we process on the starting page
                
                if debug:
                    print(f'DEBUG: Starting to collect lines for date {formatted_date}, starting at page {page_idx+1}, line {i+1}', file=sys.stderr)
                
                iteration_count = 0
                while current_page_idx < len(doc):
                    iteration_count += 1
                    if debug and iteration_count % 100 == 0:
                        print(f'DEBUG: Still collecting, iteration {iteration_count}, page {current_page_idx+1}, j={j}, collected_lines={len(collected_lines)}', file=sys.stderr)
                    if iteration_count > 1000:
                        print(f'ERROR: Infinite loop detected! Stopping at page {current_page_idx+1}, line {j}', file=sys.stderr)
                        break
                    current_page = doc[current_page_idx]
                    current_page_text = extract_text_from_page(current_page)
                    current_page_lines = [l.strip() for l in current_page_text.split('\n') if l.strip()]
                    current_page_lines = [l for l in current_page_lines if not is_footer_line(l)]
                    
                    # If this is a new page (not the one we started on), reset j and skip header
                    if current_page_idx > page_idx:
                        if debug:
                            print(f'DEBUG: Moved to new page {current_page_idx+1}, resetting j', file=sys.stderr)
                        j = 0
                        # Skip header on new pages - look for "Brought forward" and skip everything up to and including it
                        # Also look for table header ("Date" and "Particulars")
                        header_skipped = False
                        for k in range(len(current_page_lines)):
                            line_k_lower = current_page_lines[k].lower()
                            # Skip "Brought forward" and its balance
                            if 'brought forward' in line_k_lower:
                                j = k + 1
                                # Skip the balance line that follows "Brought forward"
                                if j < len(current_page_lines):
                                    next_line_after = current_page_lines[j]
                                    # Check if it's CR/DR followed by balance, or just a balance
                                    if next_line_after.strip().lower() in ('cr', 'dr'):
                                        if j + 1 < len(current_page_lines) and re.search(r'[\d,]+\.\d{2}', current_page_lines[j + 1]):
                                            j += 2  # Skip CR/DR and balance
                                    elif re.search(r'[\d,]+\.\d{2}', next_line_after):
                                        j += 1  # Skip balance
                                page_boundary_seen = True
                                header_skipped = True
                                break
                            # Also check for table header
                            elif 'date' in line_k_lower and 'particulars' in line_k_lower:
                                j = k + 1
                                header_skipped = True
                                break
                            elif line_k_lower.strip() == 'date' and k + 4 < len(current_page_lines):
                                next_lines_lower = [current_page_lines[k+m].lower() for m in range(1, 5)]
                                if 'particulars' in ' '.join(next_lines_lower):
                                    j = k + 5
                                    header_skipped = True
                                    break
                    
                    inner_iteration = 0
                    while j < len(current_page_lines):
                        inner_iteration += 1
                        if debug and inner_iteration % 50 == 0:
                            print(f'DEBUG: Inner loop iteration {inner_iteration}, j={j}/{len(current_page_lines)}, line preview: {current_page_lines[j][:50] if j < len(current_page_lines) else "END"}', file=sys.stderr)
                        if inner_iteration > 500:
                            print(f'ERROR: Inner loop stuck! j={j}, line_count={len(current_page_lines)}', file=sys.stderr)
                            print(f'DEBUG: Last few lines: {current_page_lines[max(0, j-3):j+3]}', file=sys.stderr)
                            break
                            
                        next_line = current_page_lines[j]
                        next_lower = next_line.lower()
                        
                        # Always check if we hit another date (different from the one we're processing)
                        date_match = date_pattern.match(next_line) or date_with_year_pattern.match(next_line)
                        if date_match:
                            date_str = date_match.group(1)
                            # Extract date parts to compare
                            date_parts_new = date_str.split()
                            date_parts_current = formatted_date.split('/')
                            if len(date_parts_new) >= 2 and len(date_parts_current) == 3:
                                day_new = int(date_parts_new[0])
                                month_new = month_map.get(date_parts_new[1].lower()[:3])
                                day_current = int(date_parts_current[0])
                                month_current = int(date_parts_current[1])
                                if day_new != day_current or month_new != month_current:
                                    # Different date, stop collecting
                                    if debug:
                                        print(f'DEBUG: Found different date, stopping collection', file=sys.stderr)
                                    current_page_idx = len(doc)  # Exit outer loop
                                    break
                        
                        # Skip lines with lots of stars
                        if '****' in next_line and next_line.count('*') > 10:
                            j += 1
                            continue
                        
                        # Skip footer/header text that appears at page boundaries
                        # These lines contain information like "NAB Offset Home Loan For further information call..."
                        # or "NAB Classic Banking" footer text
                        # Also skip informational text that appears between transactions
                        if any(skip_phrase in next_lower for skip_phrase in [
                            'for further information call',
                            'for personal accounts or',
                            'for business accounts',
                            'nab offset home loan for further',
                            'nab offset home loan for fur',
                            'nab classic banking',
                            'if a charge is incorrect',
                            'you may be entitled to a refund',
                            'you should act quickly',
                            'please call 13 22 65',
                            'nab.com.au/terms',
                            'disputed transactions'
                        ]):
                            # Skip this line and continue collecting (don't break, as transaction may continue)
                            j += 1
                            continue
                        
                        # Handle "Carried forward" - stop reading this page and move to next page
                        # Rule: when "Carried forward" is read, stop reading that page, then skip over "Brought forward" on next page
                        if 'carried forward' in next_lower:
                            page_boundary_seen = True
                            # Stop reading this page - break out of inner loop to move to next page
                            # "Brought forward" will be skipped when we start the next page
                            if debug:
                                print(f'DEBUG: Found "Carried forward" on page {current_page_idx+1}, stopping page and moving to next', file=sys.stderr)
                            break  # Break out of inner loop to move to next page
                        elif 'brought forward' in next_lower:
                            page_boundary_seen = True
                            # Skip "Brought forward" and the balance line that follows
                            # This should only be encountered when we've moved to a new page after "Carried forward"
                            j += 1
                            if j < len(current_page_lines):
                                next_next_line = current_page_lines[j]
                                # Check if it's a balance (CR/DR followed by amount, or just an amount)
                                if next_next_line.strip().lower() in ('cr', 'dr'):
                                    j += 1  # Skip CR/DR
                                    if j < len(current_page_lines) and re.search(r'[\d,]+\.\d{2}', current_page_lines[j]):
                                        j += 1  # Skip balance amount
                                elif re.search(r'[\d,]+\.\d{2}', next_next_line):
                                    j += 1  # Skip balance amount
                            # Continue collecting transactions after "Brought forward"
                            continue
                        
                        # Check if this is the balance for the day
                        if next_lower.strip() in ('cr', 'dr'):
                            if j + 1 < len(current_page_lines):
                                balance_line = current_page_lines[j + 1]
                                # Skip if this is a "Carried forward" or "Brought forward" balance
                                if 'carried forward' in balance_line.lower() or 'brought forward' in balance_line.lower():
                                    # Skip this balance line and continue
                                    j += 2
                                    page_boundary_seen = True
                                    continue
                                # Check if this looks like a valid balance (has number)
                                if re.search(r'[\d,]+\.\d{2}', balance_line):
                                    day_end_balance, day_end_balance_is_debit = parse_balance_with_dr_cr(f"{balance_line} {next_line}")
                                    if day_end_balance_is_debit:
                                        day_end_balance = -abs(day_end_balance)
                                    else:
                                        day_end_balance = abs(day_end_balance)
                                    collected_lines.append(next_line)
                                    collected_lines.append(balance_line)
                                    j += 2
                                    # Found final balance, break out of all loops
                                    current_page_idx = len(doc)  # Exit outer loop
                                    break
                        
                        collected_lines.append(next_line)
                        # Track if we're on the original page
                        if current_page_idx == page_idx:
                            lines_processed_on_current_page += 1
                        j += 1
                    
                    # If we found the final balance, break
                    if day_end_balance is not None:
                        break
                    
                    # Check if we've exhausted this page, or if we broke due to "Carried forward"
                    # In either case, move to next page
                    if j >= len(current_page_lines) or page_boundary_seen:
                        current_page_idx += 1
                        page_boundary_seen = False
                        if current_page_idx >= len(doc):
                            # Reached end of document, break
                            break
                        # Continue to next iteration of outer loop, which will skip "Brought forward" on new page
                        continue
                    else:
                        # Still processing current page, but something went wrong, break to avoid infinite loop
                        if debug:
                            print(f'DEBUG: j={j} < len={len(current_page_lines)}, breaking inner loop', file=sys.stderr)
                        break
                
                # Parse collected lines to extract multiple transactions on the same day
                # NAB format: multiple transactions, each with description followed by amount (with dots), then final balance
                # Transaction keywords that indicate a new transaction: Online, EFTPOS, PO, Lc, V6606, Refund, etc.
                
                transactions_for_day = []  # List of (description, (amount, is_debit)) tuples
                current_trans_desc = []
                current_trans_amount = None  # Will be (amount, is_debit) when found
                # Track the last transaction saved without an amount (for matching amounts found later)
                last_incomplete_transaction_idx = None
                
                # Transaction start keywords (case-insensitive)
                transaction_keywords = ['online', 'eftpos', 'po', 'lc', 'v6606', 'refund', 'monthly pay', 
                                       'loan repayment', 'direct credit', 'direct debit', 'hcf']
                
                line_idx = 0
                while line_idx < len(collected_lines):
                    line = collected_lines[line_idx]
                    line_lower = line.lower().strip()
                    
                    # Skip empty lines
                    if not line_lower:
                        line_idx += 1
                        continue
                    
                    # Skip "Carried forward" and "Brought forward" lines (page boundary markers)
                    if 'carried forward' in line_lower or 'brought forward' in line_lower:
                        # Skip the balance line that follows
                        line_idx += 1
                        if line_idx < len(collected_lines):
                            balance_line = collected_lines[line_idx]
                            # Check if it's a balance amount
                            if re.match(r'^[\d,]+\.?\d*\s*(CR|DR)?', balance_line, re.I):
                                line_idx += 1  # Skip the balance amount
                        continue
                    
                    # Check if this is the balance line (we've already captured it above)
                    if line_lower.strip() in ('cr', 'dr'):
                        # Check if this is part of a "Carried forward" or "Brought forward" pattern
                        if line_idx > 0:
                            prev_line = collected_lines[line_idx - 1].lower()
                            if 'carried forward' in prev_line or 'brought forward' in prev_line:
                                # Skip balance indicator and amount - this is a page boundary marker
                                line_idx += 2
                                continue
                        # Skip balance indicator and amount - we've already captured them
                        line_idx += 2
                        continue
                    
                    # Pattern 1: Line with dots followed by amount (common NAB format)
                    # Pattern: "text........................................................................ 12,941.82"
                    # Count dots before amount to determine if it's in Debit or Credit column
                    # More dots (60+) = further right = Credits column
                    # Fewer dots (<60) = further left = Debits column
                    dots_amount_match = re.search(r'(\.{3,})\s*([\d,]+\.\d{2})\s*$', line)
                    if dots_amount_match:
                        dots_str = dots_amount_match.group(1)
                        amount_str = dots_amount_match.group(2)
                        num_dots = len(dots_str)
                        desc_part = re.sub(r'\.{3,}.*$', '', line).strip()
                        if desc_part:
                            current_trans_desc.append(desc_part)
                        amt = parse_amount(amount_str)
                        if amt is not None:
                            # Determine if this is debit or credit based on dot count and keywords
                            # Based on examples: transactions with 80+ dots are DR (negative)
                            # So we use a high threshold: 100+ dots = likely Credits column
                            # Fewer dots = Debits column (amount should be negative)
                            # But also check transaction description for clear credit indicators
                            trans_so_far = ' '.join(current_trans_desc + [desc_part]).lower()
                            is_clear_credit = any(kw in trans_so_far for kw in [
                                'monthly pay', 'salary', 'direct credit', 'credit interest',
                                'transfer from', 'transfer in', 'deposit', 'refund',
                                'from a/c', 'from a/c '  # "Loan Repayment ... From A/C" is a credit (money coming in)
                            ])
                            is_debit = num_dots < 100 and not is_clear_credit
                            current_trans_amount = (amt, is_debit)
                            # Check if we have a saved transaction without an amount that this amount belongs to
                            # This happens when a transaction code was detected and we saved the transaction without an amount
                            if not current_trans_desc and last_incomplete_transaction_idx is not None:
                                # Update the incomplete transaction with this amount
                                prev_desc, _ = transactions_for_day[last_incomplete_transaction_idx]
                                transactions_for_day[last_incomplete_transaction_idx] = (prev_desc, current_trans_amount)
                                last_incomplete_transaction_idx = None
                                current_trans_amount = None
                            # This transaction is complete - save it
                            elif current_trans_desc:
                                trans_desc = clean_transaction_name(' '.join(current_trans_desc).strip())
                                if trans_desc:
                                    transactions_for_day.append((trans_desc, current_trans_amount))
                                # Reset for next transaction
                                current_trans_desc = []
                                current_trans_amount = None
                        line_idx += 1
                        continue
                    
                    # Pattern 2: Line with just dots, possibly followed by amount (continuation line)
                    if re.match(r'^\.+', line):
                        # Check if there's an amount after the dots
                        amount_after_dots = re.search(r'\.{3,}\s*([\d,]+\.\d{2})\s*$', line)
                        if amount_after_dots:
                            dots_str = amount_after_dots.group(0).split(amount_after_dots.group(1))[0]
                            num_dots = len(dots_str) if dots_str else 0
                            amount_str = amount_after_dots.group(1)
                            amt = parse_amount(amount_str)
                            if amt is not None:
                                # Count total dots on this line to determine column
                                # Based on examples: use high threshold for Credits
                                # But also check transaction description for clear credit indicators
                                trans_so_far = ' '.join(current_trans_desc).lower()
                                is_clear_credit = any(kw in trans_so_far for kw in [
                                    'monthly pay', 'salary', 'direct credit', 'credit interest',
                                    'transfer from', 'transfer in', 'deposit', 'refund',
                                    'from a/c', 'from a/c '  # "Loan Repayment ... From A/C" is a credit (money coming in)
                                ])
                                is_debit = num_dots < 100 and not is_clear_credit
                                current_trans_amount = (amt, is_debit)
                                # Check if we have a saved transaction without an amount that this amount belongs to
                                if not current_trans_desc and last_incomplete_transaction_idx is not None:
                                    # Update the incomplete transaction with this amount
                                    prev_desc, _ = transactions_for_day[last_incomplete_transaction_idx]
                                    transactions_for_day[last_incomplete_transaction_idx] = (prev_desc, current_trans_amount)
                                    last_incomplete_transaction_idx = None
                                    current_trans_amount = None
                                # Save transaction
                                elif current_trans_desc:
                                    trans_desc = clean_transaction_name(' '.join(current_trans_desc).strip())
                                    if trans_desc:
                                        transactions_for_day.append((trans_desc, current_trans_amount))
                                    current_trans_desc = []
                                    current_trans_amount = None
                        line_idx += 1
                        continue
                    
                    # Pattern 3: Description line (contains letters)
                    if re.search(r'[a-zA-Z]', line):
                        # Check if this line starts with a transaction code (e.g., "V6741", "V6606", "E5778714428") or transaction keyword
                        # Transaction code pattern: 1-3 letters followed by 3-10 digits at the start of the line
                        # Also check for longer transaction IDs like "E5778714428" (1 letter + 8+ digits) at the START
                        transaction_code_at_start = (re.match(r'^([A-Z]{1,3}\d{3,10})\s+', line, re.IGNORECASE) or
                                                     re.match(r'^([A-Z]\d{8,})\s+', line, re.IGNORECASE))  # Pattern for longer IDs like E5778714428
                        transaction_code_match = transaction_code_at_start
                        starts_with_keyword = any(line_lower.startswith(kw.lower()) for kw in transaction_keywords)
                        
                        # Check if this looks like a continuation line (e.g., "Ref: ...") that should be added to current or incomplete transaction
                        # Only treat clear continuation indicators as continuations, not names or other text
                        is_continuation = (line_lower.startswith('ref:') or 
                                         line_lower.startswith('inv '))
                        
                        # If we have an incomplete transaction and this is a clear continuation (Ref: or Inv:), add it to that transaction
                        if last_incomplete_transaction_idx is not None and is_continuation and not current_trans_desc:
                            # This is a continuation line for the incomplete transaction (current_trans_desc is empty)
                            prev_desc, _ = transactions_for_day[last_incomplete_transaction_idx]
                            updated_desc = clean_transaction_name(f"{prev_desc} {line}".strip())
                            transactions_for_day[last_incomplete_transaction_idx] = (updated_desc, (0.0, True))
                            line_idx += 1
                            continue
                        # If we're building a current transaction and this is a clear continuation, add it
                        elif current_trans_desc and is_continuation and not transaction_code_match:
                            # This is a continuation line for the current transaction being built
                            current_trans_desc.append(line)
                            line_idx += 1
                            continue
                        
                        # If we already have a completed transaction (with amount), this is a new transaction
                        if current_trans_amount is not None and current_trans_desc:
                            # Previous transaction was already saved when we found the amount
                            # This line starts a new transaction
                            current_trans_desc = [line]
                            current_trans_amount = None
                        # If this line starts with a transaction code and we have an existing description,
                        # it's definitely a new transaction (especially after page boundaries)
                        elif transaction_code_match and current_trans_desc:
                            # Clear transaction code detected - this is definitely a new transaction
                            # Save previous transaction immediately (don't look ahead - that causes merging issues)
                            # Check if the previous line (line_idx - 1) has an amount we can use
                            prev_amount = current_trans_amount
                            if not prev_amount and line_idx > 0:
                                prev_line = collected_lines[line_idx - 1]
                                # Check if previous line has an amount with dots
                                prev_dots_amt = re.search(r'(\.{3,})\s*([\d,]+\.\d{2})\s*$', prev_line)
                                if prev_dots_amt:
                                    amount_str = prev_dots_amt.group(2)
                                    amt = parse_amount(amount_str)
                                    if amt is not None:
                                        num_dots = len(prev_dots_amt.group(1))
                                        trans_so_far = ' '.join(current_trans_desc).lower()
                                        is_clear_credit = any(kw in trans_so_far for kw in [
                                            'monthly pay', 'salary', 'direct credit', 'credit interest',
                                            'transfer from', 'transfer in', 'deposit', 'refund',
                                            'from a/c', 'from a/c '
                                        ])
                                        is_debit = num_dots < 100 and not is_clear_credit
                                        prev_amount = (amt, is_debit)
                            
                            prev_desc = clean_transaction_name(' '.join(current_trans_desc).strip())
                            if prev_desc:
                                if prev_amount:
                                    transactions_for_day.append((prev_desc, prev_amount))
                                    last_incomplete_transaction_idx = None
                                else:
                                    # No amount found yet - save it and track it for later matching
                                    transactions_for_day.append((prev_desc, (0.0, True)))
                                    last_incomplete_transaction_idx = len(transactions_for_day) - 1
                            # Start new transaction
                            current_trans_desc = [line]
                            current_trans_amount = None
                        # If this line starts with a transaction keyword (but not a code) and we have an existing description,
                        # it might be a new transaction, but be more cautious
                        elif starts_with_keyword and current_trans_desc and current_trans_amount is not None:
                            # Previous transaction has an amount, save it and start new
                            prev_desc = clean_transaction_name(' '.join(current_trans_desc).strip())
                            if prev_desc:
                                transactions_for_day.append((prev_desc, current_trans_amount))
                            current_trans_desc = [line]
                            current_trans_amount = None
                        else:
                            # Continue current transaction description
                            current_trans_desc.append(line)
                        line_idx += 1
                        continue
                    
                    # Pattern 4: Standalone amount (no dots, just amount)
                    standalone_amount = re.match(r'^[\$]?\s*([\d,]+\.\d{2})\s*$', line)
                    if standalone_amount:
                        amt = parse_amount(standalone_amount.group(1))
                        if amt is not None:
                            # For standalone amounts, check previous line to see if it had dots
                            # If previous line was all dots, this is likely in the Credits column
                            if line_idx > 0 and re.match(r'^\.+$', collected_lines[line_idx - 1]):
                                # Previous line was dots, this amount is likely in Credits column
                                current_trans_amount = (amt, False)  # is_debit = False
                            else:
                                # Use keyword heuristics as fallback
                                trans_so_far = ' '.join(current_trans_desc).lower()
                                is_likely_debit = any(kw in trans_so_far for kw in [
                                    'loan repayment', 'repayment', 'transfer to', 'debit', 'payment',
                                    'eftpos', 'purchase', 'withdrawal', 'fee', 'charge', 'tv payment',
                                    'shortfall', 'linked acc trns', 'online'
                                ])
                                current_trans_amount = (amt, is_likely_debit)
                            # Check if we have a saved transaction without an amount that this amount belongs to
                            if not current_trans_desc and last_incomplete_transaction_idx is not None:
                                # Update the incomplete transaction with this amount
                                prev_desc, _ = transactions_for_day[last_incomplete_transaction_idx]
                                transactions_for_day[last_incomplete_transaction_idx] = (prev_desc, current_trans_amount)
                                last_incomplete_transaction_idx = None
                                current_trans_amount = None
                            # This transaction is complete - save it
                            elif current_trans_desc:
                                trans_desc = clean_transaction_name(' '.join(current_trans_desc).strip())
                                if trans_desc:
                                    transactions_for_day.append((trans_desc, current_trans_amount))
                                # Reset for next transaction
                                current_trans_desc = []
                                current_trans_amount = None
                        line_idx += 1
                        continue
                    
                    line_idx += 1
                
                # Now process all transactions for this day
                # Use the final balance to work backwards and determine debit/credit for each transaction
                if transactions_for_day and day_end_balance is not None:
                    # Work backwards from final balance to determine debit/credit for each transaction
                    # Start from the final balance and work backwards through transactions
                    running_bal = day_end_balance
                    processed_transactions = []  # Will store (desc, amount, balance_after) in forward order
                    
                    # Work backwards from final balance, then forward to determine debit/credit
                    # Strategy: Start from final balance, work backwards to get balance before each transaction
                    # Then work forward, using balance changes to determine debit/credit
                    prev_balance_for_day = running_balance if running_balance is not None else 0.0
                    
                    # First pass: work backwards to calculate what balance should be before each transaction
                    # We'll use the final balance and work backwards assuming all are debits first
                    balances_before = []
                    temp_bal = day_end_balance
                    for trans_desc, (trans_amt, is_debit_flag_hint) in reversed(transactions_for_day):
                        # Try as debit: balance before = balance after + amount
                        balance_before_debit = temp_bal + trans_amt
                        # Try as credit: balance before = balance after - amount
                        balance_before_credit = temp_bal - trans_amt
                        balances_before.insert(0, (balance_before_debit, balance_before_credit))
                        # For now, use the hint to determine which to use
                        if is_debit_flag_hint:
                            temp_bal = balance_before_debit
                        else:
                            temp_bal = balance_before_credit
                    
                    # Second pass: work forward, using balance verification for each transaction
                    current_balance = prev_balance_for_day
                    for idx, (trans_desc, (trans_amt, is_debit_flag_hint)) in enumerate(transactions_for_day):
                        balance_before_debit, balance_before_credit = balances_before[idx]
                        
                        # Verify which balance before matches the current balance
                        debit_diff = abs(balance_before_debit - current_balance)
                        credit_diff = abs(balance_before_credit - current_balance)
                        
                        # Use balance math to determine debit/credit
                        if debit_diff < credit_diff or (debit_diff == credit_diff and is_debit_flag_hint):
                            amount = -trans_amt  # Debit is negative
                            balance_after = current_balance - trans_amt
                        else:
                            amount = trans_amt  # Credit is positive
                            balance_after = current_balance + trans_amt
                        
                        processed_transactions.append((trans_desc, amount, balance_after))
                        current_balance = balance_after
                    
                    # Now process in forward order
                    for trans_desc, amount, balance in processed_transactions:
                        trans_lower = trans_desc.lower()
                        
                        # Skip if transaction is empty or contains skip terms
                        if not trans_desc or 'opening balance' in trans_lower or 'closing balance' in trans_lower:
                            continue
                        
                        # Skip informational messages and page boundary markers
                        if any(skip_term in trans_lower for skip_term in [
                            'the following information',
                            'if a charge is incorrect',
                            'if you have any queries',
                            'brought forward',
                            'carried forward'
                        ]):
                            continue
                        
                        rows.append([formatted_date, trans_desc, amount, balance])
                        if debug:
                            print(f'Transaction: {formatted_date} | {trans_desc[:50]} | Amount: {amount} | Balance: {balance}', file=sys.stderr)
                    
                    # Update running balance to the final balance of the day
                    running_balance = day_end_balance
                
                # After processing a date, we need to update i to skip past the lines we've already processed
                # If we moved to a new page, we need to break out of the inner loop and continue the outer page loop
                if current_page_idx > page_idx:
                    # We moved to a new page, so we should break out and let the outer loop handle the next page
                    # Set i to end of current page to exit inner loop
                    i = len(lines)
                elif transactions_for_day:
                    # No final balance, use running balance approach
                    for trans_desc, (trans_amt, is_debit_flag) in transactions_for_day:
                        trans_lower = trans_desc.lower()
                        
                        # Skip if transaction is empty or contains skip terms
                        if not trans_desc or 'opening balance' in trans_lower or 'closing balance' in trans_lower:
                            continue
                        
                        # Skip informational messages and page boundary markers
                        if any(skip_term in trans_lower for skip_term in [
                            'the following information',
                            'if a charge is incorrect',
                            'if you have any queries',
                            'brought forward',
                            'carried forward'
                        ]):
                            continue
                        
                        # Determine debit/credit using keyword heuristics
                        is_likely_debit = any(kw in trans_lower for kw in [
                            'loan repayment', 'repayment', 'transfer to', 'debit', 'payment',
                            'eftpos', 'purchase', 'withdrawal', 'fee', 'charge', 'tv payment',
                            'shortfall', 'linked acc trns', 'online'
                        ])
                        is_likely_credit = any(kw in trans_lower for kw in [
                            'direct credit', 'credit interest', 'salary', 'monthly pay',
                            'transfer from', 'transfer in', 'deposit', 'refund'
                        ]) and not any(kw in trans_lower for kw in ['payment', 'repayment'])
                        
                        if is_likely_debit and not is_likely_credit:
                            amount = -trans_amt  # Debit is negative
                        else:
                            amount = trans_amt  # Credit is positive
                        
                        # Calculate balance
                        if running_balance is not None:
                            running_balance += amount
                            balance = running_balance
                        else:
                            running_balance = amount
                            balance = amount
                        
                        rows.append([formatted_date, trans_desc, amount, balance])
                        if debug:
                            print(f'Transaction: {formatted_date} | {trans_desc[:50]} | Amount: {amount} | Balance: {balance}', file=sys.stderr)
                
                i = j
                continue
            
            i += 1
    
    doc.close()
    return rows


def write_tsv(rows: list, account_number: str, out):
    """Write rows to TSV file."""
    # Header
    out.write('Date\tAccount Number\tTransaction\tAmount\tBalance\n')
    
    for row in rows:
        date, transaction, amount, balance = row
        
        # Format amount
        if amount is not None:
            amount_str = f"{amount:.2f}"
        else:
            amount_str = ''
        
        # Format balance
        if balance is not None:
            balance_str = f"{balance:.2f}"
        else:
            balance_str = ''
        
        out.write(f'{date}\t{account_number or ""}\t{transaction}\t{amount_str}\t{balance_str}\n')


def main():
    parser = argparse.ArgumentParser(description='Convert NAB Offset Account statement PDF to TSV')
    parser.add_argument('pdf', help='Input PDF file')
    parser.add_argument('--out', help='Output TSV path (default: replace .pdf with .tsv)')
    parser.add_argument('--debug', action='store_true', help='Show debug info')
    args = parser.parse_args()
    
    if fitz is None:
        print('Error: PyMuPDF (fitz) not available. Please install it in the venv.', file=sys.stderr)
        sys.exit(1)
    
    if args.debug:
        print(f'Reading: {args.pdf}', file=sys.stderr)
    
    # Extract first page info
    account_number, period_string, year = extract_first_page_info(args.pdf, args.debug)
    
    if not period_string or year is None:
        print('Error: Could not find statement period on first page', file=sys.stderr)
        sys.exit(1)
    
    # Parse transactions
    rows = parse_transactions(args.pdf, account_number, year, args.debug)
    
    if args.debug:
        print(f'Parsed {len(rows)} transactions', file=sys.stderr)
    
    # Write output
    output_path = args.out
    if not output_path:
        output_path = args.pdf.replace('.pdf', '.tsv')
    
    with open(output_path, 'w') as f:
        write_tsv(rows, account_number or '', f)
    
    if args.debug:
        print(f'Output written to: {output_path}', file=sys.stderr)


if __name__ == '__main__':
    main()

