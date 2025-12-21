import os
import sys
import pytest

# Add repo path for imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from statement2tsv import parse_statement_lines


def load_sample_lines():
    # load the generated TSV and reconstruct minimal lines to feed the line parser
    sample_txt = os.path.join(os.path.dirname(__file__), '2020-12-31 - 06 2799 12930092 - Statement20201231.tsv')
    if not os.path.exists(sample_txt):
        pytest.skip('Sample TSV not present in test folder')
    with open(sample_txt, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    # return some fake flattened lines that mimic PDF-extracted lines (Date at start)
    # Use the TSV rows (skip header) and produce simple lines: "Date Transaction Debit Credit Balance"
    out = []
    for ln in lines[1:]:
        parts = ln.split('\t')
        # handle either old 5-column TSV (Date,Transaction,Debit,Credit,Balance)
        # or new 4-column TSV (Date,Transaction,Amount,Balance)
        if len(parts) == 5:
            date, tx, d, c, b = parts
        elif len(parts) == 4:
            date, tx, amt, b = parts
            # convert single signed amount into debit/credit placement for the parser
            if amt.startswith('-'):
                d = amt.lstrip('-')
                c = ''
            else:
                d = ''
                c = amt
        else:
            # unexpected format; skip
            continue
        # build a single-line representation similar to PDF raw: date + " " + transaction + "    " + amounts
        row = f"{date} {tx}    {d} {c} {b}".strip()
        out.append(row)
    return out


def test_09_dec_row_present():
    # Read the generated TSV and assert it contains a 09 Dec Direct Credit row
    sample_txt = os.path.join(os.path.dirname(__file__), '2020-12-31 - 06 2799 12930092 - Statement20201231.tsv')
    if not os.path.exists(sample_txt):
        pytest.skip('Sample TSV not present in test folder')
    with open(sample_txt, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    # skip header
    data = lines[1:]
    found = []
    for ln in data:
        parts = ln.split('\t')
        if not parts:
            continue
        # detect date and transaction across any tab-separated field (some rows put the
        # transaction in the same first field as the date)
        any_date = any(p.startswith('09 Dec') or p.startswith('09/12') for p in parts)
        any_tx = any(('Direct Credit' in p) or ('Direct credit' in p) for p in parts)
        if any_date and any_tx:
            found.append((parts, ln))
    assert found, 'Expected a 09 Dec Direct Credit row in generated TSV'
