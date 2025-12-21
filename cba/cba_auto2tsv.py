#!/usr/bin/env python3
"""
Automatically detect CBA statement type and route to the appropriate parser.

Supported statement types:
- Mastercard (credit card statements)
- Home Loan
- Youth Saver
- Everyday Offset
- Smart Access
- NetBank Saver

Usage:
    python3 cba/cba_auto2tsv.py input.pdf [--out output.tsv] [--debug]
"""
import sys
import subprocess
import argparse
import os

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


def detect_statement_type(pdf_path: str, debug: bool = False) -> str:
    """
    Detect the type of CBA statement by examining the first page.
    
    Returns one of: 'mastercard', 'homeloan', 'youthsaver', 'offset', 'smartaccess', 'unknown'
    """
    if fitz is None:
        if debug:
            print('Warning: PyMuPDF not available, cannot auto-detect statement type', file=sys.stderr)
        return 'unknown'
    
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        doc.close()
        return 'unknown'
    
    # Check first few pages for statement type indicators
    # Skip notice letter pages
    def is_notice_letter_page(page_text: str) -> bool:
        text_lower = page_text.lower()
        has_notice_title = 'notice of increase to repayments for your home loan' in text_lower
        has_signature = 'yours sincerely' in text_lower and 'the commbank team' in text_lower
        return has_notice_title or has_signature
    
    for p_i in range(min(3, len(doc))):  # Check first 3 pages
        page = doc[p_i]
        text = extract_text_from_page(page)
        text_lower = text.lower()
        
        # Skip notice letters
        if is_notice_letter_page(text):
            if debug:
                print(f'Skipping page {p_i+1}: notice letter page', file=sys.stderr)
            continue
        
        # Check for account-specific keywords FIRST (these are more reliable than generic Mastercard detection)
        # Check for Home Loan
        if 'home loan summary' in text_lower:
            doc.close()
            if debug:
                print('Detected: Home Loan', file=sys.stderr)
            return 'homeloan'
        
        # Check for Youth Saver
        if 'youth saver' in text_lower or 'youthsaver' in text_lower:
            doc.close()
            if debug:
                print('Detected: Youth Saver', file=sys.stderr)
            return 'youthsaver'
        
        # Check for Everyday Offset
        if 'everyday offset' in text_lower:
            doc.close()
            if debug:
                print('Detected: Everyday Offset', file=sys.stderr)
            return 'offset'
        
        # Check for Smart Access
        if 'smart access' in text_lower:
            doc.close()
            if debug:
                print('Detected: Smart Access', file=sys.stderr)
            return 'smartaccess'
        
        # Check for NetBank Saver
        if 'netbank saver' in text_lower:
            doc.close()
            if debug:
                print('Detected: NetBank Saver', file=sys.stderr)
            return 'smartaccess'  # Use same parser as Smart Access
        
        # Check for Mastercard indicators LAST (after account-specific checks)
        # This prevents false positives when account numbers happen to match Mastercard patterns
        mastercard_indicators = [
            'platinum awards credit card',
            'mastercard',
            'master card'
        ]
        for indicator in mastercard_indicators:
            if indicator in text_lower:
                # Also check for Mastercard number pattern (51-55 or 2221-2720)
                import re
                card_number_pattern = re.compile(r'\b(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\b')
                matches = card_number_pattern.findall(text)
                for match in matches:
                    first_four = match[0]
                    first_two = int(first_four[:2])
                    first_four_digits = int(first_four)
                    # Mastercard ranges: 51-55 or 2221-2720
                    if 51 <= first_two <= 55 or (2221 <= first_four_digits <= 2720):
                        doc.close()
                        if debug:
                            print(f'Detected: Mastercard (indicator: {indicator}, card number: {" ".join(match)})', file=sys.stderr)
                        return 'mastercard'
                # If we found the indicator but no valid card number, still likely Mastercard
                doc.close()
                if debug:
                    print(f'Detected: Mastercard (indicator: {indicator})', file=sys.stderr)
                return 'mastercard'
    
    doc.close()
    if debug:
        print('Warning: Could not detect statement type', file=sys.stderr)
    return 'unknown'


def main():
    parser = argparse.ArgumentParser(description='Automatically detect and parse CBA statement PDF to TSV')
    parser.add_argument('pdf', help='Input PDF file')
    parser.add_argument('--out', help='Output TSV path (default: replace .pdf with .tsv)')
    parser.add_argument('--debug', action='store_true', help='Show debug info')
    parser.add_argument('--dry-run', action='store_true', help='Print PDF name and detected statement type, then exit')
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f'Error: File not found: {args.pdf}', file=sys.stderr)
        sys.exit(1)
    
    # Detect statement type
    stmt_type = detect_statement_type(args.pdf, args.debug)
    
    # If dry-run, just print and exit
    if args.dry_run:
        pdf_name = os.path.basename(args.pdf)
        print(f'{pdf_name}\t{stmt_type}')
        sys.exit(0)
    
    # Map statement types to scripts
    script_map = {
        'mastercard': 'cba_mastercard2tsv.py',
        'homeloan': 'cba_homeloan2tsv.py',
        'youthsaver': 'cba_youthsaver2tsv.py',
        'offset': 'cba_account2tsv.py',
        'smartaccess': 'cba_account2tsv.py',
    }
    
    if stmt_type == 'unknown':
        print('Error: Could not detect statement type. Please use the appropriate parser directly:', file=sys.stderr)
        print('  - cba_mastercard2tsv.py for Mastercard statements', file=sys.stderr)
        print('  - cba_homeloan2tsv.py for Home Loan statements', file=sys.stderr)
        print('  - cba_youthsaver2tsv.py for Youth Saver statements', file=sys.stderr)
        print('  - cba_account2tsv.py for Everyday Offset or Smart Access statements', file=sys.stderr)
        sys.exit(1)
    
    script_name = script_map[stmt_type]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    
    if not os.path.exists(script_path):
        print(f'Error: Parser script not found: {script_path}', file=sys.stderr)
        sys.exit(1)
    
    if args.debug:
        print(f'Routing to: {script_name}', file=sys.stderr)
    
    # Build command to run the appropriate script
    cmd = [sys.executable, script_path, args.pdf]
    if args.out:
        cmd.extend(['--out', args.out])
    if args.debug:
        cmd.append('--debug')
    
    # Run the script
    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        pdf_name = os.path.basename(args.pdf)
        print(f'Error: Parser script failed with exit code {e.returncode} while processing: {pdf_name}', file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        pdf_name = os.path.basename(args.pdf)
        print(f'Error: Failed to run parser script for {pdf_name}: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

