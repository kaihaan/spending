"""
Ride-sharing Parsers

Uber, Lyft, Lime
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


@register_vendor(['uber.com', 'ubereats.com'])
def parse_uber_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Uber ride receipts and Uber Eats order receipts.

    Routes based on email type:
    - ride: Uber transportation receipts (category: transport)
    - eats: Uber Eats food delivery receipts (category: food_delivery)

    Extracts: total amount, currency, date, time
    """
    email_type = detect_uber_email_type(subject, html_body)

    # Set merchant based on type
    if email_type == 'eats':
        result = {
            'merchant_name': 'Uber Eats',
            'merchant_name_normalized': 'uber_eats',
            'category_hint': 'food_delivery',
            'email_type': 'eats',
        }
    else:
        result = {
            'merchant_name': 'Uber',
            'merchant_name_normalized': 'uber',
            'category_hint': 'transport',
            'email_type': 'ride',
        }

    result['parse_method'] = 'vendor_uber'
    result['parse_confidence'] = 85

    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

        # Extract total - Uber uses specific patterns
        total_patterns = [
            r'Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'You paid[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'Amount charged[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'[£$€]([0-9,]+\.[0-9]{2})',  # Fallback: any currency amount
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['total_amount'] = parse_amount(match.group(1))
                break

        # Infer currency from text
        if '£' in text:
            result['currency_code'] = 'GBP'
        elif '€' in text:
            result['currency_code'] = 'EUR'
        elif '$' in text:
            result['currency_code'] = 'USD'

        # Extract date - multiple formats
        date_patterns = [
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})',
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['receipt_date'] = parse_date_text(match.group(1))
                break

        # Extract time if available
        time_match = re.search(r'(\d{1,2}:\d{2})\s*(?:am|pm)?', text, re.IGNORECASE)
        if time_match:
            result['trip_time'] = time_match.group(1)

        # Extract line items based on type
        if email_type == 'eats':
            # Try to extract restaurant name for Uber Eats
            restaurant_patterns = [
                r'(?:Your order from|Order from)\s+([A-Za-z0-9\s&\'\-]+?)(?:\s*is|\s*has|\n)',
                r'Restaurant[:\s]+([A-Za-z0-9\s&\'\-]+?)(?:\n|\s{2,})',
                r'Thanks for ordering from\s+([A-Za-z0-9\s&\'\-]+)',
            ]
            for pattern in restaurant_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    restaurant = match.group(1).strip()
                    if len(restaurant) > 2 and len(restaurant) < 100:
                        result['restaurant_name'] = restaurant
                        result['line_items'] = [{
                            'name': f"Order from {restaurant}",
                            'restaurant': restaurant,
                            'brand': restaurant  # Restaurant is the brand for food delivery
                        }]
                        break
            # Fallback: just note it's a food order
            if 'line_items' not in result:
                result['line_items'] = [{
                    'name': 'Uber Eats order',
                    'restaurant': 'Unknown',
                    'brand': 'Uber Eats'  # Service brand when restaurant unknown
                }]
        else:
            # For rides, create a trip description
            trip_desc_parts = []
            if result.get('receipt_date'):
                trip_desc_parts.append(result['receipt_date'])
            if result.get('trip_time'):
                trip_desc_parts.append(result['trip_time'])

            if trip_desc_parts:
                result['line_items'] = [{
                    'name': f"Uber ride ({', '.join(trip_desc_parts)})",
                    'brand': 'Uber'  # Service brand
                }]
            else:
                result['line_items'] = [{
                    'name': 'Uber ride',
                    'brand': 'Uber'  # Service brand
                }]

    if result.get('total_amount'):
        return result

    return None


# ============================================================================
# LYFT PARSER
# ============================================================================



@register_vendor(['lyftmail.com'])
def parse_lyft_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Lyft ride receipts.

    Lyft emails have:
    - Subject: "Your receipt for rides on [Month Day]"
    - Trip date, pickup/dropoff locations
    - Fare breakdown and total amount
    """
    result = {
        'merchant_name': 'Lyft',
        'merchant_name_normalized': 'lyft',
        'parse_method': 'vendor_lyft',
        'parse_confidence': 85,
    }

    # Extract date from subject (e.g., "Your receipt for rides on December 12")
    subject_date_match = re.search(
        r'(?:on|from)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})',
        subject,
        re.IGNORECASE
    )

    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

        # Extract total amount - Lyft uses various patterns
        total_patterns = [
            r'Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'You paid[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'Charged[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'[£$€]\s*([0-9,]+\.[0-9]{2})\s*(?:total|charged)',
            # Lyft sometimes just shows the amount
            r'Total\s+\$([0-9,]+\.[0-9]{2})',
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['total_amount'] = parse_amount(match.group(1))
                break

        # Try to find full date in body (with year)
        full_date = parse_date_text(text)
        if full_date:
            result['receipt_date'] = full_date
        elif subject_date_match:
            # Use subject date with current year (will be refined by received_at fallback)
            months = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            month = months.get(subject_date_match.group(1).lower())
            day = int(subject_date_match.group(2))
            if month and day:
                # Use current year - matching will use received_at as fallback
                year = datetime.now().year
                result['receipt_date'] = f"{year:04d}-{month:02d}-{day:02d}"

        # Extract trip details if available
        trip_match = re.search(r'(?:from|pickup)[:\s]*([^,\n]+)', text, re.IGNORECASE)
        if trip_match:
            result['line_items'] = [f"Lyft ride: {trip_match.group(1).strip()[:50]}"]

    # Validate - must have amount or we can't match
    if result.get('total_amount'):
        return result

    # Even without amount, return if we have valid Lyft email structure
    if subject_date_match:
        return result

    return None


# ============================================================================
# DELIVEROO PARSER
# ============================================================================



@register_vendor(['li.me'])
def parse_lime_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Lime scooter receipt/refund emails.

    Email format:
    - Subject: "Receipt for your refund" or "Receipt For Your Refund"
    - Date of issue: DD Mon YYYY
    - Distance, ride times
    - Fee breakdown (Start Fee, Riding, Subtotal, VAT)
    - Refund amount (negative) or charge amount
    """
    is_refund = 'refund' in subject.lower()

    result = {
        'merchant_name': 'Lime',
        'merchant_name_normalized': 'lime',
        'merchant_domain': 'li.me',
        'parse_method': 'vendor_lime',
        'parse_confidence': 85,
        'category_hint': 'transport_scooter',
        'currency_code': 'GBP',
    }

    if not html_body:
        return None

    soup = BeautifulSoup(html_body, 'html.parser')
    text = soup.get_text(separator='\n')

    # Extract date - "Date of issue: 07 Sep 2024"
    date_match = re.search(r'Date of issue:\s*(\d{1,2})\s+(\w{3})\s+(\d{4})', text, re.IGNORECASE)
    if date_match:
        day = int(date_match.group(1))
        month_abbr = date_match.group(2)
        year = int(date_match.group(3))
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        month = months.get(month_abbr.lower(), 1)
        result['receipt_date'] = f"{year:04d}-{month:02d}-{day:02d}"

    # Find refund or total amount
    # Refund pattern: "Refunded to Apple Pay -£6.22"
    # Or total pattern near end
    if is_refund:
        refund_match = re.search(r'Refunded\s+(?:to\s+\w+\s+\w+\s+)?-?£([\d,]+\.?\d*)', text, re.IGNORECASE)
        if refund_match:
            # Store as negative for refunds
            result['total_amount'] = -parse_amount(refund_match.group(1))
    else:
        # Look for total/charged amount
        total_match = re.search(r'(?:Total|Charged)\s*[\n\s]*£([\d,]+\.?\d*)', text, re.IGNORECASE)
        if total_match:
            result['total_amount'] = parse_amount(total_match.group(1))

    # Extract ride description
    distance_match = re.search(r'([\d.]+)\s*mi\s+distance', text, re.IGNORECASE)
    time_match = re.search(r'(\d+:\d+\s*[AP]\.?M\.?)\s*-\s*(\d+:\d+\s*[AP]\.?M\.?)', text, re.IGNORECASE)

    if distance_match:
        distance = distance_match.group(1)
        ride_desc = f"Lime ride ({distance} miles)"
        if is_refund:
            ride_desc = f"Lime ride refund ({distance} miles)"
        result['line_items'] = [{
            'name': ride_desc,
            'quantity': 1,
            'price': result.get('total_amount'),
        }]

    if result.get('total_amount') or result.get('receipt_date'):
        return result
    return None


