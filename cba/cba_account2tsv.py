#!/usr/bin/env python3
"""
Convert a CBA Everyday Account statement PDF into a TSV with columns:
Date<TAB>Account Number<TAB>Transaction<TAB>Amount<TAB>Balance

Usage:
    python3 cba/cba_account2tsv.py input.pdf [--out output.tsv] [--debug]
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
    
    Also validates that this is a CBA Everyday Account statement (Everyday Offset, Smart Access, or NetBank Saver).
    Skips notice letter pages at the beginning.
    
    Returns: (account_number, period_string, year)
    Raises: ValueError if not a CBA Everyday Account statement
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available; please install it in the venv')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        raise ValueError('PDF has no pages')
    
    # helper: check if a page is a notice letter that should be skipped
    def is_notice_letter_page(page_text: str) -> bool:
        """Check if a page is a notice letter (e.g., 'Notice of increase to repayments for your home loan')."""
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
        # Check if this page has "Everyday Offset", "Smart Access", or "NetBank Saver"
        if 'everyday offset' in page_text.lower() or 'smart access' in page_text.lower() or 'netbank saver' in page_text.lower():
            first_statement_page_idx = p_i
            if debug:
                if 'everyday offset' in page_text.lower():
                    account_type = 'Everyday Offset'
                elif 'smart access' in page_text.lower():
                    account_type = 'Smart Access'
                else:
                    account_type = 'NetBank Saver'
                print(f'Found statement starting on page {p_i+1} ({account_type})', file=sys.stderr)
            break
    
    if first_statement_page_idx is None:
        doc.close()
        raise ValueError('This does not appear to be a CBA Everyday Account statement. Could not find "Everyday Offset", "Smart Access", or "NetBank Saver" after skipping notice letters.')
    
    first_page = doc[first_statement_page_idx]
    text = extract_text_from_page(first_page)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Validate that this is an Everyday Account statement
    text_lower = ' '.join(lines).lower()
    if 'everyday offset' not in text_lower and 'smart access' not in text_lower and 'netbank saver' not in text_lower:
        doc.close()
        raise ValueError('This does not appear to be a CBA Everyday Account statement. Could not find "Everyday Offset", "Smart Access", or "NetBank Saver" on the statement page.')
    
    # Check for CBA indicators (optional - if we have account type, it's likely CBA)
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
    
    # If we found account type, we're confident it's an everyday account statement
    # CBA indicator is nice to have but not required
    if not is_cba and debug:
        if 'everyday offset' in text_lower:
            account_type = 'Everyday Offset'
        elif 'smart access' in text_lower:
            account_type = 'Smart Access'
        else:
            account_type = 'NetBank Saver'
        print(f'Warning: Could not find explicit CBA indicators, but proceeding based on "{account_type}"', file=sys.stderr)
    
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
    
    # Remove $, commas, and parentheses (which indicate negative)
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
        if 'everyday offset' in page_text.lower() or 'smart access' in page_text.lower() or 'netbank saver' in page_text.lower() or 'your statement' in page_text.lower():
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
            
            # Look for table header: "Date", "Transaction", "Debit", "Credit", "Balance"
            if not header_found:
                if 'date' in line_lower and 'transaction' in line_lower:
                    header_found = True
                    table_started = True
                    # Skip header lines: "Date Transaction", "Debit", "Credit", "Balance" (4 lines total)
                    i += 4  # Skip the header rows
                    if debug:
                        print(f'Found table header on page {page_idx + 1}', file=sys.stderr)
                    continue
                elif line_lower.strip() == 'date':
                    # Check if next lines have transaction, debit, credit, balance
                    if i + 4 < len(lines):
                        next_lines = [lines[i+j].lower() for j in range(1, 5)]
                        if ('transaction' in ' '.join(next_lines) and 
                            ('debit' in ' '.join(next_lines) or 'credit' in ' '.join(next_lines)) and
                            'balance' in ' '.join(next_lines)):
                            header_found = True
                            table_started = True
                            # Skip: "Date", "Transaction", "Debit", "Credit", "Balance" (5 lines total)
                            i += 5  # Skip header rows
                            if debug:
                                print(f'Found table header on page {page_idx + 1} (multi-line)', file=sys.stderr)
                            continue
                # Also check for partial header on first page (might just have "Date Transaction Debit")
                elif line_lower.strip() == 'date' and 'transaction' in lines[i+1].lower() if i+1 < len(lines) else False:
                    # Check if debit is on next line
                    if i + 2 < len(lines) and 'debit' in lines[i+2].lower():
                        header_found = True
                        table_started = True
                        i += 3  # Skip Date, Transaction, Debit lines
                        if debug:
                            print(f'Found partial table header on page {page_idx + 1}', file=sys.stderr)
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
                
                if not formatted_date:
                    i += 1
                    continue
                
                # Update current_year and last_month
                date_parts = formatted_date.split('/')
                if len(date_parts) == 3:
                    current_year = int(date_parts[2])
                    last_month = int(date_parts[1])
                
                # Collect transaction description and amounts from following lines
                # The structure is: Date, Transaction description, Debits, Credits, Balance
                transaction_parts = []
                debit = None
                credit = None
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
                    if date_pattern.match(next_line) or date_with_year_pattern.match(next_line) or re.match(r'^(\d{1,2}\s+[A-Za-z]{3})', next_line):
                        break
                    
                    # Stop if we hit a skip pattern
                    if any(re.search(pattern, next_lower) for pattern in skip_line_patterns):
                        break
                    
                    collected_lines.append(next_line)
                    j += 1
                
                # Parse collected lines: transaction description, then debit, credit, balance
                # Strategy: Collect all text lines as description first, then parse amounts
                # A line is description if it contains letters or is not a pure number
                
                line_idx = 0
                # First pass: collect all description lines (lines with letters or non-numeric content)
                while line_idx < len(collected_lines):
                    line = collected_lines[line_idx]
                    line_lower = line.lower().strip()
                    
                    # Skip empty lines and "Nil"
                    if not line_lower or line_lower in ('nil', 'nill', 'nil.', '$'):
                        line_idx += 1
                        continue
                    
                    # Check if this line contains letters (it's text, so it's description)
                    if re.search(r'[a-zA-Z]', line):
                        transaction_parts.append(line)
                        line_idx += 1
                        continue
                    
                    # Check if this is clearly an amount (pure number patterns)
                    # Pattern 1: Negative number (debit) like "-292.80"
                    if re.match(r'^-\s*[\d,]+\.?\d*\s*$', line):
                        # This is an amount, stop collecting description
                        break
                    
                    # Pattern 2: Positive number with DR/CR (balance) like "$292.80 DR"
                    if re.search(r'[\$]?\s*[\d,]+\.?\d*\s*(DR|CR)', line, re.I):
                        # This is a balance, stop collecting description
                        break
                    
                    # Pattern 3: Dollar amount with decimal (like "$5,167.11") - check if next line is balance
                    dollar_amount_match = re.match(r'^[\$]?\s*([\d,]+\.\d{2})\s*$', line)
                    if dollar_amount_match:
                        # Check if next line is a balance (has DR/CR or starts with $)
                        if line_idx + 1 < len(collected_lines):
                            next_line = collected_lines[line_idx + 1]
                            if re.search(r'(DR|CR)', next_line, re.I) or next_line.strip().startswith('$'):
                                # Next line is balance, so this is an amount
                                break
                        # If we have description and this looks like an amount, it's likely an amount
                        if transaction_parts:
                            break
                    
                    # Pattern 4: Standalone number - check context
                    standalone_number = re.match(r'^([\d,]+\.?\d*)\s*$', line)
                    if standalone_number:
                        number_str = standalone_number.group(1).replace(',', '')
                        
                        # Check if it's a transaction ID (6+ digits, no decimal)
                        is_likely_transaction_id = ('.' not in number_str and len(number_str) >= 6)
                        if is_likely_transaction_id:
                            # Check if next line is "$" followed by an amount
                            if line_idx + 1 < len(collected_lines):
                                next_line = collected_lines[line_idx + 1].strip()
                                if next_line == '$' and line_idx + 2 < len(collected_lines):
                                    third_line = collected_lines[line_idx + 2].strip()
                                    if re.match(r'^[\$]?\s*[\d,]+\.\d{2}', third_line):
                                        # This is a transaction ID, add to description
                                        transaction_parts.append(line)
                                        line_idx += 1
                                        continue
                            # Very long numbers (10+ digits) are transaction IDs
                            if len(number_str) > 10:
                                transaction_parts.append(line)
                                line_idx += 1
                                continue
                        
                        # Check if next line is "(" or "$" (indicates debit amount)
                        if line_idx + 1 < len(collected_lines):
                            next_line = collected_lines[line_idx + 1].strip()
                            if next_line == '(' or next_line == '$':
                                # This is a debit amount, stop collecting description
                                break
                        
                        # If it's a number with decimal and we already have description, it's likely an amount
                        if '.' in number_str and transaction_parts:
                            # But wait - check if next line has text, then it might still be description
                            if line_idx + 1 < len(collected_lines):
                                next_line = collected_lines[line_idx + 1]
                                if re.search(r'[a-zA-Z]', next_line):
                                    # Next line has text, so this number might be part of description
                                    transaction_parts.append(line)
                                    line_idx += 1
                                    continue
                            # No text after, so it's an amount
                            break
                    
                    # Pattern 5: Standalone line with parentheses like "(300.00)"
                    if re.match(r'^\([\d,]+\.?\d*\)\s*$', line):
                        # This is an amount, stop collecting description
                        break
                    
                    # If we get here and it's not clearly an amount, add to description
                    transaction_parts.append(line)
                    line_idx += 1
                
                # Second pass: parse amounts from remaining lines
                while line_idx < len(collected_lines):
                    line = collected_lines[line_idx]
                    line_lower = line.lower().strip()
                    
                    # Skip empty lines and "Nil"
                    if not line_lower or line_lower in ('nil', 'nill', 'nil.', '$'):
                        line_idx += 1
                        continue
                    
                    # Check if this line is just an amount (not part of description)
                    # Pattern 1: Negative number (debit) like "-292.80"
                    negative_match = re.match(r'^-\s*([\d,]+\.?\d*)\s*$', line)
                    if negative_match:
                        if debit is None:
                            debit = parse_amount(negative_match.group(1))
                        line_idx += 1
                        continue
                    
                    # Pattern 1b: Number followed by standalone "(" or "$" on next line (indicates debit)
                    standalone_number = re.match(r'^([\d,]+\.?\d*)\s*$', line)
                    if standalone_number:
                        # Check if next line is "(" or "$" (both indicate debit in different statement formats)
                        if line_idx + 1 < len(collected_lines):
                            next_line = collected_lines[line_idx + 1].strip()
                            if next_line == '(' or next_line == '$':
                                # This is a debit amount
                                amt = parse_amount(standalone_number.group(1))
                                if amt is not None and amt > 0 and debit is None:
                                    debit = amt
                                    line_idx += 2  # Skip both the number and the "(" or "$"
                                    continue
                    
                    # Pattern 1c: Standalone line with just parentheses (indicates negative/debit) like "(300.00)"
                    if re.match(r'^\([\d,]+\.?\d*\)\s*$', line):
                        # Extract number from parentheses
                        paren_match = re.search(r'\(([\d,]+\.?\d*)\)', line)
                        if paren_match and debit is None:
                            debit = parse_amount(paren_match.group(1))
                        line_idx += 1
                        continue
                    
                    # Pattern 1d: Standalone "(" or "$" line - skip it (already handled above)
                    if line.strip() in ('(', '$'):
                        line_idx += 1
                        continue
                    
                    # Pattern 2: Positive number with DR/CR (balance) like "$292.80 DR" or "$8,835.67 CR"
                    balance_match = re.search(r'[\$]?\s*([\d,]+\.?\d*)\s*(DR|CR)', line, re.I)
                    if balance_match:
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        line_idx += 1
                        continue
                    
                    # Pattern 3: Positive number (could be credit or balance without DR/CR)
                    # Check if it has DR/CR first (this would be balance)
                    if 'dr' in line_lower or 'cr' in line_lower:
                        # This is a balance with DR/CR
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        line_idx += 1
                        continue
                    
                    positive_match = re.match(r'^[\$]?\s*([\d,]+\.?\d*)\s*$', line)
                    if positive_match:
                        # Check if this is likely a transaction ID (very long number without decimal point)
                        # Transaction IDs are typically 10+ digits, amounts are typically shorter
                        number_str = positive_match.group(1).replace(',', '')
                        if '.' not in number_str and len(number_str) > 10:
                            # This is likely a transaction ID, add to description
                            if transaction_parts:
                                transaction_parts.append(line)
                                line_idx += 1
                                continue
                            else:
                                # No transaction description yet, skip it
                                line_idx += 1
                                continue
                        
                        amt = parse_amount(positive_match.group(1))
                        if amt is not None and amt >= 0:  # Allow 0.00 as valid amount
                            # Determine if this is credit or balance based on context
                            # If we have a transaction description and no debit/credit yet, this is likely credit
                            # If we already have debit, this is credit
                            # If we already have credit, this is balance
                            # If we have transaction description and already have debit/credit, this is likely balance
                            if transaction_parts and debit is None and credit is None:
                                # We have transaction description, so this positive amount is likely a credit
                                # But if it's 0.00, it's more likely the balance
                                if amt == 0.0:
                                    balance = amt
                                    balance_is_debit = False
                                else:
                                    credit = amt
                            elif debit is not None and credit is None:
                                # If we have a debit and this is 0.00, it's likely the balance
                                if amt == 0.0:
                                    balance = amt
                                    balance_is_debit = False
                                else:
                                    credit = amt
                            elif credit is not None and balance is None:
                                # Could be balance without DR/CR, treat as positive
                                balance = amt
                                balance_is_debit = False
                            elif balance is None and not transaction_parts:
                                # No transaction description yet, could be credit or balance
                                # Prefer credit if we don't have one yet
                                if credit is None:
                                    credit = amt
                                else:
                                    balance = amt
                                    balance_is_debit = False
                            elif transaction_parts and balance is None:
                                # We have transaction description and no balance yet, this is likely the balance
                                balance = amt
                                balance_is_debit = False
                        line_idx += 1
                        continue
                    
                    # If not an amount, it's transaction description
                    transaction_parts.append(line)
                    line_idx += 1
                
                # Skip if transaction description is "Opening Balance" or "Closing Balance"
                transaction = ' '.join(transaction_parts).strip()
                # Clean up trailing parentheses and other artifacts
                transaction = re.sub(r'\s*\(\s*$', '', transaction).strip()
                trans_lower = transaction.lower()
                if 'opening balance' in trans_lower or 'closing balance' in trans_lower:
                    if debug:
                        print(f'Skipping transaction: {transaction}', file=sys.stderr)
                    i = j
                    continue
                
                # Determine amount: either debit or credit, not both
                amount = None
                if debit is not None and debit > 0:
                    amount = -debit  # Debit is negative
                elif credit is not None and credit > 0:
                    amount = credit  # Credit is positive
                
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
            # If balance is None, check if it should be 0.00
            # For now, leave as blank if truly None (not parsed)
            balance_str = ''
        
        out.write(f'{date}\t{account_number or ""}\t{transaction}\t{amount_str}\t{balance_str}\n')


def main():
    parser = argparse.ArgumentParser(description='Convert CBA Everyday Account statement PDF to TSV')
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

