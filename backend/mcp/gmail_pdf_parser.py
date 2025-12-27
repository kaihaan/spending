"""
Gmail PDF Receipt Parser

Parses PDF attachments from receipt emails to extract transaction details.
Supports:
- Charles Tyrwhitt e-receipts
- Google Cloud invoices
- Generic receipt PDFs
"""

import io
import re

try:
    import pdfplumber

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("⚠️ pdfplumber not installed - PDF parsing disabled")


def extract_text_from_pdf(pdf_bytes: bytes) -> str | None:
    """
    Extract text content from a PDF file.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Extracted text or None if extraction fails
    """
    if not PDF_SUPPORT:
        return None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_parts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
    except Exception as e:
        print(f"❌ PDF extraction error: {e}")
        return None


def parse_amount(text: str) -> float | None:
    """Extract numeric amount from text like '£12.34' or '12.34'."""
    if not text:
        return None
    cleaned = re.sub(r"[£$€¥\s,]", "", text)
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def parse_date_text(text: str) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    if not text:
        return None

    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    # 15 January 2024 or 15 Jan 2024
    match = re.search(
        r"(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        day = int(match.group(1))
        month = months.get(match.group(2).lower()[:3], 1)
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # DD/MM/YYYY
    match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    return None


# ============================================================================
# CHARLES TYRWHITT PDF PARSER
# ============================================================================


def parse_charles_tyrwhitt_pdf(pdf_bytes: bytes) -> dict | None:
    """
    Parse Charles Tyrwhitt e-receipt PDF.

    Extracts:
    - Order reference
    - Items purchased (product, size, price)
    - Subtotal, discounts, delivery, VAT
    - Total amount
    - Payment method

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        Parsed receipt dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "merchant_name": "Charles Tyrwhitt",
        "merchant_name_normalized": "charles_tyrwhitt",
        "parse_method": "vendor_charles_tyrwhitt_pdf",
        "parse_confidence": 90,
        "category_hint": "clothing",
        "currency_code": "GBP",
    }

    # Extract order reference
    ref_match = re.search(r"(?:Order|Reference)[:\s#]*([A-Z0-9]+)", text, re.IGNORECASE)
    if ref_match:
        result["order_id"] = ref_match.group(1)

    # Extract receipt date
    date_match = re.search(
        r"(?:Date|Receipt Date)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+\w+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Extract total amount (look for "Total" or "Grand Total")
    total_patterns = [
        r"(?:Grand\s+)?Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"(?:Grand\s+)?Total\s+(?:GBP\s+)?£?\s*([0-9,]+\.?\d*)",
        r"Amount\s+(?:Paid|Due)[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract VAT
    vat_match = re.search(r"VAT[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract subtotal
    subtotal_match = re.search(
        r"Sub\s*-?\s*total[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if subtotal_match:
        result["subtotal"] = parse_amount(subtotal_match.group(1))

    # Extract delivery cost
    delivery_match = re.search(
        r"(?:Delivery|Shipping)[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if delivery_match:
        result["delivery_amount"] = parse_amount(delivery_match.group(1))

    # Extract line items (product lines with prices)
    line_items = []
    # Pattern: Product description followed by quantity and price
    item_pattern = r"([A-Za-z][A-Za-z\s\-]+?)\s+(\d+)\s+£([0-9,]+\.?\d*)"
    for match in re.finditer(item_pattern, text):
        item_name = match.group(1).strip()
        quantity = int(match.group(2))
        price = parse_amount(match.group(3))
        if item_name and price:
            line_items.append(
                {
                    "name": item_name,
                    "quantity": quantity,
                    "price": price,
                    "category_hint": "clothing",
                }
            )

    if line_items:
        result["line_items"] = line_items

    # Validate: must have at least amount or order ID
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# GOOGLE CLOUD PDF PARSER
# ============================================================================


def parse_google_cloud_pdf(pdf_bytes: bytes) -> dict | None:
    """
    Parse Google Cloud invoice PDF.

    Extracts:
    - Invoice number
    - Billing period
    - Total amount
    - VAT/Tax

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        Parsed invoice dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "merchant_name": "Google Cloud",
        "merchant_name_normalized": "google_cloud",
        "parse_method": "vendor_google_cloud_pdf",
        "parse_confidence": 90,
        "category_hint": "software_subscription",
    }

    # Extract invoice number - must be "Invoice number:" to avoid matching address
    invoice_match = re.search(r"Invoice\s+number[:\s]+(\d+)", text, re.IGNORECASE)
    if invoice_match:
        result["order_id"] = invoice_match.group(1)

    # Extract billing period
    period_match = re.search(
        r"(?:Billing Period|Service Period|Summary for)[:\s]*(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if period_match:
        result["billing_period"] = period_match.group(1).strip()

    # Extract invoice date - handle "30 Nov 2024" format
    date_match = re.search(
        r"Invoice\s+date[:\s]*(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Extract currency
    if "£" in text or "GBP" in text:
        result["currency_code"] = "GBP"
    elif "€" in text or "EUR" in text:
        result["currency_code"] = "EUR"
    elif "$" in text or "USD" in text:
        result["currency_code"] = "USD"

    # Extract total amount - handle "Total in GBP £0.00" format
    total_patterns = [
        r"Total\s+in\s+(?:GBP|USD|EUR)\s*[£$€]\s*([0-9,]+\.?\d*)",  # "Total in GBP £0.00"
        r"(?:Total|Amount\s+Due)[:\s]*[£$€]\s*([0-9,]+\.?\d*)",  # "Total: £0.00"
        r"(?:Total|Amount\s+Due)[:\s]*([0-9,]+\.?\d*)\s*(?:GBP|USD|EUR)",  # "Total: 0.00 GBP"
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract VAT/Tax
    vat_match = re.search(
        r"(?:VAT|Tax)[:\s]*[£$€]\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract line items - Google Cloud services
    line_items = []

    # Common Google Cloud service patterns with amounts
    # Pattern: "Service Name    $amount" or "Service Name    amount USD"
    service_patterns = [
        # Direct service name patterns
        r"(Compute Engine|Cloud Storage|Cloud SQL|BigQuery|Cloud Functions|Cloud Run|"
        r"Kubernetes Engine|Cloud Pub/Sub|Cloud Vision|Cloud AI|Cloud DNS|"
        r"Cloud CDN|Cloud Armor|Cloud Load Balancing|App Engine|Cloud Build|"
        r"Cloud Logging|Cloud Monitoring|Cloud Dataflow|Cloud Spanner|Firestore|"
        r"Cloud Memorystore|Cloud NAT|VPN|Networking|APIs?|Maps Platform|"
        r"Cloud Identity|Workspace|Support)[:\s]*(?:\$|USD)?\s*([0-9,]+\.?\d*)",
        # SKU description pattern: "Description ... $amount"
        r"([A-Z][A-Za-z\s\-\/]+(?:Instance|Storage|Egress|Ingress|API|Request|Query|Hour|GB)s?)[:\s]+\$?\s*([0-9,]+\.?\d*)",
    ]

    seen_services = set()
    for pattern in service_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            service_name = match.group(1).strip()
            # Normalize and deduplicate
            service_key = service_name.lower()
            if service_key not in seen_services and len(service_name) > 3:
                seen_services.add(service_key)
                amount = parse_amount(match.group(2)) if match.group(2) else None
                item = {"name": service_name}
                if amount and amount > 0:
                    item["price"] = amount
                line_items.append(item)

    # If no specific services found, create a generic entry from billing period
    if not line_items and result.get("billing_period"):
        line_items.append(
            {"name": f"Google Cloud services ({result['billing_period']})"}
        )
    elif not line_items:
        line_items.append({"name": "Google Cloud Platform services"})

    result["line_items"] = line_items

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# XERO INVOICE PDF PARSER
# ============================================================================


def parse_xero_invoice_pdf(pdf_bytes: bytes) -> dict | None:
    """
    Parse Xero invoice PDF.

    Xero invoices typically have:
    - Company name at the top (from sender, e.g., "From WOOD-CONSTRUCTION LTD")
    - Invoice number (INV-XXXX)
    - Date
    - Subtotal, VAT, then Total amount with currency

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        Parsed invoice dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "parse_method": "vendor_xero_pdf",
        "parse_confidence": 85,
        "category_hint": "services",
    }

    # Extract merchant name - look for "From <COMPANY>" or company name pattern
    # Xero invoices often have the company name in format: "From COMPANY LTD"
    from_match = re.search(
        r"From\s+([A-Z][A-Z\s&\-\.]+(?:LTD|LIMITED|PLC|INC|LLC)?)", text, re.IGNORECASE
    )
    if from_match:
        company = from_match.group(1).strip()
        result["merchant_name"] = company
        result["merchant_name_normalized"] = re.sub(
            r"[^a-z0-9]+", "_", company.lower()
        ).strip("_")
    else:
        # Try to find company name from invoice header (often appears after "TAX INVOICE")
        # Look for all-caps company name followed by LTD/LIMITED
        company_match = re.search(r"([A-Z][A-Z\s\-]+(?:LTD|LIMITED))", text)
        if company_match:
            company = company_match.group(1).strip()
            result["merchant_name"] = company
            result["merchant_name_normalized"] = re.sub(
                r"[^a-z0-9]+", "_", company.lower()
            ).strip("_")

    # Extract invoice number (INV-XXXX is common Xero format)
    invoice_match = re.search(r"(INV-\d+)", text)
    if invoice_match:
        result["order_id"] = invoice_match.group(1)
    else:
        # Fallback patterns
        for pattern in [
            r"Invoice\s*#?\s*([A-Z0-9\-]+)",
            r"Reference[:\s]*([A-Z0-9\-]+)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["order_id"] = match.group(1)
                break

    # Extract date
    date_match = re.search(
        r"(?:Invoice Date|Date)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+\w+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Detect currency
    if "£" in text or "GBP" in text:
        result["currency_code"] = "GBP"
    elif "€" in text or "EUR" in text:
        result["currency_code"] = "EUR"
    elif "$" in text or "USD" in text:
        result["currency_code"] = "USD"
    else:
        result["currency_code"] = "GBP"  # Default for UK

    # Extract subtotal first
    subtotal_match = re.search(
        r"Sub\s*-?\s*total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if subtotal_match:
        result["subtotal"] = parse_amount(subtotal_match.group(1))

    # Extract VAT/Tax
    vat_match = re.search(
        r"(?:VAT|Tax)\s*(?:\d+%)?[:\s]*[£$€]?\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract total amount - Xero shows "Total <CURRENCY> <amount>" at the end
    # Find ALL "Total" matches and take the LAST one (most likely the grand total after VAT)
    total_amounts = []

    # Pattern 1: "Total GBP 180.00" format (common in Xero)
    for match in re.finditer(
        r"Total\s+(?:GBP|USD|EUR)\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    ):
        amount = parse_amount(match.group(1))
        if amount and amount > 0:
            total_amounts.append(amount)

    # Pattern 2: "Total £180.00" format
    if not total_amounts:
        for match in re.finditer(
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
        ):
            amount = parse_amount(match.group(1))
            if amount and amount > 0:
                total_amounts.append(amount)

    # Pattern 3: "Amount Due" or "Balance Due"
    if not total_amounts:
        for match in re.finditer(
            r"(?:Amount\s+Due|Balance\s+Due)[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
            text,
            re.IGNORECASE,
        ):
            amount = parse_amount(match.group(1))
            if amount and amount > 0:
                total_amounts.append(amount)

    # Take the largest total found (should be the grand total including VAT)
    if total_amounts:
        result["total_amount"] = max(total_amounts)
    elif result.get("subtotal") and result.get("vat_amount"):
        # Calculate total if we have subtotal and VAT
        result["total_amount"] = result["subtotal"] + result["vat_amount"]

    # Extract line items from Xero invoice
    # Xero invoices typically have line items in a table format:
    # Description | Quantity | Unit Price | Amount
    line_items = []

    # Pattern 1: Look for description followed by quantity and amounts
    # Common format: "Service description   1.00   150.00   150.00"
    item_pattern = r"([A-Za-z][A-Za-z\s\-\.\,\/\(\)]+?)\s+(\d+(?:\.\d+)?)\s+[\d,]+\.?\d*\s+([0-9,]+\.?\d*)"
    for match in re.finditer(item_pattern, text):
        description = match.group(1).strip()
        # Filter out headers and summary rows
        skip_keywords = [
            "subtotal",
            "total",
            "vat",
            "tax",
            "discount",
            "description",
            "quantity",
            "unit price",
            "amount",
            "due date",
            "invoice",
        ]
        if any(kw in description.lower() for kw in skip_keywords):
            continue
        if len(description) > 5 and len(description) < 200:
            quantity = float(match.group(2)) if match.group(2) else 1
            amount = parse_amount(match.group(3))
            item = {"name": description}
            if quantity and quantity != 1:
                item["quantity"] = (
                    int(quantity) if quantity == int(quantity) else quantity
                )
            if amount and amount > 0:
                item["price"] = amount
            line_items.append(item)

    # Pattern 2: Simple description lines that look like services
    if not line_items:
        # Look for service-type descriptions
        service_patterns = [
            r"(?:^|\n)([A-Za-z][A-Za-z\s\-]+(?:work|service|labour|labor|consultation|"
            r"installation|repair|maintenance|fee|charge|support)s?)",
        ]
        for pattern in service_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                service = match.group(1).strip()
                if len(service) > 5 and len(service) < 100:
                    if service.lower() not in ["subtotal", "total", "vat", "tax"]:
                        line_items.append({"name": service})

    # If still no items and we have a merchant name, use that
    if not line_items and result.get("merchant_name"):
        line_items.append({"name": f"Invoice from {result['merchant_name']}"})
    elif not line_items:
        line_items.append({"name": "Professional services"})

    result["line_items"] = line_items

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# ATLASSIAN INVOICE PDF PARSER
# ============================================================================


def parse_atlassian_invoice_pdf(pdf_bytes: bytes) -> dict | None:
    """
    Parse Atlassian invoice PDF.

    Atlassian invoices typically have:
    - Invoice number (IN-XXX-XXX-XXX format)
    - Product descriptions (Jira, Confluence, etc.)
    - Total amount with currency (USD typically)

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        Parsed invoice dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "merchant_name": "Atlassian",
        "merchant_name_normalized": "atlassian",
        "parse_method": "vendor_atlassian_pdf",
        "parse_confidence": 90,
        "category_hint": "software",
    }

    # Extract invoice number (IN-XXX-XXX-XXX format)
    invoice_match = re.search(r"(IN-\d{3}-\d{3}-\d{3})", text)
    if invoice_match:
        result["order_id"] = invoice_match.group(1)
    else:
        # Fallback patterns
        for pattern in [
            r"Invoice\s*#?\s*:?\s*([A-Z0-9\-]+)",
            r"Invoice Number[:\s]*([A-Z0-9\-]+)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["order_id"] = match.group(1)
                break

    # Extract total amount - Atlassian uses USD
    # Pattern: "Total Amount Due" or "Total:" followed by amount
    total_patterns = [
        r"Total Amount Due[:\s]*\$?\s*([0-9,]+\.?\d*)",
        r"Total Due[:\s]*\$?\s*([0-9,]+\.?\d*)",
        r"Amount Due[:\s]*\$?\s*([0-9,]+\.?\d*)",
        r"Total[:\s]*\$?\s*([0-9,]+\.?\d*)\s*USD",
        r"Total[:\s]*USD\s*\$?\s*([0-9,]+\.?\d*)",
    ]

    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                result["total_amount"] = float(amount_str)
                result["currency_code"] = "USD"
                break
            except ValueError:
                continue

    # Extract line items - Atlassian products
    line_items = []

    # Atlassian product patterns
    # Products: Jira, Confluence, Bitbucket, Trello, Opsgenie, Statuspage, Jira Service Management
    product_patterns = [
        # Direct product name matches with optional tier/user count
        r"(Jira\s*(?:Software|Core|Work Management)?|Confluence|Bitbucket|Trello|"
        r"Opsgenie|Statuspage|Jira Service (?:Management|Desk)|Atlas|Compass|"
        r"Guard|Access|Beacon)(?:\s*(?:Standard|Premium|Enterprise|Free))?"
        r"(?:\s*[–\-]\s*(\d+)\s*(?:users?|agents?|seats?))?",
        # Line item pattern: "Product Name ... $amount"
        r"(Jira[A-Za-z\s]*|Confluence[A-Za-z\s]*|Bitbucket[A-Za-z\s]*|"
        r"Trello[A-Za-z\s]*|Cloud[A-Za-z\s]+)[:\s]+\$?\s*([0-9,]+\.?\d*)",
    ]

    seen_products = set()
    for pattern in product_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            product_name = match.group(1).strip()
            product_key = product_name.lower()

            if product_key not in seen_products and len(product_name) > 3:
                seen_products.add(product_key)
                item = {"name": product_name}

                # Check for user count in group 2 if available
                if len(match.groups()) > 1 and match.group(2):
                    try:
                        user_count = int(match.group(2))
                        item["quantity"] = user_count
                    except ValueError:
                        # Might be a price instead of user count
                        price = parse_amount(match.group(2))
                        if price and price > 0:
                            item["price"] = price

                line_items.append(item)

    # If no specific products found, add generic Atlassian subscription
    if not line_items:
        line_items.append({"name": "Atlassian Cloud subscription"})

    result["line_items"] = line_items

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# GENERIC PDF PARSER
# ============================================================================


def parse_generic_receipt_pdf(
    pdf_bytes: bytes, merchant_hint: str = None
) -> dict | None:
    """
    Generic receipt PDF parser for unknown formats.

    Attempts to extract common receipt fields using pattern matching.

    Args:
        pdf_bytes: Raw PDF content
        merchant_hint: Optional merchant name hint

    Returns:
        Parsed receipt dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "parse_method": "generic_pdf",
        "parse_confidence": 70,
    }

    if merchant_hint:
        result["merchant_name"] = merchant_hint
        result["merchant_name_normalized"] = merchant_hint.lower().replace(" ", "_")

    # Try to extract order/invoice/reference number
    id_patterns = [
        r"(?:Order|Invoice|Reference|Receipt|Confirmation)\s*(?:#|Number|ID|No\.?)?[:\s]*([A-Z0-9\-]+)",
    ]
    for pattern in id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["order_id"] = match.group(1)
            break

    # Extract date
    result["receipt_date"] = parse_date_text(text)

    # Detect currency
    if "£" in text:
        result["currency_code"] = "GBP"
    elif "€" in text:
        result["currency_code"] = "EUR"
    elif "$" in text:
        result["currency_code"] = "USD"

    # Extract total amount (common patterns)
    total_patterns = [
        r"(?:Grand\s+)?Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"Amount\s+(?:Paid|Due|Charged)[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"(?:You\s+paid|Payment)[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract VAT
    vat_match = re.search(r"VAT[:\s]*[£$€]\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract line items - generic approach
    line_items = []

    # Pattern 1: Item with quantity and price (table format)
    # "Product Name   2   £10.00   £20.00"
    item_pattern = r"([A-Za-z][A-Za-z0-9\s\-\.\,\(\)\'\"]+?)\s+(\d+)\s+[£$€]?\s*[\d,]+\.?\d*\s+[£$€]?\s*([0-9,]+\.?\d*)"
    for match in re.finditer(item_pattern, text):
        item_name = match.group(1).strip()
        # Filter out common non-item rows
        skip_terms = [
            "total",
            "subtotal",
            "vat",
            "tax",
            "discount",
            "shipping",
            "delivery",
            "qty",
            "quantity",
            "price",
            "amount",
            "description",
        ]
        if any(term in item_name.lower() for term in skip_terms):
            continue
        if len(item_name) > 3 and len(item_name) < 150:
            quantity = int(match.group(2))
            price = parse_amount(match.group(3))
            item = {"name": item_name}
            if quantity and quantity > 1:
                item["quantity"] = quantity
            if price and price > 0:
                item["price"] = price
            line_items.append(item)

    # Pattern 2: Item with just a price (simpler format)
    # "Product Name   £10.00"
    if not line_items:
        simple_pattern = r"([A-Za-z][A-Za-z0-9\s\-\.\,]+?)\s+[£$€]\s*([0-9,]+\.?\d*)"
        for match in re.finditer(simple_pattern, text):
            item_name = match.group(1).strip()
            skip_terms = [
                "total",
                "subtotal",
                "vat",
                "tax",
                "discount",
                "shipping",
                "delivery",
                "amount",
                "price",
                "date",
                "invoice",
                "receipt",
            ]
            if any(term in item_name.lower() for term in skip_terms):
                continue
            if len(item_name) > 3 and len(item_name) < 100:
                price = parse_amount(match.group(2))
                if price and price > 0:
                    line_items.append({"name": item_name, "price": price})
                    if len(line_items) >= 10:  # Limit to avoid noise
                        break

    # Pattern 3: Look for product/item keywords
    if not line_items:
        product_pattern = (
            r"(?:product|item|service|description)[:\s]*([A-Za-z][A-Za-z0-9\s\-\.\,]+)"
        )
        for match in re.finditer(product_pattern, text, re.IGNORECASE):
            item_name = match.group(1).strip()
            if len(item_name) > 3 and len(item_name) < 100:
                line_items.append({"name": item_name})
                if len(line_items) >= 5:
                    break

    # If still no items, create a generic entry
    if not line_items and merchant_hint:
        line_items.append({"name": f"Purchase from {merchant_hint}"})
    elif not line_items:
        line_items.append({"name": "Receipt items"})

    result["line_items"] = line_items

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# SUFFOLK LATCH COMPANY PDF PARSER (Sage Invoice)
# ============================================================================


def parse_suffolk_latch_pdf(pdf_bytes: bytes) -> dict | None:
    """
    Parse Suffolk Latch Company invoice PDF (Sage format).

    Extracts:
    - Invoice number
    - Invoice date
    - Line items (product descriptions with quantities and prices)
    - Subtotal, VAT, Total

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        Parsed invoice dict or None
    """
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        return None

    result = {
        "merchant_name": "Suffolk Latch Company",
        "merchant_name_normalized": "suffolk_latch_company",
        "parse_method": "vendor_suffolk_latch_pdf",
        "parse_confidence": 90,
        "category_hint": "home_hardware",
        "currency_code": "GBP",
    }

    # Extract invoice number from subject or body
    # Pattern: "Invoice No. 407775" or "Invoice Number: 407775"
    invoice_match = re.search(
        r"Invoice\s*(?:No\.?|Number)[:\s]*(\d+)", text, re.IGNORECASE
    )
    if invoice_match:
        result["order_id"] = invoice_match.group(1)

    # Extract invoice date
    # Patterns: "Invoice Date: 15/01/2024" or "Date: 15 Jan 2024"
    date_match = re.search(
        r"(?:Invoice\s+)?Date[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Extract line items - Sage invoice table format
    # Typical format: Description | Quantity | Unit Price | VAT | Amount
    line_items = []

    # Pattern 1: Product code followed by description and amounts
    # e.g., "SKU123 Iron Door Handle 2 15.99 3.20 35.18"
    item_patterns = [
        # Product with code: "CODE Description Qty UnitPrice VAT Total"
        r"([A-Z0-9\-]+)\s+([A-Za-z][A-Za-z0-9\s\-\.\,\/\(\)]+?)\s+(\d+(?:\.\d+)?)\s+(\d+\.\d{2})\s+(?:\d+\.\d{2}\s+)?(\d+\.\d{2})",
        # Simple description with amounts: "Description Qty UnitPrice Total"
        r"([A-Za-z][A-Za-z0-9\s\-\.\,\/\(\)]{10,60}?)\s+(\d+)\s+(\d+\.\d{2})\s+(\d+\.\d{2})",
    ]

    seen_items = set()
    for pattern in item_patterns:
        for match in re.finditer(pattern, text):
            groups = match.groups()

            if len(groups) == 5:
                # Pattern with product code
                product_code = groups[0].strip()
                description = groups[1].strip()
                quantity = float(groups[2])
                unit_price = float(groups[3])
                total_price = float(groups[4])
                full_name = (
                    f"{description} ({product_code})" if product_code else description
                )
            else:
                # Simple pattern
                description = groups[0].strip()
                quantity = float(groups[1])
                unit_price = float(groups[2])
                total_price = float(groups[3])
                full_name = description

            # Skip header rows and summary rows
            skip_terms = [
                "description",
                "quantity",
                "unit price",
                "amount",
                "subtotal",
                "total",
                "vat",
                "carriage",
                "delivery",
                "postage",
            ]
            if any(term in description.lower() for term in skip_terms):
                continue

            # Deduplicate
            item_key = f"{description.lower()[:30]}_{total_price}"
            if item_key in seen_items:
                continue
            seen_items.add(item_key)

            if len(description) > 3:
                item = {"name": full_name}
                if quantity and quantity > 1:
                    item["quantity"] = (
                        int(quantity) if quantity == int(quantity) else quantity
                    )
                if total_price and total_price > 0:
                    item["price"] = total_price
                line_items.append(item)

    # Pattern 2: Look for hardware/ironmongery specific items
    if not line_items:
        hardware_pattern = r"([A-Za-z][A-Za-z\s\-]+(?:Handle|Latch|Lock|Hinge|Bolt|Knob|Hook|Pull|Plate|Ring|Escutcheon|Knocker|Letter|Bell)[A-Za-z\s\-]*)"
        for match in re.finditer(hardware_pattern, text, re.IGNORECASE):
            item_name = match.group(1).strip()
            if len(item_name) > 5 and len(item_name) < 80:
                if item_name.lower() not in seen_items:
                    seen_items.add(item_name.lower())
                    line_items.append({"name": item_name})

    # If no items found, use generic entry
    if not line_items:
        line_items.append({"name": "Ironmongery & door hardware"})

    result["line_items"] = line_items

    # Extract totals
    # Subtotal pattern
    subtotal_match = re.search(
        r"Sub\s*-?\s*total[:\s]*£?\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if subtotal_match:
        result["subtotal"] = parse_amount(subtotal_match.group(1))

    # VAT pattern
    vat_match = re.search(r"VAT[:\s]*£?\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Total/Grand Total pattern - find the largest "Total" value
    total_amounts = []
    for match in re.finditer(
        r"(?:Grand\s+)?Total[:\s]*£?\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    ):
        amount = parse_amount(match.group(1))
        if amount and amount > 0:
            total_amounts.append(amount)

    if total_amounts:
        result["total_amount"] = max(total_amounts)
    elif result.get("subtotal") and result.get("vat_amount"):
        result["total_amount"] = result["subtotal"] + result["vat_amount"]

    # Validate
    if result.get("total_amount") or result.get("order_id") or line_items:
        return result

    return None


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def parse_receipt_pdf(
    pdf_bytes: bytes, sender_domain: str = None, filename: str = None
) -> dict | None:
    """
    Parse a receipt PDF attachment.

    Routes to vendor-specific parser if domain is recognized,
    otherwise uses generic parser.

    Args:
        pdf_bytes: Raw PDF content
        sender_domain: Email sender domain for routing
        filename: PDF filename for hints

    Returns:
        Parsed receipt dict or None
    """
    if not PDF_SUPPORT:
        print("⚠️ PDF parsing not available - pdfplumber not installed")
        return None

    if not pdf_bytes:
        return None

    sender_domain = (sender_domain or "").lower()

    # Route to vendor-specific parser
    if "ctshirts" in sender_domain:
        return parse_charles_tyrwhitt_pdf(pdf_bytes)

    if "google" in sender_domain:
        return parse_google_cloud_pdf(pdf_bytes)

    if "xero" in sender_domain:
        return parse_xero_invoice_pdf(pdf_bytes)

    if "atlassian" in sender_domain:
        return parse_atlassian_invoice_pdf(pdf_bytes)

    if "suffolklatch" in sender_domain:
        return parse_suffolk_latch_pdf(pdf_bytes)

    # Fallback to generic parser
    return parse_generic_receipt_pdf(pdf_bytes)
