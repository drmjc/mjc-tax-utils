# Rename AliExpress invoices.
Example Renamed: 8158599067129326_payment.pdf -> 2022-11-28 AliExpress 8158599067129326.pdf
author: Mark Cowley, 2025-11-30

cd /path/to/AliExpress_invoices
python3 -m venv path/to/venv\nsource path/to/venv/bin/activate
pip install pymupdf
python rename_AliExpress_invoices.py
less rename_log.txt
