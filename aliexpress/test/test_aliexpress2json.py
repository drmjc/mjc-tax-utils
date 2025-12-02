import os
from aliexpress.aliexpress2json import extract_invoice_data, get_exchange_rate

TEST_DIR = os.path.dirname(__file__)


def test_multi_item_invoice_aud_conversion():
    TEST_PDF = os.path.join(TEST_DIR, '2025-11-08 AliExpress 8205891762989326.pdf')
    data = extract_invoice_data(TEST_PDF)
    items = data['items']
    assert len(items) == 2, "Expected 2 items in the test PDF"

    # Expected AUD values based on existing cache (0.2200000785 rate as saved)
    assert items[0]['Item Cost (AUD)'] == 4.94
    assert items[1]['Item Cost (AUD)'] == 15.17
    assert round(data['total_aud'], 2) == 20.11
    assert 'exchange_rates' in data


def test_all_items_have_exchange_applied():
    # Iterate all PDF invoices in the test directory and ensure item AUD values are correctly calculated
    for fname in os.listdir(TEST_DIR):
        if not fname.endswith('.pdf'):
            continue
        pdf_path = os.path.join(TEST_DIR, fname)
        data = extract_invoice_data(pdf_path)
        for item in data['items']:
            currency = item.get('Original Currency')
            if not currency or currency == 'AUD':
                # Nothing to convert
                continue
            # Compute expected AUD from our get_exchange_rate function using same invoice date
            rate = get_exchange_rate(item.get('Invoice Date'), currency)
            expected = round(item['Item Cost'] * rate, 2)
            assert item['Item Cost (AUD)'] == expected, f"Item not converted correctly: {fname} {item['Description']} expected {expected} got {item['Item Cost (AUD)']}"
        assert 'exchange_rates' in data


def test_usd_multi_item_invoice_conversion(tmp_path):
    """Create a USD multi-item invoice PDF and verify AUD conversions using a seeded exchange rate."""
    import fitz
    import aliexpress.aliexpress2json as module

    # Seed exchange rate (avoid network calls)
    invoice_date = "2025-10-10"
    usd_rate = 1.5
    module.exchange_rate_cache[f"{invoice_date}_USD"] = usd_rate

    # Compose a minimal invoice text matching parser expectations
    text = "\n".join([
        "NOTICE",
        "Supplier name",
        "Supplier USD Store",
        "Platform name",
        "Alibaba.com Singapore E-Commerce Private",
        "Limited",
        "Date of issue",
        invoice_date.replace('-', '/'),
        "Transaction",
        "Quantity",
        "Price exclusive of GST",
        "GST Rate",
        "GST Amount",
        "Price inclusive of GST",
        "(USD)",
        "(USD)",
        "(USD)",
        "Widget A",
        "1",
        "10.00",
        "10.0 %",
        "1.00",
        "11.00",
        "Widget B",
        "1",
        "20.00",
        "10.0 %",
        "2.00",
        "22.00",
        "Total amount inclusive of GST in USD",
        "33.00",
    ])

    pdf_path = tmp_path / "usd_multi_item_invoice.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(pdf_path))
    doc.close()

    # Run parser
    result = module.extract_invoice_data(str(pdf_path))
    items = result["items"]
    assert len(items) == 2

    # Expected values: price inclusive (USD) * seeded USD rate
    expected_aud_0 = round(11.00 * usd_rate, 2)
    expected_aud_1 = round(22.00 * usd_rate, 2)

    assert items[0]["Item Cost (AUD)"] == expected_aud_0, f"Item 0 AUD mismatch expected {expected_aud_0} got {items[0]['Item Cost (AUD)']}"
    assert items[1]["Item Cost (AUD)"] == expected_aud_1, f"Item 1 AUD mismatch expected {expected_aud_1} got {items[1]['Item Cost (AUD)']}"
    assert 'exchange_rates' in result


def test_cny_invoice_with_cached_rate(tmp_path):
    """Ensure 2025-08-29 invoice is converted correctly when cache seeded with expected rate."""
    import aliexpress.aliexpress2json as module
    TEST_PDF = os.path.join(os.path.dirname(__file__), '2025-08-29 AliExpress 8203831366279326.pdf')

    # Seed the cache for this invoice date/currency (mimic real cached value)
    module.exchange_rate_cache['2025-08-29_CNY'] = 0.22

    data = module.extract_invoice_data(TEST_PDF)
    items = data['items']
    assert len(items) == 1
    # Item price inclusive is 113.96 CNY in the PDF for the item
    expected = round(113.96 * 0.22, 2)
    assert items[0]['Item Cost (AUD)'] == expected, f"Expected {expected} AUD got {items[0]['Item Cost (AUD)']}"
    assert 'exchange_rates' in data


def test_cny_invoice_nearest_cached_rate(tmp_path):
    """If no exact date cached, nearest cached rate should be used for conversion."""
    import aliexpress.aliexpress2json as module
    TEST_PDF = os.path.join(os.path.dirname(__file__), '2025-08-29 AliExpress 8203831366279326.pdf')

    # Ensure exact date entry is removed
    if '2025-08-29_CNY' in module.exchange_rate_cache:
        del module.exchange_rate_cache['2025-08-29_CNY']

    # Seed a different date for the same currency
    module.exchange_rate_cache['2025-11-08_CNY'] = 0.2200000785

    data = module.extract_invoice_data(TEST_PDF)
    items = data['items']
    assert len(items) == 1
    expected = round(113.96 * module.exchange_rate_cache['2025-11-08_CNY'], 2)
    assert items[0]['Item Cost (AUD)'] == expected, f"Expected {expected} AUD got {items[0]['Item Cost (AUD)']}"
    assert 'exchange_rates' in data


def test_description_with_parentheses_and_unicode(tmp_path):
    """Ensure descriptions with parentheses and Unicode characters are parsed correctly."""
    import fitz
    import aliexpress.aliexpress2json as module

    # Seed exchange rate
    invoice_date = "2024-07-01"
    cny_rate = 0.22
    module.exchange_rate_cache[f"{invoice_date}_CNY"] = cny_rate

    # Create a PDF with description containing parentheses and superscript
    text = "\n".join([
        "NOTICE",
        "Supplier name",
        "Test Store",
        "Platform name",
        "Alibaba.com Singapore E-Commerce Private",
        "Limited",
        "Date of issue",
        invoice_date.replace('-', '/'),
        "Transaction",
        "Quantity",
        "Price exclusive of GST",
        "GST Rate",
        "GST Amount",
        "Price inclusive of GST",
        "(CNY)",
        "(CNY)",
        "(CNY)",
        "Ferrule Sleeves Terminal Crimping Tools",
        "6-4/6-6(0.25-10mm²/0.25-6mm²) Clamp",
        "1",
        "136.14",
        "10.0 %",
        "13.61",
        "149.75",
        "Total amount inclusive of GST in CNY",
        "13.61",
        "149.75",
    ])

    pdf_path = tmp_path / "test_parens_unicode.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(pdf_path))
    doc.close()

    # Parse and verify
    result = module.extract_invoice_data(str(pdf_path))
    items = result["items"]
    assert len(items) == 1, f"Expected 1 item, got {len(items)}"
    
    # Verify description includes both lines with parentheses
    desc = items[0]["Description"]
    assert "Ferrule Sleeves" in desc
    assert "0.25-10mm²" in desc or "0.25-10mm" in desc  # Superscript might be normalized
    
    # Verify conversion
    expected_aud = round(149.75 * cny_rate, 2)
    assert items[0]["Item Cost (AUD)"] == expected_aud


def test_description_with_inches_notation(tmp_path):
    """Ensure descriptions with inches notation (double quotes) are parsed correctly."""
    import fitz
    import aliexpress.aliexpress2json as module

    # Seed exchange rate
    invoice_date = "2024-07-01"
    usd_rate = 1.55
    module.exchange_rate_cache[f"{invoice_date}_USD"] = usd_rate

    # Create a PDF with description containing inches notation
    text = "\n".join([
        "NOTICE",
        "Supplier name",
        "STONEGO Tools Store",
        "Platform name",
        "Alibaba.com Singapore E-Commerce Private",
        "Limited",
        "Date of issue",
        invoice_date.replace('-', '/'),
        "Transaction",
        "Quantity",
        "Price exclusive of GST",
        "GST Rate",
        "GST Amount",
        "Price inclusive of GST",
        "(USD)",
        "(USD)",
        "(USD)",
        "STONEGO 180Pcs/Box Rubber Grommet Kit",
        "1/4\", 5/16\", 3/8\", 1/2\", 5/8\", 7/8\", 1\"",
        "1",
        "5.45",
        "10.0 %",
        "0.55",
        "6.00",
        "Total amount inclusive of GST in USD",
        "0.55",
        "6.00",
    ])

    pdf_path = tmp_path / "test_inches.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(pdf_path))
    doc.close()

    # Parse and verify
    result = module.extract_invoice_data(str(pdf_path))
    items = result["items"]
    assert len(items) == 1, f"Expected 1 item, got {len(items)}"
    
    # Verify description includes inches notation
    desc = items[0]["Description"]
    assert "STONEGO" in desc
    assert '1/4"' in desc or "1/4" in desc  # Inches notation
    
    # Verify conversion
    expected_aud = round(6.0 * usd_rate, 2)
    assert items[0]["Item Cost (AUD)"] == expected_aud
