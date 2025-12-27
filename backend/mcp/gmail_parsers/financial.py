"""
Financial Services Parsers

PayPal and payment processors
"""

import re

from bs4 import BeautifulSoup

from .base import parse_amount, parse_date_text, register_vendor


@register_vendor(["paypal.co.uk", "paypal.com", "mail.paypal.co.uk"])
def parse_paypal_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse PayPal payment receipts.

    PayPal receipts have:
    - Transaction ID (alphanumeric, 10-17 chars)
    - Merchant/seller name (from subject or body)
    - Amount sent/received
    - Currency (GBP, USD, EUR)
    - Date of transaction
    """
    result = {
        "parse_method": "vendor_paypal",
        "parse_confidence": 85,
        "merchant_name": "PayPal",
        "merchant_name_normalized": "paypal",
    }

    # Try to extract merchant from subject first
    # "Receipt for your payment to JustHost - Bluehost"
    # "Receipt for Your Payment to Microsoft Payments"
    subject_merchant_match = re.search(
        r"(?:payment to|receipt for your payment to)\s+([A-Za-z0-9\s\-&\'\.]+)",
        subject,
        re.IGNORECASE,
    )
    if subject_merchant_match:
        merchant = subject_merchant_match.group(1).strip()
        if 2 < len(merchant) < 50:
            result["payee_name"] = merchant
            result["merchant_name_normalized"] = (
                merchant.lower().replace(" ", "_").replace("-", "_")
            )

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract transaction ID (alphanumeric, 10-17 chars)
        tx_match = re.search(
            r"Transaction\s*ID[:\s]*([A-Z0-9]{10,17})", text, re.IGNORECASE
        )
        if tx_match:
            result["order_id"] = tx_match.group(1)

        # Extract merchant from body if not found in subject
        if "payee_name" not in result:
            merchant_patterns = [
                r"Payment to[:\s]+([A-Za-z0-9\s\-&\'\.]+?)(?:\s*Transaction|\s*Amount|\s*£|\s*\$|\s*€)",
                r"Paid to[:\s]+([A-Za-z0-9\s\-&\'\.]+)",
                r"Sent to[:\s]+([A-Za-z0-9\s\-&\'\.]+)",
            ]
            for pattern in merchant_patterns:
                match = re.search(pattern, text)
                if match:
                    merchant = match.group(1).strip()
                    if 2 < len(merchant) < 50:
                        result["payee_name"] = merchant
                        result["merchant_name_normalized"] = (
                            merchant.lower().replace(" ", "_").replace("-", "_")
                        )
                        break

        # Extract total amount
        amount_patterns = [
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"You (?:sent|paid)[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Amount[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Payment[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Currency detection
        if "£" in text or "GBP" in text:
            result["currency_code"] = "GBP"
        elif "€" in text or "EUR" in text:
            result["currency_code"] = "EUR"
        elif "$" in text or "USD" in text:
            result["currency_code"] = "USD"

        # Date extraction - multiple formats
        date_patterns = [
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
            r"(?:Date|Transaction date)[:\s]*([\d]+\s+\w+\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["receipt_date"] = parse_date_text(match.group(1))
                break

    # Set line_items with payee information
    if result.get("payee_name"):
        result["line_items"] = [
            {
                "name": f"Payment to {result['payee_name']}",
                "merchant": result["payee_name"],
                "payment_method": "PayPal",
            }
        ]
    else:
        result["line_items"] = [
            {
                "name": "PayPal payment",
                "merchant": "Unknown",
                "payment_method": "PayPal",
            }
        ]

    # Validate - must have at least amount or transaction ID
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# UBER PARSER
# ============================================================================
