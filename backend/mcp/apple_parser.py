"""
Apple Transactions Parser MCP Component
Parses Apple "Report a Problem" HTML files to extract transaction data.
"""

import os
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_apple_html(file_path):
    """
    Parse Apple "Report a Problem" HTML file into normalized transaction format.

    The HTML contains DOM-rendered transactions with:
    - Date (e.g., "24 Oct 2025")
    - Order ID (e.g., "MM62VW915F")
    - Price (e.g., "£0.99")
    - App name and publisher info

    Args:
        file_path: Path to the Apple HTML file

    Returns:
        List of transaction dictionaries
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            html_content = f.read()

        return parse_apple_html_content(html_content)

    except Exception as e:
        raise Exception(f"Failed to parse Apple HTML file: {str(e)}")


def parse_apple_html_content(html_content):
    """
    Parse Apple "Report a Problem" HTML content into normalized transaction format.

    This function accepts raw HTML content (e.g., from browser capture) rather than
    a file path. Used by browser-based import.

    Args:
        html_content: Raw HTML string from Apple's Report a Problem page

    Returns:
        List of transaction dictionaries
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Get all text with newline separators to preserve HTML structure
        # This ensures div/span elements are separated by newlines
        text = soup.get_text(separator="\n")

        # Pattern: Date + OrderID + "Total" + Price + App Name
        # With newline separators, structure is:
        # "24 Oct 2025\nMM62VW915F\nTotal\n£0.99\nLoading...\nHazard Perception Test UK\nHazard Perception Test UK Kit\nRenews..."
        # Captures: date, order_id, amount, app_name_section
        # Only match valid days (01-31), handle whitespace/newlines between elements
        # Month can be 3 or 4 letters (Sep or Sept)
        pattern = r"((?:[0-2]?\d|3[01])\s+\w{3,4}\s+\d{4})\s+([A-Z0-9]{10,15})\s+Total\s+[£$](\d+\.\d{2})\s+Loading\.\.\.\s+(.+?)(?=\s*(?:[0-2]?\d|3[01])\s+\w{3,4}\s+\d{4}\s+[A-Z0-9]|$)"

        matches = re.findall(pattern, text, re.DOTALL)

        transactions = []
        seen_orders = set()  # Track duplicates

        for match in matches:
            date_str, order_id, amount, app_info = match

            # Skip duplicates
            if order_id in seen_orders:
                continue
            seen_orders.add(order_id)

            # Clean up app info - split into app name and publisher
            app_info = app_info.strip()

            # Remove common trailing text
            app_info = re.sub(
                r"Renews\s+\d+\s+\w+\s+\d{4}.*$", "", app_info, flags=re.IGNORECASE
            )
            app_info = re.sub(r"\s*Renews\s*$", "", app_info, flags=re.IGNORECASE)

            # Often the pattern is "App NamePublisher Name" - try to split intelligently
            lines = [line.strip() for line in app_info.split("\n") if line.strip()]

            if len(lines) >= 2:
                app_name = lines[0]
                publisher = (
                    lines[1] if len(lines[1]) > 2 else ""
                )  # Skip very short publishers
            elif len(lines) == 1:
                # Single line: often "AppNamePublisher" concatenated
                # Example: "Apple TV+Apple TV", "BFI PlayerApple TV"
                text = lines[0]

                app_name = text  # Default to full text
                publisher = ""

                # Strategy 1: Look for lowercase-to-uppercase transition (concatenation point)
                # This catches "PlayerApple" where there's no space
                concat_match = re.search(r"[a-z]([A-Z][a-z])", text)
                if concat_match:
                    # Found concatenation point - split here
                    split_point = concat_match.start(1)  # Start of the capital letter
                    app_name = text[:split_point].strip()
                    publisher = text[split_point:].strip()
                else:
                    # Strategy 2: Look for repeated capitalized words
                    # Find all capitalized words (with word boundaries or after special chars)
                    seen = set()
                    split_point = -1
                    for match in re.finditer(r"(?:^|[\s+&-])([A-Z][A-Za-z]+)", text):
                        word = match.group(1)
                        if word in seen:
                            # Found repetition - split here
                            split_point = match.start(1)
                            break
                        seen.add(word)

                    if split_point > 0:
                        app_name = text[:split_point].strip()
                        publisher = text[split_point:].strip()

                # Fallback: if app name is too short or empty, use full text
                if len(app_name) < 3:
                    app_name = text[:80].strip()
                    publisher = ""
            else:
                app_name = app_info[:80].strip()  # Fallback with length limit
                publisher = ""

            transaction = {
                "order_id": order_id,
                "order_date": clean_date(date_str),
                "total_amount": float(amount),
                "currency": "GBP",
                "app_names": app_name,
                "publishers": publisher,
                "item_count": 1,
            }
            transactions.append(transaction)

        return transactions

    except Exception as e:
        raise Exception(f"Failed to parse Apple HTML content: {str(e)}")


def parse_json_from_script(script_content):
    """
    Extract transaction data from embedded JSON in script tags.

    Args:
        script_content: JavaScript content containing JSON data

    Returns:
        List of transactions
    """
    import json

    transactions = []

    try:
        # Try to find JSON objects in the script
        # Look for patterns like {"orderDate": "...", "orderId": "...", ...}
        json_pattern = r'\{[^{}]*"orderDate"[^{}]*\}'
        matches = re.findall(json_pattern, script_content)

        for match in matches:
            try:
                data = json.loads(match)
                transaction = {
                    "order_id": data.get("orderId", data.get("WebOrder", "")),
                    "order_date": clean_date(data.get("orderDate", "")),
                    "total_amount": clean_currency(data.get("totalPrice", "0")),
                    "currency": "GBP",
                    "app_names": data.get("title", ""),
                    "publishers": data.get("artistName", ""),
                    "item_count": 1,
                }
                transactions.append(transaction)
            except json.JSONDecodeError:
                continue

    except Exception as e:
        print(f"Warning: Could not parse JSON from script: {e}")

    return transactions


def parse_html_structure(soup):
    """
    Parse transaction data from HTML structure.

    Args:
        soup: BeautifulSoup object

    Returns:
        List of transactions
    """
    transactions = []

    # Find all invoice/order containers
    # This will need to be adjusted based on actual HTML structure
    # For now, creating a placeholder structure

    # Example structure we're looking for:
    # <div class="invoice-date">10 Oct 2019</div>
    # <div class="WebOrder">R3H2QZZWJWW</div>
    # <li class="pli" aria-label="Google Assistant">

    # Group by order ID
    from collections import defaultdict

    orders = defaultdict(list)

    # Find all purchase items
    items = soup.find_all("li", class_="pli")

    for item in items:
        # Extract app name from aria-label
        app_name = item.get("aria-label", "")

        # Find associated order info (may be in parent or sibling elements)
        # This is a simplified approach - actual structure may vary
        order_container = item.find_parent("div", class_="order") or item.find_parent(
            "section"
        )

        if order_container:
            date_elem = order_container.find(
                class_="invoice-date"
            ) or order_container.find(string=re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}"))
            order_id_elem = order_container.find(
                class_="WebOrder"
            ) or order_container.find(string=re.compile(r"[A-Z0-9]{11}"))
            price_elem = item.find(class_="price")

            order_data = {
                "date": date_elem.get_text() if date_elem else "",
                "order_id": order_id_elem.get_text() if order_id_elem else "",
                "app_name": app_name,
                "price": price_elem.get_text() if price_elem else "Free",
            }

            if order_data["order_id"]:
                orders[order_data["order_id"]].append(order_data)

    # Convert grouped orders to transactions
    for order_id, items in orders.items():
        if items:
            first_item = items[0]
            app_names = " | ".join(
                [item["app_name"] for item in items if item["app_name"]]
            )
            total = sum([clean_currency(item["price"]) for item in items])

            transaction = {
                "order_id": order_id,
                "order_date": clean_date(first_item["date"]),
                "total_amount": total,
                "currency": "GBP",
                "app_names": app_names or "Unknown",
                "publishers": "",
                "item_count": len(items),
            }
            transactions.append(transaction)

    return transactions


def clean_date(date_str):
    """
    Clean and normalize date from Apple format.
    Apple uses: "10 Oct 2019", "20 Aug 2019", "24 Sept 2024" etc.

    Args:
        date_str: Raw date string

    Returns:
        Normalized date string (YYYY-MM-DD)
    """
    if not date_str:
        return None

    try:
        date_str = str(date_str).strip()

        # Handle 4-letter month abbreviations (Sept, June, July, etc.)
        # Convert to 3-letter format for Python's datetime parser
        date_str = date_str.replace("Sept", "Sep")
        date_str = date_str.replace("June", "Jun")
        date_str = date_str.replace("July", "Jul")

        # Handle format: "10 Oct 2019"
        date_obj = datetime.strptime(date_str, "%d %b %Y")
        return date_obj.strftime("%Y-%m-%d")

    except Exception as e:
        print(f"Warning: Could not parse date '{date_str}': {e}")
        return None


def clean_currency(value):
    """
    Clean currency value and convert to float.
    Handles: "£2.99", "£0.00", "Free", "$4.99"

    Args:
        value: Raw currency value

    Returns:
        Float value or 0.0 if invalid/free
    """
    if not value:
        return 0.0

    # Handle "Free" apps
    if isinstance(value, str) and value.strip().upper() == "FREE":
        return 0.0

    # If already a number, return it
    if isinstance(value, (int, float)):
        return float(value)

    # Convert to string and clean
    value_str = str(value).strip()

    # Remove currency symbols and commas
    cleaned = (
        value_str.replace("£", "").replace("$", "").replace(",", "").replace(" ", "")
    )

    try:
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse currency value '{value_str}'")
        return 0.0


def export_to_csv(transactions, output_path):
    """
    Export transactions to CSV format.

    Args:
        transactions: List of transaction dictionaries
        output_path: Path for output CSV file

    Returns:
        Path to created CSV file
    """
    import csv

    if not transactions:
        raise ValueError("No transactions to export")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "order_id",
            "order_date",
            "total_amount",
            "currency",
            "app_names",
            "publishers",
            "item_count",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        for transaction in transactions:
            writer.writerow(transaction)

    return output_path


def get_apple_html_files(data_folder="../sample"):
    """
    List available Apple HTML files in the data folder.

    Args:
        data_folder: Path to folder containing HTML files

    Returns:
        List of HTML file paths
    """
    try:
        files = []
        for filename in os.listdir(data_folder):
            # Look for HTML files with "report", "problem", or "apple" in name
            if filename.endswith(".html") and any(
                keyword in filename.lower()
                for keyword in ["report", "problem", "apple", "purchase"]
            ):
                files.append(os.path.join(data_folder, filename))
        return files
    except Exception as e:
        print(f"Error listing Apple HTML files: {e}")
        return []
