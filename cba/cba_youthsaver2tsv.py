#!/usr/bin/env python3
"""
Convert a CBA Youth Saver statement PDF into a TSV with columns:
Date<TAB>Account Number<TAB>Transaction<TAB>Amount<TAB>Balance

Usage:
    python3 cba/cba_youthsaver2tsv.py input.pdf [--out output.tsv] [--debug]
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
    
    Also validates that this is a CBA Youth Saver statement.
    Skips notice letter pages at the beginning.
    
    Returns: (account_number, period_string, year)
    Raises: ValueError if not a CBA Youth Saver statement
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available; please install it in the venv')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        raise ValueError('PDF has no pages')
    
    # helper: check if a page is a notice letter that should be skipped
    def is_notice_letter_page(page_text: str) -> bool:
        """Check if a page is a notice letter."""
        text_lower = page_text.lower()
        has_notice_title = 'notice of increase to repayments for your home loan' in text_lower
        has_signature = 'yours sincerely' in text_lower and 'the commbank team' in text_lower
        return has_notice_title or has_signature
    
    # Find the first actual statement page (skip notice letters)
    first_statement_page_idx = None
    for p_i in range(len(doc)):
        page = doc[p_i]
        page_text = extract_text_from_page(page)
        if is_notice_letter_page(page_text):
            if debug:
                print(f'Skipping page {p_i+1}: notice letter page', file=sys.stderr)
            continue
        # Check if this page has "Youth Saver" or "Youthsaver" (both variations exist)
        if 'youth saver' in page_text.lower() or 'youthsaver' in page_text.lower():
            first_statement_page_idx = p_i
            if debug:
                print(f'Found statement starting on page {p_i+1}', file=sys.stderr)
            break
    
    if first_statement_page_idx is None:
        doc.close()
        raise ValueError('This does not appear to be a CBA Youth Saver statement. Could not find "Youth Saver" or "Youthsaver" after skipping notice letters.')
    
    first_page = doc[first_statement_page_idx]
    text = extract_text_from_page(first_page)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Validate that this is a Youth Saver statement
    text_lower = ' '.join(lines).lower()
    if 'youth saver' not in text_lower and 'youthsaver' not in text_lower:
        doc.close()
        raise ValueError('This does not appear to be a CBA Youth Saver statement. Could not find "Youth Saver" or "Youthsaver" on the statement page.')
    
    # Check for CBA indicators (optional - if we have "Youth Saver", it's likely CBA)
    is_cba = False
    cba_indicators = [
        'commonwealth bank',
        'commbank',
        'cba',
        'commonwealth bank of australia'
    ]
    for indicator in cba_indicators:
        if indicator in text_lower:
            is_cba = True
            if debug:
                print(f'Found CBA indicator: {indicator}', file=sys.stderr)
            break
    
    # If we found "Youth Saver", we're confident it's a youth saver statement
    # CBA indicator is nice to have but not required
    if not is_cba and debug:
        print('Warning: Could not find explicit CBA indicators, but proceeding based on "Youth Saver"', file=sys.stderr)
    
    account_number = None
    period_string = None
    year = None
    
    # Extract account number
    # Pattern: "Account number" followed by digits
    for i, line in enumerate(lines):
        if re.search(r'(?i)account\s+number', line):
            # Check current line for digits
            m = re.search(r'(?i)account\s+number[:\s]+([\d\s-]{6,})', line)
            if m:
                account_number = re.sub(r'\s+', ' ', m.group(1).strip())
                if debug:
                    print(f'Found account number: {account_number}', file=sys.stderr)
                break
            # Check next line if current line is just "Account number"
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[\d\s-]{6,}$', next_line):
                    account_number = re.sub(r'\s+', ' ', next_line).strip()
                    if debug:
                        print(f'Found account number: {account_number}', file=sys.stderr)
                    break
    
    # Extract statement period and year
    for line in lines:
        # Look for patterns like "24 Aug 2020 - 31 Dec 2020"
        m = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', line)
        if m:
            period_string = m.group(0)
            # Extract year from start date
            start_date_str = m.group(1)
            year_match = re.search(r'(\d{4})', start_date_str)
            if year_match:
                year = int(year_match.group(1))
            if debug:
                print(f'Found period: {period_string}, year: {year}', file=sys.stderr)
            break
    
    doc.close()
    
    if not account_number:
        print('Warning: Could not find account number on first page', file=sys.stderr)
    
    if not period_string or year is None:
        raise ValueError('Could not find statement period on first page')
    
    return account_number or '', period_string, year


def parse_date_dd_mmm(date_str: str, current_year: int, last_month: Optional[int], month_map: dict) -> Optional[str]:
    """
    Parse date in "DD MMM" format and convert to "DD/MM/YYYY".
    Handles year transitions (e.g., Dec -> Jan increments year).
    """
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})\s*$', date_str.strip())
    if not m:
        return None
    
    day = int(m.group(1))
    mon_str = m.group(2).lower()[:3]
    
    month_num = month_map.get(mon_str)
    if month_num is None:
        return None
    
    # Detect year transition: if current month < last month, we've rolled over
    # (e.g., last_month=12 (Dec), current month=1 (Jan) means year increased)
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


def parse_transactions(pdf_path: str, account_number: str, year: int, debug: bool = False) -> list:
    """
    Parse transactions from all pages (including first page if it has a table).
    Returns list of [date, transaction, amount, balance] rows.
    
    Column structure: DATE, TRANSACTION DETAILS, + IN, - OUT, BALANCE
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
    
    # Date patterns: DD MMM (standalone) or DD MMM YYYY (with year)
    date_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3})\s*$')
    date_with_year_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*$')
    
    # Skip patterns
    skip_line_patterns = [
        r'interest rate as of',
        r'interest rate applied to',
        r'change in interest rate'
    ]
    
    # helper: check if a page is a notice letter that should be skipped
    def is_notice_letter_page(page_text: str) -> bool:
        """Check if a page is a notice letter."""
        text_lower = page_text.lower()
        has_notice_title = 'notice of increase to repayments for your home loan' in text_lower
        has_signature = 'yours sincerely' in text_lower and 'the commbank team' in text_lower
        return has_notice_title or has_signature
    
    # Find the first statement page (skip notice letters)
    first_statement_page_idx = None
    for p_i in range(len(doc)):
        page = doc[p_i]
        page_text = extract_text_from_page(page)
        if is_notice_letter_page(page_text):
            if debug:
                print(f'Skipping page {p_i+1} in transaction parser: notice letter page', file=sys.stderr)
            continue
        # Check if this page has statement content
        if 'youth saver' in page_text.lower() or 'youthsaver' in page_text.lower() or 'your statement' in page_text.lower():
            first_statement_page_idx = p_i
            break
    
    if first_statement_page_idx is None:
        doc.close()
        return []
    
    # Start from the first statement page (it may have transactions)
    start_page_idx = first_statement_page_idx
    
    for page_idx in range(start_page_idx, len(doc)):
        page = doc[page_idx]
        text = extract_text_from_page(page)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # Skip header and find table start
        table_started = False
        header_found = False
        i = 0
        
        while i < len(lines):
            line = lines[i]
            line_lower = line.lower()
            
            # Skip specific lines
            if any(re.search(pattern, line_lower) for pattern in skip_line_patterns):
                i += 1
                continue
            
            # Look for table header: "DATE", "TRANSACTION DETAILS", "+ IN", "- OUT", "BALANCE"
            if not header_found:
                # Check for header with "+ IN" and "- OUT" (unique to Youth Saver)
                if ('date' in line_lower and 'transaction' in line_lower) or \
                   ('+ in' in line_lower and '- out' in line_lower) or \
                   (line_lower.strip() == 'date' and i + 4 < len(lines) and 
                    ('transaction' in lines[i+1].lower() or '+ in' in ' '.join(lines[i+1:i+5]).lower())):
                    header_found = True
                    table_started = True
                    # Skip header lines (typically 4-5 lines: DATE, TRANSACTION DETAILS, + IN, - OUT, BALANCE)
                    i += 5  # Skip the header rows
                    if debug:
                        print(f'Found table header on page {page_idx + 1}', file=sys.stderr)
                    continue
                elif line_lower.strip() == 'date':
                    # Check if next lines have transaction details, + in, - out, balance
                    if i + 4 < len(lines):
                        next_lines = [lines[i+j].lower() for j in range(1, 5)]
                        if ('transaction' in ' '.join(next_lines) or '+ in' in ' '.join(next_lines)) and \
                           ('- out' in ' '.join(next_lines) or 'out' in ' '.join(next_lines)) and \
                           'balance' in ' '.join(next_lines):
                            header_found = True
                            table_started = True
                            i += 5  # Skip header rows
                            if debug:
                                print(f'Found table header on page {page_idx + 1} (multi-line)', file=sys.stderr)
                            continue
            
            if not table_started:
                i += 1
                continue
            
            # Parse transaction rows
            # Check if this line starts with a date (DD MMM or DD MMM YYYY), possibly followed by transaction description
            date_with_year_match = date_with_year_pattern.match(line)
            date_match = date_pattern.match(line)
            
            # Also check if line starts with a date pattern (even if followed by text)
            date_at_start_with_year = re.match(r'^(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+(.+)', line)
            date_at_start = re.match(r'^(\d{1,2}\s+[A-Za-z]{3})\s+(.+)', line)
            
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
                if year_match:
                    current_year = int(year_match.group(1))
                # Extract just DD MMM part
                date_str = re.match(r'^(\d{1,2}\s+[A-Za-z]{3})', date_str_with_year).group(1)
                formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
            elif date_match or date_at_start:
                if date_at_start:
                    date_str = date_at_start.group(1)
                    transaction_start_on_same_line = date_at_start.group(2).strip()
                else:
                    date_str = date_match.group(1)
                formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
            
            if formatted_date:
                # Update current_year and last_month
                date_parts = formatted_date.split('/')
                if len(date_parts) == 3:
                    current_year = int(date_parts[2])
                    last_month = int(date_parts[1])
                
                # Collect transaction description and amounts from following lines
                # The structure is: Date, Transaction details, + IN, - OUT, Balance
                transaction_parts = []
                credit = None  # + IN
                debit = None   # - OUT
                balance = None
                balance_is_debit = False
                
                # If transaction description started on the same line as the date, add it
                if transaction_start_on_same_line:
                    transaction_parts.append(transaction_start_on_same_line)
                
                # Collect lines until we hit the next date or skip pattern
                collected_lines = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_lower = next_line.lower()
                    
                    # Stop if we hit another date (check if line starts with date pattern)
                    # But be careful - don't stop on lines that just contain a date in the middle
                    if date_pattern.match(next_line) or date_with_year_pattern.match(next_line):
                        # This line is just a date, so it's the start of the next transaction
                        break
                    # Also check if line starts with date pattern (even if followed by text)
                    date_at_start = re.match(r'^(\d{1,2}\s+[A-Za-z]{3})\s+(.+)', next_line)
                    if date_at_start:
                        # This line starts with a date followed by text, so it's the next transaction
                        break
                    
                    # Stop if we hit a skip pattern
                    if any(re.search(pattern, next_lower) for pattern in skip_line_patterns):
                        break
                    
                    collected_lines.append(next_line)
                    j += 1
                
                # Parse collected lines: transaction description, then + IN, - OUT, balance
                # In Youth Saver format, the order is typically:
                # 1. Transaction description (one or more lines)
                # 2. + IN amount (credit) - standalone number or line starting with "+"
                # 3. - OUT amount (debit) - standalone number or line starting with "-"
                # 4. Balance - number with $ and possibly CR/DR
                # If + IN column is blank/Nil, then the next number is in - OUT column (debit)
                line_idx = 0
                saw_blank_after_transaction = False  # Track if we saw blank/Nil after transaction description
                while line_idx < len(collected_lines):
                    line = collected_lines[line_idx]
                    line_lower = line.lower().strip()
                    
                    # Track empty lines and "Nil" - they indicate + IN column is empty
                    # But only if we haven't seen any amounts yet
                    if not line_lower or line_lower in ('nil', 'nill', 'nil.', '$'):
                        # If we have transaction description and no amounts yet, this blank indicates + IN is empty
                        if transaction_parts and credit is None and debit is None:
                            saw_blank_after_transaction = True
                            if debug:
                                print(f'  Saw blank/Nil after transaction description, + IN column is empty', file=sys.stderr)
                        line_idx += 1
                        continue
                    
                    # Pattern 1: Check for balance with DR/CR (balance) like "$292.80 DR" or "$8,835.67 CR"
                    balance_match = re.search(r'[\$]?\s*([\d,]+\.?\d*)\s*(DR|CR)', line, re.I)
                    if balance_match:
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        line_idx += 1
                        continue
                    
                    # Pattern 2: Check if it has DR/CR as a suffix or separate word (this would be balance)
                    # Be careful: "Credit Interest" contains "cr" but is not a balance
                    # Check for DR/CR at the end of the line or as a separate word
                    if re.search(r'\b(DR|CR)\b$', line, re.I) or re.search(r'\$\s*[\d,]+\.?\d*\s*(DR|CR)\b', line, re.I):
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        line_idx += 1
                        continue
                    
                    # Pattern 3: Line starting with "+" (this is + IN / credit)
                    if line.strip().startswith('+'):
                        # This is a + IN (credit)
                        amt_str = line.strip()[1:].strip()  # Remove the "+"
                        amt = parse_amount(amt_str)
                        if amt is not None and amt > 0 and credit is None:
                            credit = amt
                        line_idx += 1
                        continue
                    
                    # Pattern 4: Line starting with "-" (this is - OUT / debit)
                    elif line.strip().startswith('-'):
                        # This is a - OUT (debit)
                        amt_str = line.strip()[1:].strip()  # Remove the "-"
                        amt = parse_amount(amt_str)
                        if amt is not None and amt > 0 and debit is None:
                            debit = amt
                        line_idx += 1
                        continue
                    
                    # Pattern 5: Standalone number (could be + IN, - OUT, or balance)
                    # Check if this is likely a transaction ID (very long number without decimal point)
                    standalone_number = re.match(r'^([\d,]+\.?\d*)\s*$', line)
                    if standalone_number:
                        number_str = standalone_number.group(1).replace(',', '')
                        is_likely_transaction_id = ('.' not in number_str and len(number_str) > 10)
                        
                        if is_likely_transaction_id:
                            # Skip transaction ID
                            line_idx += 1
                            continue
                        
                        # This is a standalone number - could be + IN, - OUT, or balance
                        # In Youth Saver format, the columns are: DATE | TRANSACTION DETAILS | + IN | - OUT | BALANCE
                        # If we saw a blank/Nil after transaction description, + IN column is empty, so this is - OUT (debit)
                        # If we already have credit, the next number is - OUT (debit)
                        # If we have both, it's balance
                        amt = parse_amount(standalone_number.group(1))
                        if amt is not None and amt > 0:
                            if transaction_parts and credit is None and debit is None:
                                # We have transaction description
                                # Check if there's a blank line BEFORE this number in collected_lines
                                # (the blank line would be at line_idx - 1, but we've already skipped it)
                                # So check if the previous non-empty line was part of transaction description
                                # If we've seen transaction_parts but no blank, check if previous line was blank
                                prev_was_blank = False
                                if line_idx > 0:
                                    # Check previous lines (going backwards) to see if any were blank
                                    for prev_idx in range(line_idx - 1, -1, -1):
                                        prev_line = collected_lines[prev_idx].strip().lower()
                                        if not prev_line or prev_line in ('nil', 'nill', 'nil.', '$'):
                                            # Found a blank line - check if it was after transaction description
                                            # (i.e., all lines before it were transaction description)
                                            all_before_were_trans = True
                                            for check_idx in range(prev_idx):
                                                check_line = collected_lines[check_idx].strip().lower()
                                                # Skip if it was a blank or if it looks like an amount/balance
                                                if not check_line or check_line in ('nil', 'nill', 'nil.', '$'):
                                                    continue
                                                # Check if it's a number (amount) or balance
                                                if re.match(r'^([\d,]+\.?\d*)\s*$', collected_lines[check_idx]) or \
                                                   re.search(r'\$|DR|CR', check_line):
                                                    all_before_were_trans = False
                                                    break
                                            if all_before_were_trans:
                                                prev_was_blank = True
                                                break
                                        else:
                                            # Found a non-blank line - stop looking
                                            break
                                
                                if saw_blank_after_transaction or prev_was_blank:
                                    # We saw blank/Nil after transaction, so + IN column is empty
                                    # This number is in - OUT column (debit)
                                    debit = amt
                                    saw_blank_after_transaction = False  # Reset flag
                                    if debug:
                                        print(f'  Assigned {amt} as debit (saw blank after transaction)', file=sys.stderr)
                                else:
                                    # No blank seen, so this number is in + IN column (credit)
                                    credit = amt
                                    if debug:
                                        print(f'  Assigned {amt} as credit (no blank after transaction)', file=sys.stderr)
                            elif credit is not None and debit is None:
                                # We have credit, so this is - OUT (debit)
                                debit = amt
                            elif credit is not None and debit is not None and balance is None:
                                # We have both credit and debit, so this is balance
                                balance = amt
                                balance_is_debit = False
                            elif balance is None and not transaction_parts:
                                # No transaction description yet - this is likely + IN (credit)
                                if credit is None:
                                    credit = amt
                                elif debit is None:
                                    debit = amt
                                else:
                                    balance = amt
                                    balance_is_debit = False
                        line_idx += 1
                        continue
                    
                    # Pattern 6: Positive number with $ (likely balance)
                    # But make sure it's actually a number, not text that happens to have $
                    positive_match = re.match(r'^[\$]\s*([\d,]+\.?\d*)\s*$', line)
                    if positive_match:
                        amt = parse_amount(positive_match.group(1))
                        if amt is not None and amt > 0 and balance is None:
                            balance = amt
                            balance_is_debit = False
                        line_idx += 1
                        continue
                    
                    # If not an amount, it's transaction description
                    transaction_parts.append(line)
                    line_idx += 1
                
                # Skip if transaction description is "Opening Balance" or "Closing Balance"
                transaction = ' '.join(transaction_parts).strip()
                # Clean up transaction description - remove any trailing metadata
                # Sometimes "Closing balance" gets merged with following text
                if 'closing balance' in transaction.lower():
                    # Check if it's just "Closing balance" or has extra text
                    trans_lower = transaction.lower()
                    if trans_lower.startswith('closing balance'):
                        # Extract just "Closing balance" part, ignore the rest
                        closing_match = re.match(r'^([Cc]losing\s+[Bb]alance).*', transaction)
                        if closing_match:
                            transaction = closing_match.group(1)
                
                trans_lower = transaction.lower()
                if 'opening balance' in trans_lower or 'closing balance' in trans_lower:
                    if debug:
                        print(f'Skipping transaction: {transaction}', file=sys.stderr)
                    i = j
                    continue
                
                # Determine amount: either debit (- OUT) or credit (+ IN), not both
                # If we have a credit amount but the balance decreased, it's actually a debit
                amount = None
                if debit is not None and debit > 0:
                    amount = -debit  # Debit is negative
                elif credit is not None and credit > 0:
                    # Check balance change to verify if this is actually a debit
                    if balance is not None and len(rows) > 0:
                        # Get previous balance
                        prev_balance = None
                        for prev_row in reversed(rows):
                            if prev_row[3] is not None:  # Balance column
                                try:
                                    prev_balance_val = prev_row[3]
                                    if isinstance(prev_balance_val, (int, float)):
                                        prev_balance = float(prev_balance_val)
                                    else:
                                        prev_balance = float(str(prev_balance_val).replace(',', '').replace('$', ''))
                                    break
                                except:
                                    pass
                        
                        if prev_balance is not None:
                            try:
                                current_balance_val = balance
                                if isinstance(current_balance_val, (int, float)):
                                    current_balance = float(current_balance_val)
                                else:
                                    current_balance = float(str(current_balance_val).replace(',', '').replace('$', ''))
                                balance_change = current_balance - prev_balance
                                # If balance decreased by approximately the credit amount, it's actually a debit
                                if abs(balance_change + credit) < 0.01:  # Balance decreased by credit amount
                                    # This is actually a debit (the number was in - OUT column, not + IN)
                                    amount = -credit  # Make it negative
                                    if debug:
                                        print(f'  Corrected: balance decreased by {credit}, so this is a debit', file=sys.stderr)
                                else:
                                    # Balance increased or stayed same - it's a credit
                                    amount = credit
                            except:
                                amount = credit
                    else:
                        amount = credit  # No previous balance to compare, assume credit
                elif balance is not None and len(rows) > 0:
                    # We have balance but no amount yet - use balance change to infer
                    prev_balance = None
                    for prev_row in reversed(rows):
                        if prev_row[3] is not None:
                            try:
                                prev_balance_val = prev_row[3]
                                if isinstance(prev_balance_val, (int, float)):
                                    prev_balance = float(prev_balance_val)
                                else:
                                    prev_balance = float(str(prev_balance_val).replace(',', '').replace('$', ''))
                                break
                            except:
                                pass
                    
                    if prev_balance is not None:
                        try:
                            current_balance_val = balance
                            if isinstance(current_balance_val, (int, float)):
                                current_balance = float(current_balance_val)
                            else:
                                current_balance = float(str(current_balance_val).replace(',', '').replace('$', ''))
                            balance_change = current_balance - prev_balance
                            amount = balance_change  # Negative if debit, positive if credit
                        except:
                            pass
                
                # Format balance: if it ends in DR, make it negative; if CR, make it positive
                if balance is not None:
                    if balance_is_debit:
                        balance = -abs(balance)  # DR means debit (negative)
                    else:
                        balance = abs(balance)  # CR means credit (positive), or no suffix means positive
                
                if amount is not None or balance is not None:
                    rows.append([formatted_date, transaction, amount, balance])
                    if debug:
                        print(f'Transaction: {formatted_date} | {transaction[:50]} | Amount: {amount} | Balance: {balance}', file=sys.stderr)
                
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
    parser = argparse.ArgumentParser(description='Convert CBA Youth Saver statement PDF to TSV')
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

