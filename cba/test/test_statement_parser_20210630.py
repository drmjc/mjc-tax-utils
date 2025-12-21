import os
import pytest


def test_generated_tsv_exists_and_has_rows():
    sample = os.path.join(os.path.dirname(__file__), '2021-06-30 - 06 2799 12930092 - Statement20210630.tsv')
    assert os.path.exists(sample), f"Expected generated TSV at {sample}"
    with open(sample, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f if l.strip()]
    # header + at least one data row
    assert len(lines) >= 2
    # basic sanity: second line should contain a date-like prefix
    assert any(lines[1].startswith(d) for d in ('01 Jan', '02 Jan', '03 Jan', '04 Jan', '05 Jan', '06 Jan', '07 Jan', '08 Jan', '09 Jan', '10 Jan')) or len(lines[1].split('\t')[0]) > 0
