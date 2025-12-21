
#!/usr/bin/env python3
# Extract data from AliExpress invoice PDFs into JSON format
#
# Installation:
#   pip install python-dotenv pymupdf requests
#
# API Key Setup:
#   1. Get a free API key from: https://exchangerate.host/
#   2. Create a .env file in the same folder as this script
#   3. Add the following line to .env:
#      API_KEY=your_api_key_here
#
# Usage:
#   python aliexpress2json.py /path/to/invoice.pdf [--debug]
#
#   Options:
#     --debug    Enable debug output showing raw PDF text and processing details
#
# Output:
#   - Prints JSON to stdout
#   - Saves JSON file with same name as PDF (e.g., invoice.pdf -> invoice.json)
#   - Caches exchange rates in exchange_rate_cache.json to avoid repeated API calls
#
# Features:
#   - Extracts all items from invoice
#   - Converts currencies (USD/CNY) to AUD using historical exchange rates
#   - Pro-rates delivery fees across items
#   - Validates that PDF is an AliExpress invoice
#
# Author:
#   Mark Cowley, 2025-11-30

import os
import re
import sys
import fitz  # PyMuPDF
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
ACCESS_KEY = os.getenv("API_KEY")
if not ACCESS_KEY:
    raise ValueError("API_KEY not found. Please create a .env file with API_KEY=your_api_key_here")

# Debug flag
DEBUG = "--debug" in sys.argv

# Exchange rate scaling factor to adjust for real-world pricing differences
# Based on comparison with actual AliExpress charges
EXCHANGE_RATE_SCALE_FACTOR = 1.0165  # ~1.65% increase

# Script directory
SCRIPT_DIR = os.path.dirname(__file__)

# Exchange rate cache file (stored next to this script)
CACHE_FILE = os.path.join(SCRIPT_DIR, "exchange_rate_cache.json")

# Load existing cache if available
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r") as f:
            exchange_rate_cache = json.load(f)
    except Exception:
        exchange_rate_cache = {}
else:
    exchange_rate_cache = {}

def log_debug(message):
    if DEBUG:
        print(f"[DEBUG] {message}")

def get_exchange_rate(date_str, currency, return_date=False):
    """Fetch historical exchange rate to AUD for given currency and date, with caching."""
    if not currency or currency == "AUD":
        return 1.0
    
    # Normalize date string
    try:
        # Expecting YYYY-MM-DD
        date_obj = datetime.strptime(date_str, "%Y-%m-%d") if date_str else None
    except Exception:
        date_obj = None

    # Check cache first for exact date
    cache_key = f"{date_str}_{currency}"
    if cache_key in exchange_rate_cache:
        cached_rate = exchange_rate_cache[cache_key]
        log_debug(f"Exchange rate for {currency} on {date_str}: {cached_rate} (from cache)")
        return (cached_rate, date_str) if return_date else cached_rate

    # If no exact cached rate, look for a nearby cached rate for the currency
    nearest_cached_rate = None
    nearest_cached_date = None
    if date_obj:
        best_diff = None
        for key, value in exchange_rate_cache.items():
            if not key.endswith(f"_{currency}"):
                continue
            # key format: YYYY-MM-DD_CURRENCY
            try:
                k_date_str = key.split("_")[0]
                k_date = datetime.strptime(k_date_str, "%Y-%m-%d")
                diff = abs((k_date - date_obj).days)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    nearest_cached_rate = value
                    nearest_cached_date = k_date_str
            except Exception:
                continue
        if nearest_cached_rate is not None:
            log_debug(f"No exact exchange rate cached for {currency} on {date_str}; using nearest cached {nearest_cached_date} rate {nearest_cached_rate}")
            return (nearest_cached_rate, nearest_cached_date) if return_date else nearest_cached_rate
    
    # Use exchangerate.host convert API with access key
    # Convert 1 unit to get the exchange rate
    url = f"https://api.exchangerate.host/convert?from={currency}&to=AUD&date={date_str}&amount=1&access_key={ACCESS_KEY}"
    # Try API call for the exact date first
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("success", False):
                # The result is the converted amount (1 unit * rate = rate)
                rate = data.get("result", 1.0)
                # Apply scaling factor to adjust for real-world pricing
                rate = rate * EXCHANGE_RATE_SCALE_FACTOR
                # Cache the result
                exchange_rate_cache[cache_key] = rate
                log_debug(f"Exchange rate for {currency} on {date_str}: {rate} (scaled by {EXCHANGE_RATE_SCALE_FACTOR}, cached)")
                return (rate, date_str) if return_date else rate
            else:
                log_debug(f"Exchange rate API returned success=false: {data}")
    except Exception as e:
        log_debug(f"Exchange rate fetch failed: {e}")
    
    # If the API failed for the exact date, try surrounding dates (up to 7 days) to find a usable rate
    if date_obj:
        for offset in range(1, 8):
            for sign in (1, -1):
                try_date = (date_obj + timedelta(days=sign * offset)).strftime("%Y-%m-%d")
                try_key = f"{try_date}_{currency}"
                # First use any cached nearby date
                if try_key in exchange_rate_cache:
                    cached_rate = exchange_rate_cache[try_key]
                    log_debug(f"Using cached rate for {currency} on {try_date} (nearest to requested {date_str}): {cached_rate}")
                    return (cached_rate, try_date) if return_date else cached_rate
                # Otherwise try API for that date
                url2 = f"https://api.exchangerate.host/convert?from={currency}&to=AUD&date={try_date}&amount=1&access_key={ACCESS_KEY}"
                try:
                    resp2 = requests.get(url2)
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        if data2.get("success", False):
                            rate2 = data2.get("result", 1.0) * EXCHANGE_RATE_SCALE_FACTOR
                            exchange_rate_cache[try_key] = rate2
                            log_debug(f"Exchange rate for {currency} on {try_date}: {rate2} (from API fallback, cached)")
                            return (rate2, try_date) if return_date else rate2
                except Exception as e:
                    log_debug(f"Exchange rate fetch failed for fallback date {try_date}: {e}")

    # Try to use any existing cached rate for this currency (most recent)
    last_cached_rate = None
    last_cached_date = None
    for key, value in exchange_rate_cache.items():
        if not key.endswith(f"_{currency}"):
            continue
        k_date_str = key.split("_")[0]
        if last_cached_date is None or k_date_str > last_cached_date:
            last_cached_date = k_date_str
            last_cached_rate = value
    if last_cached_rate is not None:
        log_debug(f"Using most recent cached rate for {currency} (date {last_cached_date}): {last_cached_rate}")
        return (last_cached_rate, last_cached_date) if return_date else last_cached_rate

    # As a final resort, fallback to 1.0 and log a warning
    log_debug(f"Using fallback exchange rate of 1.0 for {currency}")
    return (1.0, None) if return_date else 1.0

def clean_description(lines):
    """Combine lines into a single description, allowing alphanumeric, unicode, and common punctuation."""
    description_parts = []
    for line in lines:
        # Allow letters, digits, unicode characters, and common punctuation including parentheses and quotes
        if re.match(r"^[\w\s,.&'/()\[\]\"-]+$", line.strip(), re.UNICODE):
            description_parts.append(line.strip())
        else:
            break
    return " ".join(description_parts)

def extract_delivery_fee(lines, invoice_date, default_currency):
    """Extract delivery fee from invoice lines."""
    delivery_fee = None
    delivery_currency = None
    
    for i, line in enumerate(lines):
        if "delivery charge" in line.lower() or "delivery fee" in line.lower() or "shipping" in line.lower():
            # Pattern: Delivery Charge -> price exclusive -> GST rate -> GST amount -> price inclusive
            # Price inclusive is 4 lines after "Delivery Charge"
            if i + 4 < len(lines):
                try:
                    # Verify GST rate line has %
                    if "%" in lines[i + 2]:
                        fee = float(lines[i + 4])
                        delivery_fee = fee
                        delivery_currency = default_currency  # Use currency from items
                        log_debug(f"Found delivery fee: {fee} {delivery_currency}")
                except (ValueError, IndexError):
                    pass
            break
    
    return delivery_fee, delivery_currency

def extract_invoice_data(pdf_path):
    """Extract invoice data and return as JSON array."""
    with fitz.open(pdf_path) as doc:
        text = "".join(page.get_text() for page in doc)

    # Validate that this is an AliExpress invoice
    if "alibaba.com" not in text.lower():
        raise ValueError(f"Error: This does not appear to be an AliExpress invoice. Expected 'Alibaba.com' in the PDF but not found. File: {pdf_path}")

    if DEBUG:
        print("[DEBUG] Raw text preview:")
        print(text.replace("\n", "\\n")[:1000])  # Show first 1000 chars with newline markers

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Invoice date
    date_match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", text)
    invoice_date = date_match.group(0).replace("/", "-") if date_match else None

    # Supplier name
    supplier_name = "Unknown Supplier"
    for i, line in enumerate(lines):
        if line.lower().startswith("supplier name"):
            if i + 1 < len(lines):
                supplier_name = lines[i + 1].strip()
            break

    # Invoice number from filename (format: "YYYY-MM-DD AliExpress INVOICE_NUMBER.pdf")
    filename = os.path.basename(pdf_path).replace(".pdf", "")
    filename_parts = filename.split()
    # Look for a long numeric string (invoice number) in the filename
    invoice_number = None
    for part in filename_parts:
        # Invoice numbers are typically long numeric strings
        if part.isdigit() and len(part) > 10:
            invoice_number = part
            break
    # Fallback to first part if no invoice number found
    if not invoice_number:
        invoice_number = filename_parts[0] if filename_parts else "Unknown"

    # Extract items first to get currency, then extract delivery fee
    # (We'll extract items twice - once to get currency, then properly with delivery fee)
    # Actually, let's extract currency from headers first
    currency = None
    for i, line in enumerate(lines):
        if "transaction" in line.lower():
            j = i + 1
            while j < len(lines):
                if "price inclusive of gst" in lines[j].lower():
                    k = j + 1
                    while k < len(lines) and re.match(r"^\([A-Z]{3}\)$", lines[k].strip()):
                        currency_match = re.match(r"^\(([A-Z]{3})\)$", lines[k].strip())
                        if currency_match:
                            currency = currency_match.group(1)
                        k += 1
                    break
                j += 1
            break

    # Extract delivery fee (needs currency)
    delivery_fee, delivery_currency = extract_delivery_fee(lines, invoice_date, currency)

    # Extract items
    # Find where items start (after "Transaction" and headers)
    items_start_idx = -1
    currency = None
    
    for i, line in enumerate(lines):
        if "transaction" in line.lower():
            # Look for the pattern: Price inclusive of GST header, then currency headers, then items
            j = i + 1
            while j < len(lines):
                if "price inclusive of gst" in lines[j].lower():
                    # Find currency from header lines (lines with just currency in parentheses)
                    k = j + 1
                    while k < len(lines) and re.match(r"^\([A-Z]{3}\)$", lines[k].strip()):
                        currency_match = re.match(r"^\(([A-Z]{3})\)$", lines[k].strip())
                        if currency_match:
                            currency = currency_match.group(1)
                        k += 1
                    items_start_idx = k
                    break
                j += 1
            break
    
    rows = []
    # Track exchange rates used during parsing (key: date_currency, value: rate)
    used_exchange_rates = {}
    if items_start_idx > 0 and currency:
        i = items_start_idx
        while i < len(lines):
            # Stop at "Total amount" line
            if "total amount" in lines[i].lower():
                break
            
            # Skip currency-only lines
            if re.match(r"^\([A-Z]{3}\)$", lines[i].strip()):
                i += 1
                continue
            
            # Collect description lines (English-like text, not numbers or percentages)
            desc_lines = []
            j = i
            while j < len(lines):
                line_stripped = lines[j].strip()
                # Stop if we hit a number (quantity or price)
                try:
                    float(line_stripped)
                    break
                except ValueError:
                    pass
                # Stop if it's a percentage
                if "%" in line_stripped:
                    break
                # Stop if it's "Total amount"
                if "total amount" in line_stripped.lower():
                    break
                # Include if it looks like description text
                if re.match(r"^[\w\s,.&'/()\[\]\"-]+$", line_stripped, re.UNICODE):
                    desc_lines.append(line_stripped)
                else:
                    break
                j += 1
            
            if not desc_lines:
                i += 1
                continue
            
            description = clean_description(desc_lines)
            
            # After description, pattern is: quantity, price exclusive, GST rate, GST amount, price inclusive
            # j is the index where we stopped (quantity line, first number after description)
            # We want the price inclusive (4 values after quantity)
            if j < len(lines):
                try:
                    # j = quantity
                    try:
                        quantity = int(lines[j])
                    except ValueError:
                        quantity = 1  # Default to 1 if parsing fails

                    # j+1 = price exclusive
                    # j+2 = GST rate (has %)
                    # j+3 = GST amount
                    # j+4 = price inclusive (this is what we want)
                    if j + 4 < len(lines):
                        # Verify GST rate line has %
                        if "%" in lines[j + 2]:
                            price = float(lines[j + 4])
                            rate, rate_date = get_exchange_rate(invoice_date, currency, return_date=True)
                            if not rate_date:
                                rate_date = invoice_date
                            used_exchange_rates[f"{rate_date}_{currency}"] = rate
                            price_aud = round(price * rate, 2)
                            log_debug(f"Item parsed: desc='{description}' qty={quantity} price={price} {currency} -> {price_aud} AUD using rate={rate}")
                            
                            rows.append({
                                "Invoice Date": invoice_date,
                                "Invoice Number": invoice_number,
                                "Shop": "AliExpress",
                                "Branch": supplier_name,
                                "Description": description,
                                "Quantity": quantity,
                                "Original Currency": currency,
                                "Item Cost": price,
                                "Item Cost (AUD)": price_aud
                            })
                            
                            # Move to next item (skip quantity + 4 price fields, j already points to quantity)
                            i = j + 5
                        else:
                            i += 1
                    else:
                        i += 1
                except (ValueError, IndexError):
                    i += 1
            else:
                i += 1
    # NOTE: Removed fallback parsing method (duplicate logic). If invoice parsing using the
    # main 'items_start_idx' detection fails, the invoice format likely doesn't match the
    # expected structure. Consider adding more robust parsing or explicit patterns for
    # edge-case invoices rather than maintaining two near-duplicate parsing branches.

    # Pro-rate delivery fee across items
    if delivery_fee and delivery_currency and rows:
        delivery_rate, delivery_rate_date = get_exchange_rate(invoice_date, delivery_currency, return_date=True)
        if not delivery_rate_date:
            delivery_rate_date = invoice_date
        used_exchange_rates[f"{delivery_rate_date}_{delivery_currency}"] = delivery_rate
        delivery_fee_aud = round(delivery_fee * delivery_rate, 2)
        num_items = len(rows)
        prorated_delivery_aud = delivery_fee_aud / num_items
        
        log_debug(f"Pro-rating delivery fee: {delivery_fee_aud} AUD across {num_items} items = {prorated_delivery_aud:.4f} AUD per item")
        
        # Add prorated delivery fee to each item, handling rounding to ensure total matches
        total_added = 0.0
        prorated_delivery_original = delivery_fee / num_items
        
        for idx, row in enumerate(rows):
            # Store original cost before adding delivery fee
            original_cost_aud = row["Item Cost (AUD)"]
            
            if idx == len(rows) - 1:
                # Last item gets any remainder to ensure exact total
                amount_to_add_aud = round(delivery_fee_aud - total_added, 2)
                prorated_delivery_original_item = round(delivery_fee - (prorated_delivery_original * (num_items - 1)), 2)
            else:
                amount_to_add_aud = round(prorated_delivery_aud, 2)
                prorated_delivery_original_item = round(prorated_delivery_original, 2)
            
            # Add prorated delivery fee in original currency and AUD
            row["Prorated Delivery Fee"] = prorated_delivery_original_item
            row["Prorated Delivery Fee (AUD)"] = amount_to_add_aud
            
            # Calculate total item cost including delivery
            total_item_cost_aud = round(original_cost_aud + amount_to_add_aud, 2)
            row["Total Item Cost (AUD)"] = total_item_cost_aud
            
            # Keep Item Cost (AUD) as base cost (before delivery)
            total_added += amount_to_add_aud
    else:
        # No delivery fee - add consistent fields with zero values
        for row in rows:
            row["Prorated Delivery Fee"] = 0.0
            row["Prorated Delivery Fee (AUD)"] = 0.0
            row["Total Item Cost (AUD)"] = row["Item Cost (AUD)"]

    if DEBUG and not rows:
        print("[DEBUG] No items found. Check invoice structure.")

    # Consolidate AUD values - use Total Item Cost (always present now)
    total_aud = round(sum(row["Total Item Cost (AUD)"] for row in rows), 2)
    
    result = {
        "items": rows,
        "total_aud": total_aud
    }
    
    # Add delivery fee summary if present
    if delivery_fee and delivery_currency:
        delivery_rate, delivery_rate_date = get_exchange_rate(invoice_date, delivery_currency, return_date=True)
        if not delivery_rate_date:
            delivery_rate_date = invoice_date
        used_exchange_rates[f"{delivery_rate_date}_{delivery_currency}"] = delivery_rate
        delivery_fee_aud = round(delivery_fee * delivery_rate, 2)
        result["delivery_fee"] = {
            "amount": delivery_fee,
            "currency": delivery_currency,
            "amount_aud": delivery_fee_aud,
            "prorated_across_items": len(rows)
        }
    # Add a summary of exchange rates used (always include, even if empty)
    result["exchange_rates"] = used_exchange_rates
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aliexpress2json.py /path/to/invoice.pdf [--debug]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    data = extract_invoice_data(pdf_path)
    json_output = json.dumps(data, indent=2)

    # Print to stdout
    print(json_output)

    # Print a summary of exchange rates used
    if 'exchange_rates' in data:
        print("\nExchange rates used:")
        for key, rate in data['exchange_rates'].items():
            try:
                date_str, currency_str = key.split("_")
            except ValueError:
                date_str = key
                currency_str = "?"
            print(f"  {currency_str} on {date_str}: {rate:.3f}")

    # Save to file
    json_file = os.path.splitext(pdf_path)[0] + ".json"
    with open(json_file, "w", encoding="utf-8") as f:
        f.write(json_output)

    print(f"JSON saved to {json_file}")
    
    # Save exchange rate cache
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(exchange_rate_cache, f, indent=2)
    except Exception as e:
        log_debug(f"Failed to save exchange rate cache: {e}")
