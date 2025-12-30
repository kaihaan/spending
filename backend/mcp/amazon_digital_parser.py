"""
Amazon Digital Orders Parser MCP Component
Parses Amazon digital orders CSV files (Kindle, Video, Music, Prime subscriptions, etc.).
"""

import io
from datetime import datetime

import pandas as pd


def parse_amazon_digital_csv_content(csv_content: str) -> list:
    """
    Parse Amazon digital orders from CSV string content.

    Args:
        csv_content: CSV file content as a string

    Returns:
        List of digital order dictionaries
    """
    try:
        # Read CSV from string content
        df = pd.read_csv(io.StringIO(csv_content))

        # Verify required columns exist
        required_columns = [
            "ASIN",
            "ProductName",
            "OrderId",
            "DigitalOrderItemId",
            "OrderDate",
            "OurPrice",
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        orders = []

        for _, row in df.iterrows():
            # Skip rows with no order ID or item ID
            if pd.isna(row["OrderId"]) or pd.isna(row["DigitalOrderItemId"]):
                continue

            # Skip rows with zero price (free items)
            price = clean_currency(row["OurPrice"])
            if price == 0.0:
                continue

            orders.append(
                {
                    "asin": str(row["ASIN"]).strip()
                    if not pd.isna(row["ASIN"])
                    else "",
                    "product_name": clean_string(row["ProductName"]),
                    "order_id": str(row["OrderId"]).strip(),
                    "digital_order_item_id": str(row["DigitalOrderItemId"]).strip(),
                    "order_date": clean_datetime(row["OrderDate"]),
                    "fulfilled_date": clean_datetime(row.get("FulfilledDate")),
                    "price": price,
                    "price_tax": clean_currency(row.get("OurPriceTax")),
                    "currency": str(row.get("OurPriceCurrencyCode", "GBP")).strip(),
                    "publisher": clean_string(row.get("Publisher")),
                    "seller_of_record": clean_string(row.get("SellerOfRecord")),
                    "marketplace": clean_string(row.get("Marketplace")),
                }
            )

        return orders

    except Exception as e:
        raise Exception(
            f"Failed to parse Amazon digital orders CSV content: {e!s}"
        ) from e


def parse_amazon_digital_csv(file_path: str) -> list:
    """
    Parse Amazon digital orders CSV file into normalized order format.

    Args:
        file_path: Path to the Amazon digital orders CSV file

    Returns:
        List of digital order dictionaries
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)

        # Verify required columns exist
        required_columns = [
            "ASIN",
            "ProductName",
            "OrderId",
            "DigitalOrderItemId",
            "OrderDate",
            "OurPrice",
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        orders = []

        for _, row in df.iterrows():
            # Skip rows with no order ID or item ID
            if pd.isna(row["OrderId"]) or pd.isna(row["DigitalOrderItemId"]):
                continue

            # Skip rows with zero price (free items)
            price = clean_currency(row["OurPrice"])
            if price == 0.0:
                continue

            orders.append(
                {
                    "asin": str(row["ASIN"]).strip()
                    if not pd.isna(row["ASIN"])
                    else "",
                    "product_name": clean_string(row["ProductName"]),
                    "order_id": str(row["OrderId"]).strip(),
                    "digital_order_item_id": str(row["DigitalOrderItemId"]).strip(),
                    "order_date": clean_datetime(row["OrderDate"]),
                    "fulfilled_date": clean_datetime(row.get("FulfilledDate")),
                    "price": price,
                    "price_tax": clean_currency(row.get("OurPriceTax")),
                    "currency": str(row.get("OurPriceCurrencyCode", "GBP")).strip(),
                    "publisher": clean_string(row.get("Publisher")),
                    "seller_of_record": clean_string(row.get("SellerOfRecord")),
                    "marketplace": clean_string(row.get("Marketplace")),
                }
            )

        return orders

    except Exception as e:
        raise Exception(f"Failed to parse Amazon digital orders CSV: {e!s}") from e


def clean_datetime(date_str) -> datetime | None:
    """
    Clean and normalize datetime from Amazon format.
    Amazon uses ISO format: 2025-06-01T19:25:00Z

    Args:
        date_str: Raw date string

    Returns:
        datetime object with timezone info, or None if invalid
    """
    if pd.isna(date_str):
        return None

    try:
        date_str = str(date_str).strip()

        # Handle ISO format with timezone
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Handle date-only format
        return datetime.strptime(date_str, "%Y-%m-%d")

    except Exception as e:
        print(f"Warning: Could not parse datetime '{date_str}': {e}")
        return None


def clean_currency(value) -> float:
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
    if isinstance(value, int | float):
        return float(value)

    # Convert to string and clean
    value_str = str(value).strip()

    # Remove currency symbols and commas
    cleaned = (
        value_str.replace("£", "").replace("$", "").replace(",", "").replace(" ", "")
    )

    # Handle quoted negative numbers
    cleaned = cleaned.replace("'", "")

    try:
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse currency value '{value_str}'")
        return 0.0


def clean_string(value) -> str | None:
    """
    Clean string value, handling 'Not Applicable' and NaN.

    Args:
        value: Raw string value

    Returns:
        Cleaned string or None if empty/NA
    """
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    # Handle 'Not Applicable' as null
    if value_str.lower() == "not applicable":
        return None

    return value_str if value_str else None
