#!/usr/bin/env python3
"""
Convert a CBA Mastercard statement PDF into a TSV with columns:
Date<TAB>Card Number<TAB>Transaction<TAB>Amount<TAB>Balance

Usage:
    python3 cba/cba_mastercard2tsv.py input.pdf [--out output.tsv] [--debug]
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


def is_mastercard_number(card_number: str) -> bool:
    """
    Check if a credit card number is a Mastercard.
    Mastercard numbers start with:
    - 51-55 (old range, 16 digits)
    - 2221-2720 (new range, 16-19 digits)
    """
    if not card_number:
        return False
    # Remove spaces and dashes
    digits = card_number.replace(' ', '').replace('-', '')
    if len(digits) < 4:
        return False
    first_four = int(digits[:4])
    # Check old range (51-55)
    if len(digits) == 16 and 51 <= int(digits[:2]) <= 55:
        return True
    # Check new range (2221-2720)
    if 16 <= len(digits) <= 19 and 2221 <= first_four <= 2720:
        return True
    return False


def extract_first_page_info(pdf_path: str, debug: bool = False) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str], Optional[str]]:
    """
    Extract from first page:
    - Opening balance
    - Closing balance
    - Statement period (to determine year)
    - Credit card number (16 digits in 4 groups of 4)
    - Statement period end date (DD/MM/YYYY format)
    
    Also validates that this is a CBA Mastercard statement.
    
    Returns: (opening_balance, closing_balance, period_string, card_number, period_end_date)
    Raises: ValueError if not a CBA Mastercard statement
    """
    if fitz is None:
        raise RuntimeError('PyMuPDF (fitz) not available; please install it in the venv')
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        return None, None, None, None, None, None
    
    first_page = doc[0]
    text = extract_text_from_page(first_page)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    # Don't close doc here - we'll close it after validation
    
    opening_balance = None
    closing_balance = None
    period_string = None
    card_number = None
    
    # Extract opening balance
    # Pattern 1: "Opening balance" on same line as amount
    for line in lines:
        m = re.search(r'(?i)opening\s+balance[:\s]+[\$]?\s*(-?)([\d,]+\.?\d*)', line)
        if m:
            try:
                has_minus = m.group(1) == '-'
                amount = float(m.group(2).replace(',', ''))
                # Flip the sign: positive debt becomes negative, negative credit becomes positive
                opening_balance = -amount if not has_minus else amount
                if debug:
                    print(f'Found opening balance: {amount} (raw, minus={has_minus}) -> {opening_balance} (flipped)', file=sys.stderr)
                break
            except ValueError:
                pass
    
    # Pattern 2: "Opening balance" on one line, amount on next line
    if opening_balance is None:
        for i, line in enumerate(lines):
            if re.search(r'(?i)opening\s+balance', line) and i + 1 < len(lines):
                next_line = lines[i + 1]
                # Handle formats like "-$0.03" or "$0.03" or "-0.03" or "0.03"
                m = re.search(r'(-?)\s*[\$]?\s*([\d,]+\.?\d*)', next_line)
                if m:
                    try:
                        has_minus = m.group(1) == '-'
                        amount = float(m.group(2).replace(',', ''))
                        # Flip the sign: positive debt becomes negative, negative credit becomes positive
                        opening_balance = -amount if not has_minus else amount
                        if debug:
                            print(f'Found opening balance: {amount} (raw, minus={has_minus}) -> {opening_balance} (flipped)', file=sys.stderr)
                        break
                    except ValueError:
                        pass
    
    # Extract closing balance
    # Pattern 1: "Closing balance" on same line as amount
    for line in lines:
        m = re.search(r'(?i)closing\s+balance[:\s]+[\$]?\s*(-?)([\d,]+\.?\d*)', line)
        if m:
            try:
                has_minus = m.group(1) == '-'
                amount = float(m.group(2).replace(',', ''))
                # Flip the sign: positive debt becomes negative, negative credit becomes positive
                closing_balance = -amount if not has_minus else amount
                if debug:
                    print(f'Found closing balance: {amount} (raw, minus={has_minus}) -> {closing_balance} (flipped)', file=sys.stderr)
                break
            except ValueError:
                pass
    
    # Pattern 2: "Closing balance" on one line, amount on next line
    if closing_balance is None:
        for i, line in enumerate(lines):
            if re.search(r'(?i)closing\s+balance', line) and i + 1 < len(lines):
                next_line = lines[i + 1]
                # Handle formats like "-$0.03" or "$0.03" or "-0.03" or "0.03"
                m = re.search(r'(-?)\s*[\$]?\s*([\d,]+\.?\d*)', next_line)
                if m:
                    try:
                        has_minus = m.group(1) == '-'
                        amount = float(m.group(2).replace(',', ''))
                        # Flip the sign: positive debt becomes negative, negative credit becomes positive
                        closing_balance = -amount if not has_minus else amount
                        if debug:
                            print(f'Found closing balance: {amount} (raw, minus={has_minus}) -> {closing_balance} (flipped)', file=sys.stderr)
                        break
                    except ValueError:
                        pass
    
    # Extract statement period and end date
    period_end_date = None
    for line in lines:
        # Look for patterns like "1 Dec 2023 - 31 Dec 2023" or "Dec 1, 2023 - Dec 31, 2023"
        m = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', line)
        if m:
            period_string = m.group(0)
            # Extract end date: "31 Dec 2023" -> "31/12/2023"
            end_date_str = m.group(2)
            end_date_match = re.match(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', end_date_str)
            if end_date_match:
                day = int(end_date_match.group(1))
                mon_str = end_date_match.group(2).lower()[:3]
                year = int(end_date_match.group(3))
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                    'jul': '07', 'aug': '08', 'sep': '09', 'sept': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }
                month = month_map.get(mon_str, '01')
                period_end_date = f"{day:02d}/{month}/{year}"
            if debug:
                print(f'Found period: {period_string}, end date: {period_end_date}', file=sys.stderr)
            break
        # Alternative format: "Dec 1, 2023 - Dec 31, 2023"
        m = re.search(r'([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\s*-\s*([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})', line)
        if m:
            period_string = m.group(0)
            # Extract end date: "Dec 31, 2023" -> "31/12/2023"
            end_date_str = m.group(2)
            end_date_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', end_date_str)
            if end_date_match:
                mon_str = end_date_match.group(1).lower()[:3]
                day = int(end_date_match.group(2))
                year = int(end_date_match.group(3))
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                    'jul': '07', 'aug': '08', 'sep': '09', 'sept': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }
                month = month_map.get(mon_str, '01')
                period_end_date = f"{day:02d}/{month}/{year}"
            if debug:
                print(f'Found period: {period_string}, end date: {period_end_date}', file=sys.stderr)
            break
    
    # Extract credit card number (16 digits in 4 groups of 4)
    # Pattern: 4 digits, space/dash, 4 digits, space/dash, 4 digits, space/dash, 4 digits
    card_re = re.compile(r'\b(\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4})\b')
    for line in lines:
        match = card_re.search(line)
        if match:
            card_number = match.group(1).replace(' ', ' ').replace('-', ' ')
            # Normalize to space-separated
            card_number = re.sub(r'[\s-]+', ' ', card_number).strip()
            if debug:
                print(f'Found card number: {card_number}', file=sys.stderr)
            break
    
    # Validate that this is a CBA Mastercard statement
    # Check 1: Look for Mastercard indicators in the text
    text_lower = ' '.join(lines).lower()
    is_mastercard = False
    mastercard_indicators = [
        'platinum awards credit card',
        'mastercard',
        'master card'
    ]
    for indicator in mastercard_indicators:
        if indicator in text_lower:
            is_mastercard = True
            if debug:
                print(f'Found Mastercard indicator: {indicator}', file=sys.stderr)
            break
    
    # Check 2: Validate card number is a Mastercard
    if card_number:
        if is_mastercard_number(card_number):
            is_mastercard = True
            if debug:
                print(f'Card number {card_number} is a Mastercard', file=sys.stderr)
        elif debug:
            print(f'Warning: Card number {card_number} does not match Mastercard format', file=sys.stderr)
    
    # Check 3: Look for CBA indicators
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
    
    # Close document before returning or raising errors
    # Use a try/except to handle cases where doc might already be closed
    try:
        doc.close()
    except (ValueError, AttributeError):
        pass  # Document may already be closed
    
    # Raise error if not a CBA Mastercard statement
    # If we have a valid Mastercard number, we're more lenient about CBA indicators
    # (the card number format is a strong indicator it's from CBA)
    if not is_mastercard:
        raise ValueError('This does not appear to be a CBA Mastercard statement. Could not find Mastercard indicators (e.g., "Platinum Awards Credit Card", "Mastercard") on the first page.')
    
    # Only require CBA indicator if we don't have a valid Mastercard number
    # (having a valid Mastercard number is a strong signal it's a CBA statement)
    if not is_cba and not (card_number and is_mastercard_number(card_number)):
        raise ValueError('This does not appear to be a CBA Mastercard statement. Could not find CBA indicators (e.g., "Commonwealth Bank", "CommBank") on the first page, and card number format could not be validated.')
    
    return opening_balance, closing_balance, period_string, card_number, period_end_date


def extract_year_from_period(period_string: str) -> Optional[int]:
    """Extract the starting year from the statement period."""
    if not period_string:
        return None
    
    # Try pattern like "1 Dec 2023 - 31 Dec 2023"
    m = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+(\d{4}))', period_string)
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            pass
    
    # Try pattern like "Dec 1, 2023 - Dec 31, 2023"
    m = re.search(r'[A-Za-z]{3}\s+\d{1,2},?\s+(\d{4})', period_string)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    
    return None


def parse_amount(amount_str: str) -> Tuple[Optional[float], bool]:
    """
    Parse amount string. Returns (amount, is_credit).
    Positive number = debit, negative number = credit (e.g., "7.60-")
    """
    if not amount_str:
        return None, False
    
    # Remove $ and commas
    cleaned = amount_str.replace('$', '').replace(',', '').strip()
    
    # Check if it ends with '-' (negative/credit)
    is_credit = cleaned.endswith('-')
    if is_credit:
        cleaned = cleaned.rstrip('-').strip()
    
    try:
        amount = float(cleaned)
        return abs(amount), is_credit
    except ValueError:
        return None, False


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


def parse_transactions(pdf_path: str, opening_balance: float, period_string: str, period_end_date: Optional[str], debug: bool = False) -> list:
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
    
    # Extract year from period
    year = extract_year_from_period(period_string)
    if year is None:
        year = 2023  # fallback
        if debug:
            print(f'Warning: Could not extract year from period, using {year}', file=sys.stderr)
    
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    # Find transactions starting on page 2
    transactions_started = False
    date_header_found = False
    rows = []
    current_year = year
    last_month = None
    running_balance = opening_balance
    
    # Date pattern: DD MMM (standalone, not part of a date range)
    date_pattern = re.compile(r'^(\d{1,2}\s+[A-Za-z]{3})\s*$')
    # Amount pattern: number with optional minus at end (e.g., "7.60-" or "100.00")
    amount_pattern = re.compile(r'^([\d,]+\.\d{2})\s*(-?)\s*$|^([\d,]+)\s*(-?)\s*$')
    
    current_transaction = None  # [date_str, transaction_parts, amount_str, is_credit]
    
    for page_idx in range(1, len(doc)):  # Start from page 2 (index 1)
        page = doc[page_idx]
        text = extract_text_from_page(page)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for "Transactions" keyword to start processing
            if not transactions_started:
                if 'transactions' in line.lower():
                    transactions_started = True
                    if debug:
                        print(f'Found "Transactions" keyword on page {page_idx + 1}', file=sys.stderr)
                i += 1
                continue
            
            # After "Transactions", look for "Date" header (may be on separate line from "Transaction details")
            if not date_header_found:
                if line.lower().strip() == 'date':
                    # Check if next line has "transaction" or "details"
                    if i + 1 < len(lines) and ('transaction' in lines[i+1].lower() or 'details' in lines[i+1].lower()):
                        date_header_found = True
                        if debug:
                            print(f'Found "Date" header on page {page_idx + 1}', file=sys.stderr)
                        # Skip the header lines (Date, Transaction details, Amount)
                        i += 3  # Skip Date, Transaction details, Amount lines
                        continue
                i += 1
                continue
            
            # Check if this line is a standalone date (DD MMM)
            date_match = date_pattern.match(line)
            if date_match:
                # If we have a previous transaction being built, finalize it
                if current_transaction and current_transaction[2]:  # Has amount
                    date_str, trans_parts, amt_str, is_cred = current_transaction
                    formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
                    if formatted_date:
                        # Update current_year and last_month
                        date_parts = formatted_date.split('/')
                        if len(date_parts) == 3:
                            current_year = int(date_parts[2])
                            last_month = int(date_parts[1])
                    
                    transaction = ' '.join(trans_parts).strip()
                    amount, _ = parse_amount(amt_str)
                    if amount is not None:
                        # Update running balance
                        # For credit cards with flipped balances: 
                        # - Credits (payments) reduce debt: balance += amount (makes less negative)
                        # - Debits (purchases) increase debt: balance -= amount (makes more negative)
                        if is_cred:
                            running_balance += amount  # Credit reduces debt
                        else:
                            running_balance -= amount  # Debit increases debt
                        
                        rows.append([formatted_date, transaction, amount, is_cred, running_balance])
                        
                        if debug:
                            print(f'Transaction: {formatted_date} | {transaction[:50]} | {amount} {"(credit)" if is_cred else "(debit)"} | Balance: {running_balance}', file=sys.stderr)
                
                # Start new transaction
                date_str = date_match.group(1)
                current_transaction = [date_str, [], None, False]
                i += 1
                continue
            
            # Check if this line is an amount (standalone amount line)
            amount_match = amount_pattern.match(line)
            if amount_match and current_transaction:
                # Get the matched amount
                amt_str = amount_match.group(1) or amount_match.group(3)
                has_minus = (amount_match.group(2) == '-' or amount_match.group(4) == '-') or line.rstrip().endswith('-')
                current_transaction[2] = amt_str
                current_transaction[3] = has_minus
                i += 1
                continue
            
            # Check if we should stop - look for "Interest charged on purchases"
            if 'interest charged on purchases' in line.lower():
                # Finalize any pending transaction before stopping
                if current_transaction and current_transaction[2]:  # Has amount
                    date_str, trans_parts, amt_str, is_cred = current_transaction
                    formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
                    if formatted_date:
                        transaction = ' '.join(trans_parts).strip()
                        amount, _ = parse_amount(amt_str)
                        if amount is not None:
                            # For credit cards: credits reduce debt, debits increase debt
                            if is_cred:
                                running_balance += amount  # Credit reduces debt
                            else:
                                running_balance -= amount  # Debit increases debt
                            rows.append([formatted_date, transaction, amount, is_cred, running_balance])
                    # Clear current_transaction so it's not finalized again
                    current_transaction = None
                
                # Extract amount from "Interest charged on purchases" line
                # Skip percentage rates (e.g., "Purchase Rate 20.240%p.a.") and find the actual interest amount
                # The amount is the final number AFTER skipping rate lines
                interest_purchases_amount = None
                number_pattern = re.compile(r'([\d,]+\.?\d*)')
                # Look ahead in next lines, skipping any that contain "Rate" or "%"
                # Find the first number on a line that doesn't contain rate/percentage info
                for j in range(i + 1, min(i + 15, len(lines))):
                    # Skip lines with percentage rates
                    if '%' in lines[j].lower() or ('rate' in lines[j].lower() and '%' in lines[j].lower()):
                        if debug:
                            print(f'Skipping rate line: {lines[j][:50]}', file=sys.stderr)
                        continue
                    # Look for numbers on this line
                    numbers = number_pattern.findall(lines[j])
                    if numbers:
                        # Take the last number found (the final number on the line)
                        last_number_str = numbers[-1]
                        try:
                            amount = float(last_number_str.replace(',', ''))
                            if amount >= 0:  # Allow 0.00
                                interest_purchases_amount = amount
                                if debug:
                                    print(f'Found interest on purchases amount on line {j+1}: {amount} (from: {lines[j][:50]})', file=sys.stderr)
                                break
                        except ValueError:
                            pass
                
                # Add "Interest charged on purchases" transaction
                if interest_purchases_amount is not None:
                    # Interest is a debit (increases debt)
                    running_balance -= interest_purchases_amount
                    # Use statement period end date
                    interest_date = period_end_date if period_end_date else (rows[-1][0] if rows else "01/01/2023")
                    rows.append([interest_date, "Interest charged on purchases", interest_purchases_amount, False, running_balance])
                    if debug:
                        print(f'Processed interest on purchases: {interest_purchases_amount} (debit) | Balance: {running_balance}', file=sys.stderr)
                
                # Now look for "Interest charged on cash advances"
                interest_cash_advances_amount = None
                number_pattern = re.compile(r'([\d,]+\.?\d*)')
                # Look ahead in remaining lines to find "Interest charged on cash advances"
                for j in range(i + 1, min(i + 20, len(lines))):
                    if 'interest charged on cash advances' in lines[j].lower():
                        # Now look ahead from this line, skipping rate lines, to find the amount
                        for k in range(j + 1, min(j + 15, len(lines))):
                            # Skip lines with percentage rates
                            if '%' in lines[k].lower() or ('rate' in lines[k].lower() and '%' in lines[k].lower()):
                                if debug:
                                    print(f'Skipping rate line for cash advances: {lines[k][:50]}', file=sys.stderr)
                                continue
                            # Look for numbers on this line
                            numbers = number_pattern.findall(lines[k])
                            if numbers:
                                # Take the last number found (the final number on the line)
                                last_number_str = numbers[-1]
                                try:
                                    amount = float(last_number_str.replace(',', ''))
                                    if amount >= 0:  # Allow 0.00
                                        interest_cash_advances_amount = amount
                                        if debug:
                                            print(f'Found interest on cash advances amount on line {k+1}: {amount} (from: {lines[k][:50]})', file=sys.stderr)
                                        break
                                except ValueError:
                                    pass
                        break
                
                # Add "Interest charged on cash advances" transaction
                if interest_cash_advances_amount is not None:
                    # Interest is a debit (increases debt)
                    running_balance -= interest_cash_advances_amount
                    # Use statement period end date
                    interest_date = period_end_date if period_end_date else (rows[-1][0] if rows else "01/01/2023")
                    rows.append([interest_date, "Interest charged on cash advances", interest_cash_advances_amount, False, running_balance])
                    if debug:
                        print(f'Processed interest on cash advances: {interest_cash_advances_amount} (debit) | Balance: {running_balance}', file=sys.stderr)
                
                if debug:
                    print(f'Stopping: found "Interest charged on purchases"', file=sys.stderr)
                # Break out of the while loop
                break
            
            # Otherwise, this is likely transaction description text
            if current_transaction and not amount_pattern.match(line) and not date_pattern.match(line):
                current_transaction[1].append(line)
            
            i += 1
        
        # Finalize any pending transaction at end of page
        if current_transaction and current_transaction[2]:  # Has amount
            date_str, trans_parts, amt_str, is_cred = current_transaction
            formatted_date = parse_date_dd_mmm(date_str, current_year, last_month, month_map)
            if formatted_date:
                transaction = ' '.join(trans_parts).strip()
                amount, _ = parse_amount(amt_str)
                if amount is not None:
                    # For credit cards: credits reduce debt, debits increase debt
                    if is_cred:
                        running_balance += amount  # Credit reduces debt
                    else:
                        running_balance -= amount  # Debit increases debt
                    rows.append([formatted_date, transaction, amount, is_cred, running_balance])
                    if debug:
                        print(f'Transaction: {formatted_date} | {transaction[:50]} | {amount} {"(credit)" if is_cred else "(debit)"} | Balance: {running_balance}', file=sys.stderr)
            current_transaction = None
    
    doc.close()
    return rows, running_balance


def write_tsv(rows: list, card_number: str, out):
    """Write rows to TSV file."""
    # Header
    out.write('Date\tCard Number\tTransaction\tAmount\tBalance\n')
    
    for row in rows:
        date, transaction, amount, is_credit, balance = row
        
        # Format amount: flip the sign - debits are negative, credits are positive
        if is_credit:
            amount_str = f"{amount:.2f}"  # Credit: positive
        else:
            amount_str = f"-{amount:.2f}"  # Debit: negative
        
        # Format balance
        balance_str = f"{balance:.2f}"
        
        out.write(f'{date}\t{card_number or ""}\t{transaction}\t{amount_str}\t{balance_str}\n')


def main():
    parser = argparse.ArgumentParser(description='Convert CBA Mastercard statement PDF to TSV')
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
    opening_balance, closing_balance, period_string, card_number, period_end_date = extract_first_page_info(args.pdf, args.debug)
    
    if opening_balance is None:
        print('Error: Could not find opening balance on first page', file=sys.stderr)
        sys.exit(1)
    
    if closing_balance is None:
        print('Error: Could not find closing balance on first page', file=sys.stderr)
        sys.exit(1)
    
    if not period_string:
        print('Warning: Could not find statement period on first page', file=sys.stderr)
    
    if not card_number:
        print('Warning: Could not find credit card number on first page', file=sys.stderr)
    
    # Parse transactions
    rows, final_balance = parse_transactions(args.pdf, opening_balance, period_string or '', period_end_date, args.debug)
    
    if args.debug:
        print(f'Parsed {len(rows)} transactions', file=sys.stderr)
        print(f'Final balance: {final_balance:.2f}, Expected: {closing_balance:.2f}', file=sys.stderr)
    
    # Validate balance
    if abs(final_balance - closing_balance) > 0.01:
        print(f'Warning: Running balance ({final_balance:.2f}) does not match closing balance ({closing_balance:.2f})', file=sys.stderr)
    
    # Write output
    output_path = args.out
    if not output_path:
        output_path = args.pdf.replace('.pdf', '.tsv')
    
    with open(output_path, 'w') as f:
        write_tsv(rows, card_number or '', f)
    
    if args.debug:
        print(f'Output written to: {output_path}', file=sys.stderr)


if __name__ == '__main__':
    main()

