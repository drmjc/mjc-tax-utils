import re
import importlib.util
from pathlib import Path

# load the script module directly (the `cba` package may not be importable during tests)
pkg_dir = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('statement2tsv', str(pkg_dir / 'statement2tsv.py'))
statement2tsv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statement2tsv)


def normalize_cell(s: str) -> str:
    if not s:
        return ''
    t = s.strip()
    # detect parentheses (negative) or DR/CR markers
    negative = False
    low = t.lower()
    if '(' in t and ')' in t:
        negative = True
    if ' dr' in low or low.endswith(' dr') or low.endswith('dr'):
        negative = True
    cleaned = re.sub(r'[^0-9\.,\-]', '', t)
    cleaned = cleaned.replace(',', '')
    if cleaned == '':
        return ''
    try:
        val = float(cleaned)
    except Exception:
        return cleaned
    if negative:
        val = -abs(val)
    return f"{val:.2f}"


def test_afterpay_amount_and_balance():
    pdf = 'cba/test/2020-12-31 - 06 2799 12930092 - Statement20201231.pdf'
    rows = statement2tsv.parse_using_blocks(pdf, debug=False)
    assert rows, 'block parser returned no rows'

    # normalize amounts similar to the main script
    norm = []
    for r in rows:
        d = normalize_cell(r[2])
        c = normalize_cell(r[3])
        b = normalize_cell(r[4])
        norm.append([r[0], r[1], d, c, b])

    found = False
    for r in norm:
        if 'AFTERPAY' in r[1].upper():
            # compute signed amount = credit - debit
            debit = float(r[2]) if r[2] else 0.0
            credit = float(r[3]) if r[3] else 0.0
            amount = credit - debit
            balance = r[4]
            assert round(amount, 2) == -104.99
            assert balance == '11884.29'
            found = True
            break
    assert found, 'AFTERPAY row not found in parsed rows'
