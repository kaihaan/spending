"""
Amazon Order History Parser MCP Component
Parses Amazon CSV order history files and extracts transaction data.
Supports Amazon.co.uk, Amazon.com, Amazon Digital, and Amazon Marketplace.
"""

import pandas as pd
import io
from datetime import datetime
from collections import defaultdict


def parse_amazon_csv(file_path):
    """
    Parse Amazon order history CSV file into normalized order format.

    Args:
        file_path: Path to the Amazon CSV file

    Returns:
        List of order dictionaries with consolidated product names
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)

        # Verify required columns exist
        required_columns = ['Website', 'Order ID', 'Order Date', 'Total Owed', 'Product Name']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        # Group items by Order ID to handle multi-item orders
        orders_dict = defaultdict(list)

        for idx, row in df.iterrows():
            # Skip rows with no order ID or product name
            if pd.isna(row['Order ID']) or pd.isna(row['Product Name']):
                continue

            order_id = str(row['Order ID']).strip()

            orders_dict[order_id].append({
                'order_id': order_id,
                'order_date': clean_date(row['Order Date']),
                'website': str(row['Website']).strip(),
                'currency': str(row.get('Currency', 'GBP')).strip(),
                'total_owed': clean_currency(row['Total Owed']),
                'product_name': str(row['Product Name']).strip(),
                'order_status': str(row.get('Order Status', '')).strip() if 'Order Status' in row else None,
                'shipment_status': str(row.get('Shipment Status', '')).strip() if 'Shipment Status' in row else None,
            })

        # Consolidate orders - combine product names for multi-item orders
        consolidated_orders = []

        for order_id, items in orders_dict.items():
            # Use first item for base data (all items in same order have same metadata)
            base_item = items[0]

            # Combine product names
            if len(items) == 1:
                product_names = base_item['product_name']
            else:
                # Multiple items - abbreviate each and join
                abbreviated_names = [abbreviate_product_name(item['product_name']) for item in items]
                product_names = ' | '.join(abbreviated_names)

                # If still too long, truncate to first few items
                if len(product_names) > 150:
                    first_items = ' | '.join(abbreviated_names[:3])
                    remaining = len(items) - 3
                    product_names = f"{first_items} & {remaining} more"

            consolidated_orders.append({
                'order_id': base_item['order_id'],
                'order_date': base_item['order_date'],
                'website': base_item['website'],
                'currency': base_item['currency'],
                'total_owed': base_item['total_owed'],
                'product_names': product_names,
                'order_status': base_item['order_status'],
                'shipment_status': base_item['shipment_status'],
            })

        return consolidated_orders

    except Exception as e:
        raise Exception(f"Failed to parse Amazon CSV: {str(e)}")


def parse_amazon_csv_content(csv_content: str) -> list:
    """
    Parse Amazon order history from CSV string content.

    Args:
        csv_content: CSV file content as a string

    Returns:
        List of order dictionaries with consolidated product names
    """
    try:
        # Read CSV from string content
        df = pd.read_csv(io.StringIO(csv_content))

        # Verify required columns exist
        required_columns = ['Website', 'Order ID', 'Order Date', 'Total Owed', 'Product Name']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        # Group items by Order ID to handle multi-item orders
        orders_dict = defaultdict(list)

        for idx, row in df.iterrows():
            # Skip rows with no order ID or product name
            if pd.isna(row['Order ID']) or pd.isna(row['Product Name']):
                continue

            order_id = str(row['Order ID']).strip()

            orders_dict[order_id].append({
                'order_id': order_id,
                'order_date': clean_date(row['Order Date']),
                'website': str(row['Website']).strip(),
                'currency': str(row.get('Currency', 'GBP')).strip(),
                'total_owed': clean_currency(row['Total Owed']),
                'product_name': str(row['Product Name']).strip(),
                'order_status': str(row.get('Order Status', '')).strip() if 'Order Status' in row else None,
                'shipment_status': str(row.get('Shipment Status', '')).strip() if 'Shipment Status' in row else None,
            })

        # Consolidate orders - combine product names for multi-item orders
        consolidated_orders = []

        for order_id, items in orders_dict.items():
            # Use first item for base data (all items in same order have same metadata)
            base_item = items[0]

            # Combine product names
            if len(items) == 1:
                product_names = base_item['product_name']
            else:
                # Multiple items - abbreviate each and join
                abbreviated_names = [abbreviate_product_name(item['product_name']) for item in items]
                product_names = ' | '.join(abbreviated_names)

                # If still too long, truncate to first few items
                if len(product_names) > 150:
                    first_items = ' | '.join(abbreviated_names[:3])
                    remaining = len(items) - 3
                    product_names = f"{first_items} & {remaining} more"

            consolidated_orders.append({
                'order_id': base_item['order_id'],
                'order_date': base_item['order_date'],
                'website': base_item['website'],
                'currency': base_item['currency'],
                'total_owed': base_item['total_owed'],
                'product_names': product_names,
                'order_status': base_item['order_status'],
                'shipment_status': base_item['shipment_status'],
            })

        return consolidated_orders

    except Exception as e:
        raise Exception(f"Failed to parse Amazon CSV content: {str(e)}")


def abbreviate_product_name(product_name, max_length=35):
    """
    Abbreviate a product name to a maximum length while keeping it recognizable.
    Tries to break at word boundaries.

    Args:
        product_name: Full product name
        max_length: Maximum characters to keep

    Returns:
        Abbreviated product name
    """
    if len(product_name) <= max_length:
        return product_name

    # Try to break at last space before max_length
    truncated = product_name[:max_length]
    last_space = truncated.rfind(' ')

    if last_space > max_length * 0.7:  # If space is reasonably close to end
        truncated = truncated[:last_space]

    # Remove trailing punctuation and incomplete words
    truncated = truncated.rstrip('.,:-()[]')

    return truncated.strip()


def clean_date(date_str):
    """
    Clean and normalize date from Amazon format.
    Amazon uses ISO format: 2025-10-20T08:28:33Z

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
    Handles various formats including negative values in quotes.

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


def get_amazon_csv_files(data_folder='../sample'):
    """
    List available Amazon CSV files in the data folder.

    Args:
        data_folder: Path to folder containing CSV files

    Returns:
        List of CSV file paths
    """
    import os

    try:
        files = []
        for filename in os.listdir(data_folder):
            if filename.endswith('.csv') and ('amazon' in filename.lower() or 'orderhistory' in filename.lower()):
                files.append(os.path.join(data_folder, filename))
        return files
    except Exception as e:
        print(f"Error listing Amazon CSV files: {e}")
        return []
