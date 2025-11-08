"""
Amazon Returns Parser MCP Component
Parses Amazon returns/refunds CSV files.
"""

import pandas as pd
from datetime import datetime


def parse_amazon_returns_csv(file_path):
    """
    Parse Amazon returns CSV file into normalized return format.

    Args:
        file_path: Path to the Amazon returns CSV file

    Returns:
        List of return dictionaries
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)

        # Verify required columns exist
        required_columns = ['OrderID', 'ReversalID', 'RefundCompletionDate', 'AmountRefunded']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        returns = []

        for idx, row in df.iterrows():
            # Skip rows with no order ID or reversal ID
            if pd.isna(row['OrderID']) or pd.isna(row['ReversalID']):
                continue

            returns.append({
                'order_id': str(row['OrderID']).strip(),
                'reversal_id': str(row['ReversalID']).strip(),
                'refund_completion_date': clean_date(row['RefundCompletionDate']),
                'currency': str(row.get('Currency', 'GBP')).strip(),
                'amount_refunded': clean_currency(row['AmountRefunded']),
                'status': str(row.get('Status', '')).strip() if 'Status' in row else None,
                'disbursement_type': str(row.get('DisbursementType', '')).strip() if 'DisbursementType' in row else None,
            })

        return returns

    except Exception as e:
        raise Exception(f"Failed to parse Amazon returns CSV: {str(e)}")


def clean_date(date_str):
    """
    Clean and normalize date from Amazon format.
    Amazon uses ISO format: 2025-08-12T22:09:43.797Z

    Args:
        date_str: Raw date string

    Returns:
        Normalized date string (YYYY-MM-DD)
    """
    if pd.isna(date_str):
        return None

    try:
        # Parse ISO format
        date_str = str(date_str).strip()

        # Handle ISO format with timezone
        if 'T' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')

        return date_obj.strftime('%Y-%m-%d')

    except Exception as e:
        print(f"Warning: Could not parse date '{date_str}': {e}")
        return None


def clean_currency(value):
    """
    Clean currency value and convert to float.

    Args:
        value: Raw currency value

    Returns:
        Float value or 0.0 if invalid
    """
    if pd.isna(value):
        return 0.0

    # If already a number, return it
    if isinstance(value, (int, float)):
        return float(value)

    # Convert to string and clean
    value_str = str(value).strip()

    # Remove currency symbols and commas
    cleaned = value_str.replace('£', '').replace('$', '').replace(',', '').replace(' ', '')

    # Handle quoted negative numbers: '-0.2' -> -0.2
    cleaned = cleaned.replace("'", "")

    try:
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse currency value '{value_str}'")
        return 0.0


def get_amazon_returns_csv_files(data_folder='../sample'):
    """
    List available Amazon returns CSV files in the data folder.

    Args:
        data_folder: Path to folder containing CSV files

    Returns:
        List of CSV file paths
    """
    import os

    try:
        files = []
        for filename in os.listdir(data_folder):
            if filename.endswith('.csv') and 'return' in filename.lower():
                files.append(os.path.join(data_folder, filename))
        return files
    except Exception as e:
        print(f"Error listing Amazon returns CSV files: {e}")
        return []
