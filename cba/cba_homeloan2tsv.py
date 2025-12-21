#!/usr/bin/env python3
"""
Convert a CBA Home Loan statement PDF into a TSV with columns:
Date<TAB>Account Number<TAB>Transaction<TAB>Amount<TAB>Balance

Usage:
    python3 cba/cba_homeloan2tsv.py input.pdf [--out output.tsv] [--debug]
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
    
    Also validates that this is a CBA Home Loan statement.
    Skips notice letter pages at the beginning.
    
    Returns: (account_number, period_string, year)
    Raises: ValueError if not a CBA Home Loan statement
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available; please install it in the venv')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        raise ValueError('PDF has no pages')
    
    # helper: check if a page is a notice letter that should be skipped
    def is_notice_letter_page(page_text: str) -> bool:
        """Check if a page is a notice letter (e.g., 'Notice of increase to repayments for your home loan').
        
        The notice letter typically:
        - Contains "Notice of increase to repayments for your home loan"
        - Ends with "Yours sincerely" followed by "The CommBank Team"
        """
        text_lower = page_text.lower()
        # Check for the specific notice letter pattern
        has_notice_title = 'notice of increase to repayments for your home loan' in text_lower
        # Check if it ends with the signature block
        has_signature = 'yours sincerely' in text_lower and 'the commbank team' in text_lower
        
        # It's a notice letter if it has the title OR the signature block
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
        # Check if this page has "Home Loan Summary"
        if 'home loan summary' in page_text.lower():
            first_statement_page_idx = p_i
            if debug:
                print(f'Found statement starting on page {p_i+1}', file=sys.stderr)
            break
    
    if first_statement_page_idx is None:
        doc.close()
        raise ValueError('This does not appear to be a CBA Home Loan statement. Could not find "Home Loan Summary" after skipping notice letters.')
    
    first_page = doc[first_statement_page_idx]
    text = extract_text_from_page(first_page)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Validate that this is a Home Loan statement
    text_lower = ' '.join(lines).lower()
    if 'home loan summary' not in text_lower:
        doc.close()
        raise ValueError('This does not appear to be a CBA Home Loan statement. Could not find "Home Loan Summary" on the statement page.')
    
    # Check for CBA indicators (optional - if we have "Home Loan Summary", it's likely CBA)
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
    
    # If we found "Home Loan Summary", we're confident it's a home loan statement
    # CBA indicator is nice to have but not required
    if not is_cba and debug:
        print('Warning: Could not find explicit CBA indicators, but proceeding based on "Home Loan Summary"', file=sys.stderr)
    
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
        # Look for patterns like "25 Aug 2020 - 4 Nov 2020"
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
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})$', date_str.strip())
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
    
    # Remove $ and commas
    cleaned = cleaned.replace('$', '').replace(',', '').strip()
    
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
    
    # Remove $ and commas
    cleaned = cleaned.replace('$', '').replace(',', '').strip()
    
    try:
        amount = float(cleaned)
        return amount, is_debit
    except ValueError:
        return None, False


def parse_transactions(pdf_path: str, account_number: str, year: int, debug: bool = False) -> list:
    """
    Parse transactions from page 2 onwards.
    Returns list of [date, transaction, amount, balance] rows.
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available')
    
    doc = fitz.open(pdf_path)
    if len(doc) < 2:
        doc.close()
        return []
    
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    rows = []
    current_year = year
    last_month = None
    
    # Date pattern: DD MMM (standalone)
    date_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3})\s*$')
    
    # Skip patterns
    skip_blocks = ['borrowers', 'security address']
    skip_line_patterns = [
        r'fixed rate investment home loan transactions',
        r'standard variable rate home loan transactions',
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
        if 'home loan summary' in page_text.lower() or 'your statement' in page_text.lower():
            first_statement_page_idx = p_i
            break
    
    # Start from the page after the first statement page (where transactions typically are)
    # If no statement page found, start from page 2 as fallback
    if first_statement_page_idx is not None:
        start_page_idx = first_statement_page_idx + 1
    else:
        start_page_idx = 1
    
    if start_page_idx >= len(doc):
        start_page_idx = 1
    
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
            
            # Skip blocks
            if any(block in line_lower for block in skip_blocks):
                # Skip this line and continue until we find the next section
                i += 1
                continue
            
            # Skip specific lines
            if any(re.search(pattern, line_lower) for pattern in skip_line_patterns):
                i += 1
                continue
            
            # Look for table header: "Date", "Transaction description", "Debits", "Credits", "Balance"
            if not header_found:
                if 'date' in line_lower and 'transaction' in line_lower:
                    header_found = True
                    table_started = True
                    # Skip header lines (Date, Transaction description, Debits, Credits, Balance)
                    i += 5  # Skip the header rows
                    if debug:
                        print(f'Found table header on page {page_idx + 1}', file=sys.stderr)
                    continue
                elif line_lower.strip() == 'date':
                    # Check if next lines have transaction description, debits, credits, balance
                    if i + 4 < len(lines):
                        next_lines = [lines[i+j].lower() for j in range(1, 5)]
                        if ('transaction' in ' '.join(next_lines) and 
                            ('debit' in ' '.join(next_lines) or 'credit' in ' '.join(next_lines)) and
                            'balance' in ' '.join(next_lines)):
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
            # Check if this line is a date (DD MMM)
            date_match = date_pattern.match(line)
            if date_match:
                date_str = date_match.group(1)
                formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
                
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
                
                # Collect lines until we hit the next date or skip pattern
                collected_lines = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_lower = next_line.lower()
                    
                    # Stop if we hit another date
                    if date_pattern.match(next_line):
                        break
                    
                    # Stop if we hit a skip pattern
                    if any(re.search(pattern, next_lower) for pattern in skip_line_patterns):
                        break
                    
                    collected_lines.append(next_line)
                    j += 1
                
                # Parse collected lines: transaction description, then debit, credit, balance
                # Transaction description is typically the first non-amount line
                # Then we look for amounts in order: debit, credit, balance
                amount_found_count = 0
                for line in collected_lines:
                    line_lower = line.lower().strip()
                    
                    # Skip empty lines and "Nil"
                    if not line_lower or line_lower in ('nil', 'nill', 'nil.', '$'):
                        continue
                    
                    # Check if this line is an amount
                    # Pattern 1: Negative number (debit) like "-292.80"
                    negative_match = re.match(r'^-\s*([\d,]+\.?\d*)\s*$', line)
                    if negative_match:
                        if debit is None:
                            debit = parse_amount(negative_match.group(1))
                            amount_found_count += 1
                        continue
                    
                    # Pattern 2: Positive number with DR/CR (balance) like "$292.80 DR"
                    balance_match = re.search(r'[\$]?\s*([\d,]+\.?\d*)\s*(DR|CR)', line, re.I)
                    if balance_match:
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        amount_found_count += 1
                        continue
                    
                    # Pattern 3: Positive number (could be credit or balance without DR/CR)
                    # Check if it has DR/CR first (this would be balance)
                    if 'dr' in line_lower or 'cr' in line_lower:
                        # This is a balance with DR/CR
                        balance, balance_is_debit = parse_balance_with_dr_cr(line)
                        amount_found_count += 1
                        continue
                    
                    positive_match = re.match(r'^[\$]?\s*([\d,]+\.?\d*)\s*$', line)
                    if positive_match:
                        amt = parse_amount(positive_match.group(1))
                        if amt is not None and amt > 0:
                            # Determine if this is credit or balance based on context
                            # If we have a transaction description and no debit/credit yet, this is likely credit
                            # If we already have debit, this is credit
                            # If we already have credit, this is balance
                            if transaction_parts and debit is None and credit is None:
                                # We have transaction description, so this positive amount is likely a credit
                                credit = amt
                                amount_found_count += 1
                            elif debit is not None and credit is None:
                                credit = amt
                                amount_found_count += 1
                            elif credit is not None and balance is None:
                                # Could be balance without DR/CR, treat as positive
                                balance = amt
                                balance_is_debit = False
                                amount_found_count += 1
                            elif balance is None and not transaction_parts:
                                # No transaction description yet, could be credit or balance
                                # Prefer credit if we don't have one yet
                                if credit is None:
                                    credit = amt
                                    amount_found_count += 1
                                else:
                                    balance = amt
                                    balance_is_debit = False
                                    amount_found_count += 1
                        continue
                    
                    # If not an amount, it's transaction description
                    transaction_parts.append(line)
                
                # Skip if transaction description is "Opening Balance" or "Closing Balance"
                transaction = ' '.join(transaction_parts).strip()
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
            balance_str = ''
        
        out.write(f'{date}\t{account_number or ""}\t{transaction}\t{amount_str}\t{balance_str}\n')


def main():
    parser = argparse.ArgumentParser(description='Convert CBA Home Loan statement PDF to TSV')
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

