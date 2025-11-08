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


def extract_merchant(description):
    """
    Extract merchant name from transaction description.

    This is a simple heuristic that takes the first few words.
    Can be enhanced with more sophisticated parsing later.

    Examples:
        "TESCO STORES 1234 LONDON" -> "TESCO STORES"
        "AMAZON PRIME MEMBERSHIP" -> "AMAZON PRIME"
        "DIRECT DEBIT PAYMENT TO THAMES WATER" -> "THAMES WATER"

    Args:
        description: Raw transaction description

    Returns:
        Extracted merchant name
    """
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

    # Remove card numbers (4 digits at the end)
    cleaned = re.sub(r'\s+\d{4}$', '', cleaned)

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
