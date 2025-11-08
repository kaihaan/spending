"""
Santander HTML Parser
Parses Santander bank statements that are HTML files disguised as .xls files.
"""

import pandas as pd
import re
from mcp.merchant_normalizer import normalize_merchant_name


def parse_santander_html(file_path):
    """
    Parse Santander HTML-format bank statement.

    These files have .xls extension but are actually HTML tables.

    Format:
    - Column 1: Date (DD/MM/YYYY)
    - Column 3: Description
    - Column 5: Money in (Credit)
    - Column 6: Money Out (Debit)
    - Column 7: Balance

    Args:
        file_path: Path to the HTML file

    Returns:
        List of transaction dictionaries
    """
    try:
        # Read HTML tables
        tables = pd.read_html(file_path, encoding='iso-8859-1')

        if not tables:
            raise ValueError("No tables found in HTML file")

        # Get the first (and usually only) table
        df = tables[0]

        # Find where actual transactions start
        # Look for row with "Date" in column 1
        start_row = None
        for idx, row in df.iterrows():
            if str(row[1]).strip().lower() == 'date':
                start_row = idx + 2  # Skip the header and empty row
                break

        if start_row is None:
            # Fallback: start from row 5 (common pattern)
            start_row = 5

        # Extract transactions
        transactions = []

        for idx in range(start_row, len(df)):
            row = df.iloc[idx]

            # Extract date from column 1
            date_str = str(row[1]).strip()
            if date_str == 'nan' or not date_str or date_str == '':
                continue

            # Skip if not a date format (DD/MM/YYYY)
            if not re.match(r'\d{2}/\d{2}/\d{4}', date_str):
                continue

            # Extract description from column 3
            description = str(row[3]).strip()
            if description == 'nan' or not description:
                continue

            # Extract credit and debit from columns 5 and 6
            credit_str = str(row[5]).strip()
            debit_str = str(row[6]).strip()

            # Determine amount
            amount = 0.0

            if credit_str != 'nan' and credit_str != '':
                # Money in (positive)
                amount = parse_currency(credit_str)
            elif debit_str != 'nan' and debit_str != '':
                # Money out (negative)
                amount = -parse_currency(debit_str)
            else:
                # Skip if no amount
                continue

            # Convert date from DD/MM/YYYY to YYYY-MM-DD
            try:
                day, month, year = date_str.split('/')
                formatted_date = f"{year}-{month}-{day}"
            except:
                continue

            # Extract merchant from description
            merchant = extract_merchant_from_description(description)
            normalized_merchant = normalize_merchant_name(merchant, description)

            transactions.append({
                'date': formatted_date,
                'description': description,
                'amount': amount,
                'merchant': normalized_merchant,
                'source_file': file_path.split('/')[-1]
            })

        return transactions

    except Exception as e:
        raise Exception(f"Failed to parse Santander HTML file: {str(e)}")


def parse_currency(value_str):
    """
    Parse UK currency string to float.

    Examples:
        "£3.10" -> 3.10
        "£1,430.95" -> 1430.95

    Args:
        value_str: Currency string

    Returns:
        Float value
    """
    # Remove £ symbol, commas, and spaces
    cleaned = value_str.replace('£', '').replace(',', '').replace(' ', '').strip()

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_merchant_from_description(description):
    """
    Extract merchant name from Santander transaction description.

    Examples:
        "CARD PAYMENT TO Caffe Nero UK App ON 30-09-2024" -> "Caffe Nero UK App"
        "ZETTLE_*FOOD & MOOD BY (VIA APPLE PAY), ON 29-09-2024" -> "FOOD & MOOD BY"
        "TRANSFER FROM MR KAIHAAN ANTONY JAMSHIDI" -> "KAIHAAN ANTONY JAMSHIDI"
        "TFL TRAVEL CH (VIA APPLE PAY), ON 29-09-2024" -> "TFL TRAVEL CH"
        "DIRECT DEBIT PAYMENT TO LAND & PROPERTY SE REF 00937818" -> "LAND & PROPERTY SE"

    Args:
        description: Transaction description

    Returns:
        Extracted merchant name
    """
    # Remove common prefixes
    prefixes = [
        r'CARD PAYMENT TO ',
        r'DIRECT DEBIT PAYMENT TO ',
        r'TRANSFER FROM ',
        r'TRANSFER TO ',
        r'STANDING ORDER TO ',
        r'ZETTLE_\*',
        r'PPOINT_\*',
    ]

    cleaned = description
    for prefix in prefixes:
        cleaned = re.sub(f'^{prefix}', '', cleaned, flags=re.IGNORECASE)

    # Remove payment method suffixes
    cleaned = re.sub(r'\s*\(VIA APPLE PAY\)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\(VIA GOOGLE PAY\)', '', cleaned, flags=re.IGNORECASE)

    # Remove date suffix (e.g., ", ON 29-09-2024")
    cleaned = re.sub(r',?\s*ON \d{2}-\d{2}-\d{4}', '', cleaned, flags=re.IGNORECASE)

    # Remove reference numbers (e.g., "REF 00937818, MANDATE NO 0019")
    cleaned = re.sub(r',?\s*REF \d+.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r',?\s*MANDATE NO \d+.*$', '', cleaned, flags=re.IGNORECASE)

    # Trim and limit length
    cleaned = cleaned.strip()

    # If too long, take first few words
    words = cleaned.split()
    if len(words) > 4:
        cleaned = ' '.join(words[:4])

    return cleaned.strip()
