"""
Excel Parser MCP Component
Parses Santander Excel bank statements into normalized transaction format.
Supports true Excel files (.xls, .xlsx) and HTML files disguised as .xls
"""

import pandas as pd
from datetime import datetime
import re
from mcp.merchant_normalizer import normalize_merchant_name


def parse_santander_excel(file_path):
    """
    Parse Santander Excel format into normalized transactions.
    Auto-detects format: true Excel or HTML disguised as .xls

    Args:
        file_path: Path to the Excel file

    Returns:
        List of transaction dictionaries
    """
    try:
        # First, detect if this is actually an HTML file
        if is_html_file(file_path):
            # Use HTML parser
            from mcp.santander_html_parser import parse_santander_html
            return parse_santander_html(file_path)

        # Otherwise, parse as true Excel file
        return parse_true_excel(file_path)

    except Exception as e:
        raise Exception(f"Failed to parse Excel file: {str(e)}")


def is_html_file(file_path):
    """
    Check if file is actually HTML (common for Santander exports).

    Args:
        file_path: Path to file

    Returns:
        Boolean indicating if file is HTML
    """
    try:
        with open(file_path, 'rb') as f:
            # Read first 100 bytes
            header = f.read(100).decode('utf-8', errors='ignore').lower()
            return '<!doctype' in header or '<html' in header
    except:
        return False


def parse_true_excel(file_path):
    """
    Parse true Excel files (.xls with xlrd or .xlsx with openpyxl).

    Args:
        file_path: Path to the Excel file

    Returns:
        List of transaction dictionaries
    """
    try:
        # Determine file format and use appropriate engine
        file_path_str = str(file_path)
        if file_path_str.endswith('.xls'):
            # Use xlrd for older .xls files
            df = pd.read_excel(file_path, engine='xlrd')
        else:
            # Use openpyxl for newer .xlsx files
            df = pd.read_excel(file_path, engine='openpyxl')

        # Normalize column names (handle case variations)
        df.columns = df.columns.str.strip().str.title()

        # Verify required columns exist
        required_columns = ['Date', 'Description']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        transactions = []

        for idx, row in df.iterrows():
            # Skip rows with no description
            if pd.isna(row['Description']) or str(row['Description']).strip() == '':
                continue

            # Parse date
            try:
                if isinstance(row['Date'], str):
                    transaction_date = pd.to_datetime(row['Date'], dayfirst=True).strftime('%Y-%m-%d')
                else:
                    transaction_date = row['Date'].strftime('%Y-%m-%d')
            except Exception as e:
                print(f"Skipping row {idx}: Invalid date format - {e}")
                continue

            # Calculate amount (negative for expenses, positive for income)
            amount = 0.0

            # Check for Debit column (expenses - should be negative)
            if 'Debit' in df.columns and pd.notna(row['Debit']):
                debit_value = clean_currency_value(row['Debit'])
                if debit_value is not None:
                    amount = -abs(debit_value)  # Ensure negative

            # Check for Credit column (income - should be positive)
            if 'Credit' in df.columns and pd.notna(row['Credit']):
                credit_value = clean_currency_value(row['Credit'])
                if credit_value is not None:
                    amount = abs(credit_value)  # Ensure positive

            # If we have an Amount column instead
            if amount == 0.0 and 'Amount' in df.columns and pd.notna(row['Amount']):
                amount = clean_currency_value(row['Amount'])

            # Skip if amount is still 0
            if amount == 0.0:
                continue

            description = str(row['Description']).strip()

            merchant = extract_merchant(description)
            normalized_merchant = normalize_merchant_name(merchant, description)

            transactions.append({
                'date': transaction_date,
                'description': description,
                'amount': amount,
                'merchant': normalized_merchant,
                'source_file': file_path.split('/')[-1]
            })

        return transactions

    except Exception as e:
        raise Exception(f"Failed to parse Excel file: {str(e)}")


def clean_currency_value(value):
    """
    Clean UK currency format and convert to float.
    Handles: £1,234.56, 1234.56, £1234.56

    Args:
        value: Raw currency value (string or number)

    Returns:
        Float value or None if invalid
    """
    if pd.isna(value):
        return None

    # If already a number, return it
    if isinstance(value, (int, float)):
        return float(value)

    # Convert to string and clean
    value_str = str(value).strip()

    # Remove £ symbol, commas, and spaces
    cleaned = value_str.replace('£', '').replace(',', '').replace(' ', '')

    # Handle parentheses for negative numbers: (123.45) -> -123.45
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]

    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_card_payment_merchant(description):
    """
    Extract merchant name from card payment transactions.

    Pattern: "CARD PAYMENT TO {MERCHANT}{*{ref} OR -{ref}} ON {date}"
    Supports various formats with optional asterisk/dash and reference numbers.

    Special cases:
    - Uber *ONE -> "Uber One" (special service)
    - Uber *EATS -> "Uber" (ignore Eats suffix)
    - Zipcar Trip -> "Zipcar" (ignore trip details)
    - Bandcamp variations -> "Bandcamp"

    Examples:
        "CARD PAYMENT TO AIRBNB * HM4EFPXHB8 ON 30-09-2025" -> "AIRBNB"
        "CARD PAYMENT TO LIME*3 RIDES 7RUI ON 28-09-2025" -> "LIME"
        "CARD PAYMENT TO Microsoft-G113688814 ON 15-09-2025" -> "Microsoft"
        "CARD PAYMENT TO HSBC - Teya ON 15-01-2025" -> "HSBC - Teya"
        "CARD PAYMENT TO UBER *ONE ON 14-09-2025" -> "Uber One"
        "CARD PAYMENT TO UBER *EATS ON 12-09-2025" -> "Uber"
        "CARD PAYMENT TO Zipcar Trip SEP06 ON 06-09-2025" -> "Zipcar"
        "CARD PAYMENT TO BANDCAMPLESDISQUESBO ,9.60 EUR, RATE 0.8" -> "Bandcamp"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if card payment transaction, None otherwise
    """
    if not description or 'CARD PAYMENT TO' not in description.upper():
        return None

    # Match merchant name after "CARD PAYMENT TO"
    # Stop at: *, " ON ", comma, or end of string
    # Allow hyphens in merchant names (e.g., "HSBC - Teya")
    match = re.search(r'CARD PAYMENT TO\s+(.+?)(?:\s*\*|\s+ON\s+|,|\s*$)', description, re.IGNORECASE)

    if not match:
        return None

    merchant = match.group(1).strip()

    if not merchant:
        return None

    # Remove reference codes that appear after a hyphen with no space: -XXXXXX
    # Example: "Microsoft-G113688814" -> "Microsoft"
    # This preserves hyphens with spaces like "HSBC - Teya"
    merchant = re.sub(r'-[A-Z0-9]+$', '', merchant)

    # Special case: Bandcamp (contains "BANDCAMP" in merchant name)
    if 'BANDCAMP' in merchant.upper():
        return 'Bandcamp'

    # Special case: Zipcar (contains "ZIPCAR" and "TRIP" in description)
    if 'ZIPCAR' in merchant.upper() and 'TRIP' in description.upper():
        return 'Zipcar'

    # Special case: Uber *ONE -> "Uber One" (specific service)
    if merchant.upper() == 'UBER' and re.search(r'\*\s*ONE', description, re.IGNORECASE):
        return 'Uber One'

    # Special case: Uber *EATS -> "Uber" (ignore Eats suffix, return base Uber)
    if merchant.upper() == 'UBER' and re.search(r'\*\s*EATS', description, re.IGNORECASE):
        return 'Uber'

    return merchant


def extract_direct_debit_merchant(description):
    """
    Extract merchant name from direct debit transactions with REF pattern.

    Direct debit transactions have the merchant between "Direct debit payment to" and "REF".
    Examples:
        "Direct debit payment to THAMES WATER REF 123456789" -> "THAMES WATER"
        "DIRECT DEBIT PAYMENT TO BRITISH GAS REF ABC123" -> "BRITISH GAS"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if direct debit REF transaction, None otherwise
    """
    if not description or 'DIRECT DEBIT PAYMENT TO' not in description.upper() or 'REF' not in description.upper():
        return None

    # Look for pattern: DIRECT DEBIT PAYMENT TO {MERCHANT} REF
    # Capture merchant name between "DIRECT DEBIT PAYMENT TO" and "REF"
    match = re.search(r'DIRECT DEBIT PAYMENT TO\s+([A-Z0-9\s]+?)\s+REF', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        # Clean up - remove trailing numbers/codes if present
        merchant = re.sub(r'\s+\d+$', '', merchant)
        if merchant:
            return merchant

    return None


def extract_zettle_merchant(description):
    """
    Extract real merchant name from Zettle transactions.

    Zettle transactions have the real merchant embedded after ZETTLE_*.
    Examples:
        "ZETTLE_*HAGEN ESPRESSO" -> "HAGEN ESPRESSO"
        "ZETTLE_*NETFLIX ON 26-06-2025" -> "NETFLIX"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if Zettle transaction, None otherwise
    """
    if not description or 'ZETTLE' not in description.upper():
        return None

    # Look for pattern: ZETTLE_*MERCHANTNAME
    # Match ZETTLE_* followed by merchant name
    match = re.search(r'ZETTLE_\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        # Clean up - remove trailing numbers/codes if present
        merchant = re.sub(r'\s+\d+$', '', merchant)
        if merchant:
            return merchant

    return None


def extract_via_apple_pay_merchant(description):
    """
    Extract merchant name from VIA APPLE PAY transactions.

    VIA APPLE PAY transactions have the merchant name BEFORE the "(VIA APPLE PAY)" text.
    Examples:
        "HIGHGATE WHOLEFOODS (VIA APPLE PAY), ON 16-05-2025" -> "HIGHGATE WHOLEFOODS"
        "SAINSBURYS (VIA APPLE PAY)" -> "SAINSBURYS"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if VIA APPLE PAY transaction, None otherwise
    """
    if not description or 'VIA APPLE PAY' not in description.upper():
        return None

    # Look for pattern: MERCHANTNAME (VIA APPLE PAY)
    # Extract everything before "(VIA APPLE PAY)"
    match = re.search(r'^(.+?)\s*\(VIA APPLE PAY\)', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        # Clean up - remove trailing numbers/codes if present
        merchant = re.sub(r'\s+\d+$', '', merchant)
        if merchant:
            return merchant

    return None


def extract_paypal_merchant(description):
    """
    Extract real merchant name from PayPal transactions.

    PayPal transactions have the real merchant embedded after an asterisk.
    Examples:
        "CARD PAYMENT TO PAYPAL *NETFLIX ON 26-06-2025" -> "NETFLIX"
        "PAYPAL *AMAZON" -> "AMAZON"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if PayPal transaction, None otherwise
    """
    if not description or 'PAYPAL' not in description.upper():
        return None

    # Look for pattern: *MERCHANTNAME
    # Match asterisk followed by merchant name (letters, spaces, digits)
    # Use greedy matching to capture full merchant name up to date or location code
    match = re.search(r'\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        # Clean up - remove trailing numbers/codes if present
        merchant = re.sub(r'\s+\d+$', '', merchant)
        if merchant:
            return merchant

    return None


def extract_bank_giro_merchant(description):
    """
    Extract merchant name from Bank Giro Credit transactions.

    Bank Giro Credit transactions have the merchant name after "REF".
    Examples:
        "BANK GIRO CREDIT REF CITI PAYROLL, SALARY" -> "CITI PAYROLL, SALARY"
        "BANK GIRO CREDIT REF EMPLOYER PAYMENT" -> "EMPLOYER PAYMENT"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if Bank Giro Credit transaction, None otherwise
    """
    if not description or 'BANK GIRO CREDIT' not in description.upper():
        return None

    # Look for pattern: BANK GIRO CREDIT REF {MERCHANT}
    # Capture everything after "REF " until end of string
    match = re.search(r'BANK GIRO CREDIT\s+REF\s+(.+)$', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        if merchant:
            return merchant

    return None


def extract_bill_payment_merchant(description):
    """
    Extract merchant name from Bill Payment via Faster Payment transactions.

    Bill Payment transactions have the merchant name after "TO".
    Examples:
        "BILL PAYMENT VIA FASTER PAYMENT TO BRITISH GAS REFE ABC123" -> "BRITISH GAS"
        "BILL PAYMENT VIA FASTER PAYMENT TO THAMES WATER REFEREN 123" -> "THAMES WATER"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name if Bill Payment transaction, None otherwise
    """
    if not description or 'BILL PAYMENT VIA FASTER PAYMENT TO' not in description.upper():
        return None

    # Look for pattern: BILL PAYMENT VIA FASTER PAYMENT TO {MERCHANT} REFEREN...
    # Match everything between "TO " and either " REFE", " REFEREN", " REF" or end of string
    match = re.search(r'BILL PAYMENT VIA FASTER PAYMENT TO\s+(.+?)(?:\s+REF(?:E|EREN)?|\s*$)', description, re.IGNORECASE)

    if match:
        merchant = match.group(1).strip()
        if merchant:
            return merchant

    return None


def extract_merchant(description):
    """
    Extract merchant name from transaction description.

    Tries specific patterns first (highest priority) then falls back to generic extraction.
    Priority order:
    1. Bill Payment via Faster Payment (has REF delimiter)
    2. Bank Giro Credit (has REF delimiter)
    3. Direct debit with REF pattern (most specific - has delimiters on both sides)
    2. Card payment to merchant (very specific pattern)
    3. VIA APPLE PAY (payment method but merchant is before it)
    4. Zettle (real merchant is after ZETTLE_*)
    5. PayPal (real merchant is after PAYPAL *)
    6. Generic extraction (fallback)

    Examples:
        "BILL PAYMENT VIA FASTER PAYMENT TO BRITISH GAS REFE ABC123" -> "BRITISH GAS"
        "BANK GIRO CREDIT REF CITI PAYROLL, SALARY" -> "CITI PAYROLL, SALARY"
        "Direct debit payment to THAMES WATER REF 123456789" -> "THAMES WATER"
        "CARD PAYMENT TO AIRBNB * HM4EFPXHB8 ON 30-09-2025" -> "AIRBNB"
        "CARD PAYMENT TO UBER *ONE ON 14-09-2025" -> "Uber One"
        "HIGHGATE WHOLEFOODS (VIA APPLE PAY), ON 16-05-2025" -> "HIGHGATE WHOLEFOODS"
        "ZETTLE_*HAGEN ESPRESSO" -> "HAGEN ESPRESSO"
        "CARD PAYMENT TO PAYPAL *NETFLIX ON 26-06-2025" -> "NETFLIX"
        "TESCO STORES 1234 LONDON" -> "TESCO STORES"

    Args:
        description: Raw transaction description

    Returns:
        Extracted merchant name
    """
    # Try bill payment via faster payment extraction first (has REF delimiter)
    bill_payment_merchant = extract_bill_payment_merchant(description)
    if bill_payment_merchant:
        return bill_payment_merchant

    # Try bank giro credit extraction (has specific REF delimiter)
    bank_giro_merchant = extract_bank_giro_merchant(description)
    if bank_giro_merchant:
        return bank_giro_merchant

    # Try direct debit with REF pattern (most specific - has delimiters on both sides)
    direct_debit_merchant = extract_direct_debit_merchant(description)
    if direct_debit_merchant:
        return direct_debit_merchant

    # Try card payment extraction (very specific pattern)
    card_payment_merchant = extract_card_payment_merchant(description)
    if card_payment_merchant:
        # Special case: if card payment extracted "PAYPAL", check if PayPal extraction finds the real merchant
        # Example: "CARD PAYMENT TO PAYPAL *NETFLIX" should return "NETFLIX", not "PAYPAL"
        if card_payment_merchant.upper() == 'PAYPAL':
            paypal_merchant = extract_paypal_merchant(description)
            if paypal_merchant:
                return paypal_merchant
        return card_payment_merchant

    # Try VIA APPLE PAY extraction (payment method but merchant is before it)
    via_apple_pay_merchant = extract_via_apple_pay_merchant(description)
    if via_apple_pay_merchant:
        return via_apple_pay_merchant

    # Try Zettle extraction (real merchant is after ZETTLE_*)
    zettle_merchant = extract_zettle_merchant(description)
    if zettle_merchant:
        return zettle_merchant

    # Try PayPal extraction (real merchant is after PAYPAL *)
    paypal_merchant = extract_paypal_merchant(description)
    if paypal_merchant:
        return paypal_merchant
    # Remove common prefixes
    prefixes_to_remove = [
        'DIRECT DEBIT PAYMENT TO ',
        'PAYMENT TO ',
        'CARD PAYMENT TO ',
        'ONLINE PAYMENT TO ',
        'TRANSFER TO ',
        'STANDING ORDER TO ',
    ]

    cleaned = description.upper()
    for prefix in prefixes_to_remove:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Remove card numbers (4 digits at the end or in the middle followed by space)
    # This handles: "TESCO STORES 1234 LONDON" and "TESCO 1234"
    cleaned = re.sub(r'\s+\d{4}(?:\s|$)', ' ', cleaned)

    # Remove location codes (like "LONDON", "GB")
    cleaned = re.sub(r'\s+[A-Z]{2,}$', '', cleaned)

    # Remove dates in format DD/MM or DDMMYY
    cleaned = re.sub(r'\s+\d{2}/\d{2}', '', cleaned)
    cleaned = re.sub(r'\s+\d{6}$', '', cleaned)

    # Take first 2-3 words (most likely the merchant name)
    words = cleaned.split()

    if len(words) <= 2:
        return cleaned.strip()
    else:
        # Take first 2-3 words depending on length
        merchant_words = words[:3] if len(words[2]) > 2 else words[:2]
        return ' '.join(merchant_words).strip()
