"""
Gmail Schema.org Extraction

Extracts structured receipt data from Schema.org markup in emails.
Supports JSON-LD, Microdata, and RDFa formats.
"""

import json
import re

from bs4 import BeautifulSoup

from mcp.logging_config import get_logger

from .utilities import normalize_merchant_name, parse_date_string

# Initialize logger
logger = get_logger(__name__)

# Check if extruct is available
try:
    import extruct

    EXTRUCT_AVAILABLE = True
except ImportError:
    EXTRUCT_AVAILABLE = False


def extract_schema_org(html_body: str) -> dict | None:
    """
    Extract Schema.org data from email HTML using extruct.

    Handles JSON-LD, Microdata, and RDFa formats uniformly.

    Args:
        html_body: Raw HTML content of email

    Returns:
        Parsed receipt dictionary or None
    """
    if not html_body:
        return None

    # Try extruct first (handles JSON-LD, Microdata, RDFa)
    if EXTRUCT_AVAILABLE:
        result = _extract_with_extruct(html_body)
        if result:
            return result

    # Fallback to manual BeautifulSoup parsing for JSON-LD only
    return _extract_json_ld_manual(html_body)


def _extract_with_extruct(html_body: str) -> dict | None:
    """
    Extract structured data using extruct library.

    Args:
        html_body: Raw HTML content

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        # Extract all supported formats
        data = extruct.extract(
            html_body,
            syntaxes=["json-ld", "microdata", "rdfa"],
            uniform=True,  # Normalize all formats to same structure
        )

        # Check each syntax type for Order/Invoice/Receipt
        for syntax in ["json-ld", "microdata", "rdfa"]:
            items = data.get(syntax, [])
            for item in items:
                item_type = item.get("@type", "")

                # Handle array types (extruct sometimes returns list)
                if isinstance(item_type, list):
                    item_type = item_type[0] if item_type else ""

                # Check for receipt-related types
                if item_type in ["Order", "Invoice", "Receipt", "ConfirmAction"]:
                    return parse_schema_org_order(item)

                # Check nested @graph structure
                if "@graph" in item:
                    for node in item["@graph"]:
                        node_type = node.get("@type", "")
                        if isinstance(node_type, list):
                            node_type = node_type[0] if node_type else ""
                        if node_type in ["Order", "Invoice", "Receipt"]:
                            return parse_schema_org_order(node)

    except Exception as e:
        logger.warning(f"Extruct extraction failed: {e}", exc_info=True)

    return None


def _extract_json_ld_manual(html_body: str) -> dict | None:
    """
    Fallback manual JSON-LD extraction using BeautifulSoup.

    Args:
        html_body: Raw HTML content

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        soup = BeautifulSoup(html_body, "lxml")
    except Exception:
        soup = BeautifulSoup(html_body, "html.parser")

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            if not script.string:
                continue

            data = json.loads(script.string)

            # Handle both single object and array of objects
            items = data if isinstance(data, list) else [data]

            for item in items:
                item_type = item.get("@type", "")

                # Check for receipt-related types
                if item_type in ["Order", "Invoice", "Receipt", "ConfirmAction"]:
                    return parse_schema_org_order(item)

                # Check nested @graph structure
                if "@graph" in item:
                    for node in item["@graph"]:
                        if node.get("@type") in ["Order", "Invoice", "Receipt"]:
                            return parse_schema_org_order(node)

        except (json.JSONDecodeError, AttributeError, TypeError):
            continue

    return None


def parse_schema_org_order(data: dict) -> dict:
    """
    Parse Schema.org Order/Invoice into our receipt format.

    Args:
        data: Schema.org JSON-LD object

    Returns:
        Receipt data dictionary
    """
    # Extract merchant name from various possible locations
    merchant_name = None
    seller = data.get("seller") or data.get("merchant") or data.get("provider")
    if isinstance(seller, dict):
        merchant_name = seller.get("name")
    elif isinstance(seller, str):
        merchant_name = seller

    # Extract total amount
    total_amount = None
    currency = "GBP"

    # Try price specification first
    price_spec = data.get("acceptedOffer", {}).get("priceSpecification", {})
    if price_spec:
        total_amount = price_spec.get("price")
        currency = price_spec.get("priceCurrency", "GBP")

    # Fallback to direct price fields
    if total_amount is None:
        total_amount = (
            data.get("totalPrice")
            or data.get("total")
            or data.get("price")
            or data.get("totalPaymentDue", {}).get("value")
        )

    if total_amount is None:
        total_payment = data.get("totalPaymentDue")
        if isinstance(total_payment, dict):
            total_amount = total_payment.get("value") or total_payment.get("price")
            currency = total_payment.get("priceCurrency", currency)

    # Convert amount to float
    if total_amount is not None:
        try:
            total_amount = float(str(total_amount).replace(",", ""))
        except (ValueError, TypeError):
            total_amount = None

    # Extract date
    receipt_date = None
    date_str = (
        data.get("orderDate") or data.get("paymentDueDate") or data.get("dateCreated")
    )
    if date_str:
        receipt_date = parse_date_string(date_str)

    # Extract line items with enhanced data
    line_items = []
    ordered_items = data.get("orderedItem", [])
    if not isinstance(ordered_items, list):
        ordered_items = [ordered_items]

    for item in ordered_items:
        if isinstance(item, dict):
            item_name = item.get("name") or item.get("orderedItem", {}).get("name")
            item_desc = item.get("description")
            item_price = item.get("price")

            # Try to get price from nested priceSpecification
            if item_price is None:
                price_spec = item.get("priceSpecification", {})
                if isinstance(price_spec, dict):
                    item_price = price_spec.get("price")

            # Try to convert price to float
            if item_price is not None:
                try:
                    item_price = float(str(item_price).replace(",", ""))
                except (ValueError, TypeError):
                    item_price = None

            line_items.append(
                {
                    "name": item_name,
                    "description": item_desc or infer_description_from_name(item_name),
                    "category_hint": infer_category_from_name(item_name),
                    "quantity": item.get("orderQuantity", 1),
                    "price": item_price,
                }
            )

    return {
        "merchant_name": merchant_name,
        "merchant_name_normalized": normalize_merchant_name(merchant_name),
        "order_id": data.get("orderNumber") or data.get("confirmationNumber"),
        "total_amount": total_amount,
        "currency_code": currency,
        "receipt_date": receipt_date,
        "line_items": line_items if line_items else None,
        "parse_method": "schema_org",
        "parse_confidence": 95,
        "parsing_status": "parsed",
        "raw_schema_data": data,
    }


def infer_description_from_name(name: str) -> str | None:
    """
    Infer a brief description from product name.

    Args:
        name: Product name

    Returns:
        Brief description or None
    """
    if not name:
        return None

    name_lower = name.lower()

    type_patterns = [
        (r"headphone|earphone|earbud|airpod", "audio headphones/earbuds"),
        (r"cable|charger|adapter|usb", "charging/connectivity accessory"),
        (r"case|cover|screen protector", "protective case/cover"),
        (r"battery|power bank", "portable power/battery"),
        (r"book|kindle|paperback|hardcover", "book"),
        (r"shirt|dress|pants|jeans|jacket|coat", "clothing item"),
        (r"toy|lego|game|puzzle", "toy/game"),
        (r"vitamin|supplement|medicine", "health supplement"),
        (r"food|snack|chocolate|coffee|tea", "food/beverage"),
        (r"cleaning|soap|detergent", "cleaning product"),
        (r"phone|tablet|laptop|computer", "electronic device"),
        (r"subscription|monthly|annual", "subscription service"),
        (r"delivery|shipping", "delivery service"),
    ]

    for pattern, description in type_patterns:
        if re.search(pattern, name_lower):
            return description

    return None


def infer_category_from_name(name: str) -> str:
    """
    Infer category hint from product name.

    Args:
        name: Product name

    Returns:
        Category hint string
    """
    if not name:
        return "other"

    name_lower = name.lower()

    category_patterns = [
        (
            r"headphone|speaker|audio|earphone|earbud|airpod|cable|charger|phone|tablet|laptop|computer|usb|hdmi|adapter|battery|power bank",
            "electronics",
        ),
        (r"book|kindle|paperback|hardcover|novel|magazine", "entertainment"),
        (
            r"shirt|dress|pants|jeans|jacket|coat|shoe|sock|underwear|clothing",
            "clothing",
        ),
        (
            r"food|snack|chocolate|coffee|tea|grocery|organic|vitamin|supplement",
            "groceries",
        ),
        (r"toy|lego|game|puzzle|doll|action figure", "entertainment"),
        (r"cleaning|soap|detergent|shampoo|toothpaste|tissue", "home"),
        (r"medicine|pharmacy|health|first aid|bandage", "health"),
        (r"kitchen|cooking|pan|pot|utensil|plate|bowl|cup", "home"),
        (r"uber|lyft|taxi|ride|trip", "transport"),
        (r"deliveroo|uber eats|just eat|delivery", "food_delivery"),
        (r"subscription|monthly|annual|premium|membership", "subscription"),
        (r"netflix|spotify|disney|streaming", "subscription"),
    ]

    for pattern, category in category_patterns:
        if re.search(pattern, name_lower):
            return category

    return "other"
