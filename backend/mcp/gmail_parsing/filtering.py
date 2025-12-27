"""
Gmail Receipt Filtering

Vendor-specific and generic receipt vs marketing classification.
Pre-filters emails before extraction to reject marketing/promotional content.
"""

import re
from typing import Tuple


# Strong receipt indicators (weighted +2)
STRONG_RECEIPT_INDICATORS = [
    'order confirmed', 'order confirmation', 'your order has been',
    'payment received', 'payment confirmation', 'receipt for your',
    'invoice #', 'invoice number', 'order #', 'order number',
    'transaction id', 'confirmation number', 'booking confirmed',
    'thank you for your order', 'thank you for your purchase',
    'your receipt', 'e-receipt', 'digital receipt',
]

# Weak receipt indicators (weighted +1)
WEAK_RECEIPT_INDICATORS = [
    'order', 'receipt', 'invoice', 'confirmation', 'purchase',
    'payment', 'transaction', 'booking', 'subscription',
]

# Strong marketing/promotional indicators (weighted -3, any one = reject)
STRONG_MARKETING_INDICATORS = [
    'shop now', 'buy now', 'order now', 'get yours',
    'sale ends', 'limited time', 'flash sale', 'black friday',
    'cyber monday', 'exclusive deal', 'special offer',
    'save up to', 'up to % off', 'deals you', 'deals for',
    'gift ideas', 'gift guide', 'perfect gift',
    'don\'t miss', 'last chance', 'hurry',
    'view in browser', 'email preferences', 'manage preferences',
]

# Weak marketing indicators (weighted -1)
WEAK_MARKETING_INDICATORS = [
    'unsubscribe', 'newsletter', 'promotional', 'marketing',
    'sale', 'discount', 'offer', 'promo', 'savings',
]

# Known transactional sender patterns (full email prefixes, not just domains)
KNOWN_RECEIPT_SENDERS = [
    'auto-confirm@amazon', 'order-update@amazon', 'shipment-tracking@amazon', 'return@amazon',
    'noreply@uber.com', 'receipts@uber.com',
    'noreply@apple.com', 'no_reply@email.apple.com',
    'service@paypal', 'noreply@paypal',
    'noreply@deliveroo', 'orders@deliveroo',
    'receipts@netflix.com', 'info@account.netflix.com',
    'noreply@spotify.com',
    'noreply@google.com', 'payments-noreply@google.com',
    'msa@communication.microsoft.com',  # Account notifications
    # eBay transactional senders
    'ebay@ebay.com', 'orders@ebay.com', 'transaction@ebay.com', 'ebay@reply.ebay.com',
]

# Known marketing sender patterns (reject these even from known domains)
KNOWN_MARKETING_SENDERS = [
    'store-news@amazon', 'deals@amazon', 'recommendations@amazon',
    'marketing@', 'promo@', 'newsletter@',
    'deals@', 'offers@', 'sales@', 'promotions@',
    'campaign@', 'email@', 'hello@',  # Often marketing
    # eBay marketing senders
    'newsletter@ebay', 'promotions@ebay', 'deals@ebay', 'offers@ebay',
    # Uber marketing senders
    'marketing@uber', 'promo@uber', 'promotions@uber', 'deals@uber', 'news@uber',
]


def is_ebay_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    eBay-specific receipt filter using strict subject patterns.

    Only accepts these 3 subject patterns:
    1. "{name}, your order is confirmed"
    2. "Order confirmed: {product description}"
    3. "Your order is confirmed."

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an eBay email
    """
    sender_lower = sender_email.lower()

    # Only process eBay emails
    if 'ebay' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Pattern 1: "{name}, your order is confirmed"
    if ', your order is confirmed' in subject_lower:
        return (True, 'eBay receipt: {name}, your order is confirmed', 95)

    # Pattern 2: "Order confirmed: {product description}"
    if subject_lower.startswith('order confirmed:'):
        return (True, 'eBay receipt: Order confirmed: {product}', 95)

    # Pattern 3: "Your order is confirmed."
    if subject_lower == 'your order is confirmed.' or subject_lower == 'your order is confirmed':
        return (True, 'eBay receipt: Your order is confirmed', 95)

    # Reject all other eBay emails
    return (False, 'eBay email - not a receipt', 90)


def is_amazon_receipt_email(subject: str, sender_email: str, body_text: str = None) -> tuple:
    """
    Amazon-specific receipt filter using subject patterns and body content.

    Accepts:
    - Regular orders: Subject starts with "Ordered:"
    - Amazon Fresh: Subject "Your Amazon Fresh order has been received"
    - Amazon Business: Subject "Your Amazon.co.uk order." (exact match)
    - Refunds: Subject contains "your refund" or "refund for"
    - Body fallback: Contains "Thanks for your order"

    Rejects:
    - Marketing senders
    - Return notifications
    - Shipment/delivery notifications

    Args:
        subject: Email subject line
        sender_email: Full sender email address
        body_text: Email body text (HTML or plain text)

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Amazon email
    """
    sender_lower = sender_email.lower()

    # Only process Amazon emails
    if 'amazon' not in sender_lower:
        return (None, None, None)

    # Reject known marketing senders first (fast path)
    AMAZON_MARKETING_SENDERS = [
        'store-news@amazon', 'deals@amazon', 'recommendations@amazon',
        'marketing@amazon', 'promo@amazon',
    ]
    for pattern in AMAZON_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Amazon marketing sender: {pattern}', 95)

    subject_lower = subject.lower()

    # Reject return notification emails (not receipts)
    # Patterns: "Your return {of product}", "dropoff confirmation for {product}"
    if subject_lower.startswith('your return'):
        return (False, 'Amazon return notification (not a receipt)', 95)
    if 'drop' in subject_lower and 'confirmation' in subject_lower:
        # Matches: "dropoff confirmation", "drop-off confirmation", "drop off confirmation"
        return (False, 'Amazon return dropoff confirmation (not a receipt)', 95)

    # Reject shipment/delivery notifications (not receipts)
    SHIPMENT_PATTERNS = [
        'has been dispatched', 'has been shipped', 'has shipped',
        'out for delivery', 'arriving today', 'arriving tomorrow',
        'delivered:', 'dispatched:'
    ]
    for pattern in SHIPMENT_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Amazon shipment notification: {pattern}', 95)

    # === ACCEPT PATTERNS (subject-based) ===

    # Regular Amazon order receipts: "Ordered: 'Product Name...'"
    if subject_lower.startswith('ordered:'):
        return (True, 'Amazon order receipt (Ordered: subject pattern)', 95)

    # Amazon Fresh order confirmations (specific subject pattern)
    if subject_lower == 'your amazon fresh order has been received':
        return (True, 'Amazon Fresh order confirmation', 95)

    # Amazon Business: body contains "order is placed on behalf of"
    # NOTE: Subject "Your Amazon.co.uk order." is NOT unique to Business - must check body
    if body_text and 'order is placed on behalf of' in body_text.lower():
        return (True, 'Amazon Business order (body indicator)', 95)

    # Simple body-based filter: Amazon receipts contain "Thanks for your order"
    if body_text and 'thanks for your order' in body_text.lower():
        return (True, 'Amazon receipt (body contains "Thanks for your order")', 95)

    # Check for refund emails (different body pattern)
    if 'your refund' in subject_lower or 'refund for' in subject_lower:
        return (True, 'Amazon refund email', 90)

    # Accept from return@ sender (refunds)
    if 'return@amazon' in sender_lower:
        return (True, 'Amazon refund sender', 90)

    # Reject all other Amazon emails (delivery notifications, cancellations, etc.)
    return (False, 'Amazon email without receipt indicator', 90)


def is_uber_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Uber-specific receipt filter using strict subject pattern.

    Only accepts: "Your {daypart} trip with Uber"
    e.g., "Your Thursday evening trip with Uber"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Uber email
    """
    sender_lower = sender_email.lower()

    # Only process Uber emails
    if 'uber' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Only accept pattern: "Your {daypart} trip with Uber"
    # e.g., "Your Thursday evening trip with Uber"
    if subject_lower.startswith('your ') and 'trip with uber' in subject_lower:
        return (True, 'Uber receipt: Your {daypart} trip with Uber', 95)

    # Reject all other Uber emails
    return (False, 'Uber email - not a trip receipt', 90)


def is_paypal_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    PayPal-specific receipt filter using strict subject patterns.

    Accepts ONLY these 3 patterns:
    1. "Receipt for your payment to {merchant}"
    2. "Your PayPal receipt"
    3. "Receipt for your paypal payment"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a PayPal email
    """
    sender_lower = sender_email.lower()

    # Only process PayPal emails
    if 'paypal' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Pattern 1: "Receipt for your payment to {merchant}"
    if subject_lower.startswith('receipt for your payment to'):
        return (True, 'PayPal receipt: Receipt for your payment to {merchant}', 95)

    # Pattern 2: "Your PayPal receipt"
    if subject_lower == 'your paypal receipt':
        return (True, 'PayPal receipt: Your PayPal receipt', 95)

    # Pattern 3: "Receipt for your paypal payment"
    if subject_lower == 'receipt for your paypal payment':
        return (True, 'PayPal receipt: Receipt for your paypal payment', 95)

    # Reject all other PayPal emails
    return (False, 'PayPal email - not a receipt', 90)


def is_microsoft_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Microsoft-specific receipt vs marketing classification.

    Microsoft sends purchase receipts from microsoft-noreply@microsoft.com
    with subjects like "Your purchase of [PRODUCT] has been processed".

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Microsoft email
    """
    sender_lower = sender_email.lower()

    # Only process Microsoft emails
    if 'microsoft' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject known marketing senders first
    MICROSOFT_MARKETING_SENDERS = [
        'marketing@microsoft', 'promo@microsoft', 'newsletter@microsoft',
        'offers@microsoft', 'xbox@microsoft',
    ]
    for pattern in MICROSOFT_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Microsoft marketing sender: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence)
    MICROSOFT_RECEIPT_PATTERNS = [
        ('your purchase of', 95),
        ('has been processed', 90),
        ('order confirmation', 95),
        ('your order', 90),
        ('subscription renewed', 90),
        ('payment received', 90),
        ('receipt for your', 95),
    ]
    for pattern, confidence in MICROSOFT_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Microsoft receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    MICROSOFT_MARKETING_PATTERNS = [
        'special offer', 'save on', 'exclusive deal', 'limited time',
        'try for free', 'introducing', 'new features', 'update available',
        'security alert', 'sign-in activity', 'verify your',
    ]
    for pattern in MICROSOFT_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Microsoft marketing subject: {pattern}', 90)

    # Accept from noreply@ sender for transactions
    if 'microsoft-noreply@microsoft' in sender_lower:
        return (True, 'Microsoft noreply sender', 85)

    # Ambiguous Microsoft email - reject to avoid false positives
    return (False, 'Microsoft - no receipt indicators', 60)


def is_apple_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Apple-specific receipt vs marketing classification.

    Apple sends many marketing emails from the same domains as receipts.
    Need to distinguish receipts/invoices from App Store promos.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Apple email
    """
    sender_lower = sender_email.lower()

    # Only process Apple emails
    if 'apple' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject known marketing senders first
    APPLE_MARKETING_SENDERS = [
        'news@apple', 'news@email.apple', 'marketing@apple',
        'promo@apple', 'store@apple',
    ]
    for pattern in APPLE_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Apple marketing sender: {pattern}', 95)

    # Reject subscription notification patterns FIRST (these have no amounts)
    APPLE_SUBSCRIPTION_NOTIFICATION_PATTERNS = [
        'subscription is confirmed',
        'subscription is expiring',
        'subscription confirmation',
        'subscription renewal',
        'your subscription is',
        'pre-order for',
        'is now available',
    ]
    for pattern in APPLE_SUBSCRIPTION_NOTIFICATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Apple subscription notification: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence) - actual invoices with amounts
    APPLE_RECEIPT_PATTERNS = [
        ('your receipt from apple', 95),
        ('your invoice from apple', 95),
        ('your apple store order', 95),
        ('order confirmation', 90),
        ('your purchase', 90),
    ]
    for pattern, confidence in APPLE_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Apple receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    APPLE_MARKETING_PATTERNS = [
        'new in the app store', 'discover', 'special offer',
        'try apple', 'get more from', 'introducing',
        'free trial', 'upgrade to', 'what\'s new',
    ]
    for pattern in APPLE_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Apple marketing subject: {pattern}', 90)

    # Ambiguous Apple email - reject to avoid false positives
    return (False, 'Apple - no receipt indicators', 60)


def is_lyft_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Lyft-specific receipt vs marketing classification.

    Lyft sends ride receipts and promotional emails from the same domain.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Lyft email
    """
    sender_lower = sender_email.lower()

    # Only process Lyft emails
    if 'lyft' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept receipt subject patterns (HIGH confidence)
    LYFT_RECEIPT_PATTERNS = [
        ('your receipt for rides', 95),
        ('your lyft ride receipt', 95),
        ('receipt for your ride', 95),
        ('your ride on', 90),
    ]
    for pattern, confidence in LYFT_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Lyft receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    LYFT_MARKETING_PATTERNS = [
        'earn credits', 'refer a friend', 'special offer',
        'free ride', 'promo code', 'discount',
    ]
    for pattern in LYFT_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Lyft marketing subject: {pattern}', 90)

    # Ambiguous Lyft email - reject to avoid false positives
    return (False, 'Lyft - no receipt indicators', 60)


def is_deliveroo_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Deliveroo-specific receipt vs marketing classification.

    Only accepts: "Your order's in the kitchen 🎉" (the actual receipt)
    Rejects: cancellations, surveys, marketing, etc.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Deliveroo email
    """
    sender_lower = sender_email.lower()

    # Only process Deliveroo emails
    if 'deliveroo' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY "Your order's in the kitchen" emails (actual receipts)
    if "order's in the kitchen" in subject_lower or "order is in the kitchen" in subject_lower:
        return (True, 'Deliveroo order confirmation', 95)

    # Reject everything else from Deliveroo (cancellations, surveys, marketing)
    return (False, 'Deliveroo - not an order confirmation', 90)


def is_spotify_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Spotify-specific classification - always marketing, never receipts.

    Spotify does not send receipt emails - all emails are marketing/promotional.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Spotify email
    """
    sender_lower = sender_email.lower()

    # Only process Spotify emails
    if 'spotify' not in sender_lower:
        return (None, None, None)

    # Spotify never sends receipts via email - all are marketing
    return (False, 'Spotify - never sends receipt emails', 95)


def is_netflix_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Netflix-specific classification - always marketing, never receipts.

    Netflix does not send receipt emails - all emails are marketing/promotional.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Netflix email
    """
    sender_lower = sender_email.lower()

    # Only process Netflix emails
    if 'netflix' not in sender_lower:
        return (None, None, None)

    # Netflix never sends receipts via email - all are marketing
    return (False, 'Netflix - never sends receipt emails', 95)


def is_google_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Google-specific receipt vs marketing classification.

    Google sends receipts from:
    - Google Play: googleplay-noreply@google.com
    - Google Payments/Cloud: payments-noreply@google.com

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Google email
    """
    sender_lower = sender_email.lower()

    # Only process Google emails
    if 'google' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept from known receipt senders
    GOOGLE_RECEIPT_SENDERS = [
        'googleplay-noreply@google.com',
        'payments-noreply@google.com',
    ]
    for pattern in GOOGLE_RECEIPT_SENDERS:
        if pattern in sender_lower:
            # Check subject for receipt indicators
            if any(ind in subject_lower for ind in ['receipt', 'invoice', 'order', 'payment']):
                return (True, f'Google receipt sender: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence)
    GOOGLE_RECEIPT_PATTERNS = [
        ('google play order receipt', 95),
        ('your invoice is available', 95),
        ('payment confirmation', 90),
        ('order confirmation', 90),
        ('your receipt', 90),
    ]
    for pattern, confidence in GOOGLE_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Google receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    GOOGLE_MARKETING_PATTERNS = [
        'new features', 'introducing', 'try google',
        'upgrade to', 'get more', 'special offer',
    ]
    for pattern in GOOGLE_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Google marketing subject: {pattern}', 90)

    # Ambiguous Google email - reject to avoid false positives
    return (False, 'Google - no receipt indicators', 60)


def is_ocado_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Ocado-specific filter - reject marketing emails.

    marketing.ocado.com sends only marketing emails, never receipts.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Ocado email
    """
    sender_lower = sender_email.lower()

    # Only process Ocado emails
    if 'ocado' not in sender_lower:
        return (None, None, None)

    # Reject all marketing.ocado.com emails
    if 'marketing.ocado' in sender_lower:
        return (False, 'Ocado marketing sender', 95)

    # Allow other Ocado emails through (will be filtered by generic logic)
    return (None, None, None)


def is_citizens_of_soil_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Citizens of the Soil receipt filter.

    Accepts: "Olive oil order #XXX confirmed 🙌" (purchase confirmations)
    Rejects: "Your order #XXX is on the way..." (shipping notifications)

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Citizens of the Soil email
    """
    sender_lower = sender_email.lower()

    # Only process Citizens of the Soil emails
    if 'citizensofsoil' not in sender_lower and 'citizens of soil' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept: "Olive oil order #XXX confirmed" (purchase confirmation)
    if 'confirmed' in subject_lower and 'order' in subject_lower:
        return (True, 'Citizens of the Soil order confirmation', 95)

    # Reject: "Your order #XXX is on the way..." (shipping notification)
    if 'is on the way' in subject_lower:
        return (False, 'Citizens of the Soil shipping notification', 95)

    # Reject other emails from this sender
    return (False, 'Citizens of the Soil - not a receipt', 90)


def is_figma_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Figma receipt filter.

    Accepts: "Receipt for subscription payment {month day, year}"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Figma email
    """
    sender_lower = sender_email.lower()

    # Only process Figma emails
    if 'figma' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept: "Receipt for subscription payment {month day, year}"
    if subject_lower.startswith('receipt for subscription payment'):
        return (True, 'Figma subscription receipt', 95)

    # Reject other emails from this sender
    return (False, 'Figma - not a receipt', 90)


def is_sebago_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Sebago-specific receipt filter.

    Accepts: "Your Sebago Order" from orders@sebago.co.uk
    Rejects: Status updates, marketing from info@email.sebago.co.uk

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Sebago email
    """
    sender_lower = sender_email.lower()

    # Only process Sebago emails
    if 'sebago' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject marketing emails from info@email.sebago.co.uk
    if 'info@' in sender_lower or 'email.sebago' in sender_lower:
        return (False, 'Sebago marketing email', 95)

    # Accept: "Your Sebago Order" or "Your order from Sebago"
    if 'sebago order' in subject_lower or 'order from sebago' in subject_lower:
        return (True, 'Sebago order confirmation', 95)

    # Reject status updates
    if 'has updates' in subject_lower or 'status' in subject_lower:
        return (False, 'Sebago status update (not a receipt)', 95)

    # Reject other Sebago emails
    return (False, 'Sebago - not an order confirmation', 90)


def is_gmail_forwarded_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all gmail.com emails (user-forwarded receipts).

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a gmail.com email
    """
    if 'gmail.com' in sender_email.lower():
        return (False, 'Forwarded email from gmail.com', 95)
    return (None, None, None)


def is_sony_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all bmail.sony-europe.com emails.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Sony email
    """
    if 'bmail.sony-europe.com' in sender_email.lower():
        return (False, 'Sony marketing email', 95)
    return (None, None, None)


def is_booking_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all booking.com emails.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a booking.com email
    """
    if 'booking.com' in sender_email.lower():
        return (False, 'Booking.com email rejected', 95)
    return (None, None, None)


def is_non_receipt_notification(subject: str, sender_email: str) -> tuple:
    """
    Filter out booking confirmations and shipping notifications.

    These are NOT receipts - they don't contain payment amounts:
    - Booking confirmations (restaurant reservations, travel bookings)
    - Shipping/delivery notifications
    - Order status updates

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a known non-receipt notification
    """
    subject_lower = subject.lower()

    # Booking confirmation patterns (restaurant reservations, etc.)
    BOOKING_CONFIRMATION_PATTERNS = [
        'booking confirmation for',
        'your reservation at',
        'reservation confirmed',
        'table booked',
        'your booking at',
    ]
    for pattern in BOOKING_CONFIRMATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Booking confirmation: {pattern}', 95)

    # Shipping/delivery notification patterns (not receipts)
    SHIPPING_NOTIFICATION_PATTERNS = [
        'your order is on the way',
        'your order has shipped',
        'your order has been shipped',
        'your order has been delivered',
        'your package is on its way',
        'out for delivery',
        'delivery update',
        'tracking your order',
        'your shipment',
        'has been dispatched',
        'is being prepared',
    ]
    for pattern in SHIPPING_NOTIFICATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Shipping notification: {pattern}', 95)

    # Known shipping notification domains (all emails are shipping updates, not receipts)
    SHIPPING_DOMAINS = [
        'woolrich.com',  # Only sends delivery notifications
    ]
    for domain in SHIPPING_DOMAINS:
        if domain in sender_email.lower():
            # Reject all emails from these domains except actual receipts/purchase confirmations
            is_purchase_email = any(kw in subject_lower for kw in ['receipt', 'invoice', 'your purchase', 'thank you for your purchase'])
            if not is_purchase_email:
                return (False, f'Shipping notification domain: {domain}', 95)

    # Known booking/reservation domains
    BOOKING_DOMAINS = [
        'thefork.co.uk', 'thefork.com',
        'opentable.com', 'opentable.co.uk',
    ]
    sender_lower = sender_email.lower()
    for domain in BOOKING_DOMAINS:
        if domain in sender_lower:
            # Only reject if it's a confirmation, not a receipt
            if 'confirmation' in subject_lower or 'booked' in subject_lower:
                return (False, f'Booking platform confirmation: {domain}', 95)

    return (None, None, None)


def is_designacable_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Designacable receipt filter.

    Accepts ONLY: "Your designacable.com order confirmation"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Designacable email
    """
    sender_lower = sender_email.lower()

    # Only process Designacable emails
    if 'designacable' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY: "Your designacable.com order confirmation"
    if subject_lower == 'your designacable.com order confirmation':
        return (True, 'Designacable order confirmation', 95)

    # Reject all other Designacable emails
    return (False, 'Designacable - not order confirmation', 90)


def is_ryanair_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Ryanair receipt filter.

    Accepts ONLY: "Ryanair Travel Itinerary"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Ryanair email
    """
    sender_lower = sender_email.lower()

    # Only process Ryanair emails
    if 'ryanair' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY: "Ryanair Travel Itinerary"
    if subject_lower == 'ryanair travel itinerary':
        return (True, 'Ryanair Travel Itinerary', 95)

    # Reject all other Ryanair emails
    return (False, 'Ryanair - not travel itinerary', 90)


def is_charles_tyrwhitt_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Charles Tyrwhitt receipt filter.

    Accepts ONLY: "With our thanks, here is your Charles Tyrwhitt e-receipt!"
    These emails contain the actual receipt as an attached PDF.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Charles Tyrwhitt email
    """
    sender_lower = sender_email.lower()

    # Only process Charles Tyrwhitt emails
    if 'ctshirts' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY e-receipt emails (have PDF attachment)
    if subject_lower == 'with our thanks, here is your charles tyrwhitt e-receipt!':
        return (True, 'Charles Tyrwhitt e-receipt (PDF attached)', 95)

    # Reject order confirmations and other emails
    return (False, 'Charles Tyrwhitt - not e-receipt', 90)


def is_etsy_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Etsy-specific receipt filter.

    Etsy sends TWO types of transactional emails:
    1. Purchase receipts: "Your Etsy Purchase from {seller} ({order_id})" - ACCEPT
    2. Dispatch notifications: "Your Etsy Order dispatched (Receipt #{order_id})" - REJECT

    Only purchase receipts contain actual payment amounts.
    Dispatch notifications are shipping updates, not receipts.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Etsy email
    """
    sender_lower = sender_email.lower()

    # Only process Etsy emails
    if 'etsy' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # ACCEPT: "Your Etsy Purchase from {seller} ({order_id})"
    # Pattern: starts with "your etsy purchase from"
    if subject_lower.startswith('your etsy purchase from'):
        return (True, 'Etsy purchase receipt', 95)

    # REJECT: "Your Etsy Order dispatched (Receipt #{order_id})"
    # These are shipping notifications, NOT receipts
    if 'dispatched' in subject_lower or 'shipped' in subject_lower:
        return (False, 'Etsy dispatch/shipping notification (not a receipt)', 95)

    # REJECT: Other shipping/delivery patterns
    if 'on the way' in subject_lower or 'delivered' in subject_lower:
        return (False, 'Etsy delivery notification (not a receipt)', 95)

    # Reject all other Etsy emails (marketing, surveys, etc.)
    return (False, 'Etsy - not a purchase receipt', 90)


def is_likely_receipt(
    subject: str,
    body_text: str,
    sender_email: str,
    sender_domain: str = None,
    list_unsubscribe: str = None,
    has_schema_order: bool = False
) -> tuple:
    """
    Determine if email is likely a receipt vs marketing/promotional.

    Uses multi-signal approach:
    1. Schema.org Order markup = definite receipt
    2. List-Unsubscribe header = likely marketing
    3. Sender email pattern matching
    4. Content keyword scoring

    Args:
        subject: Email subject
        body_text: Email body text (first 1000 chars used)
        sender_email: Full sender email address
        sender_domain: Sender domain (optional)
        list_unsubscribe: List-Unsubscribe header value (optional)
        has_schema_order: Whether email has Schema.org Order markup

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
    """
    # Signal 1: Schema.org Order markup is definitive
    if has_schema_order:
        return (True, 'Has Schema.org Order markup', 100)

    # Signal 1.5: Reject user-forwarded emails and known non-receipt senders first
    gmail_result = is_gmail_forwarded_email(subject, sender_email)
    if gmail_result[0] is not None:
        return gmail_result

    sony_result = is_sony_email(subject, sender_email)
    if sony_result[0] is not None:
        return sony_result

    booking_result = is_booking_email(subject, sender_email)
    if booking_result[0] is not None:
        return booking_result

    # Filter out booking confirmations and shipping notifications
    non_receipt_result = is_non_receipt_notification(subject, sender_email)
    if non_receipt_result[0] is not None:
        return non_receipt_result

    # Signal 1.6: Vendor-specific pre-filters (before generic processing)
    # These vendors need special handling due to high volume of marketing emails
    designacable_result = is_designacable_receipt_email(subject, sender_email)
    if designacable_result[0] is not None:
        return designacable_result

    ryanair_result = is_ryanair_receipt_email(subject, sender_email)
    if ryanair_result[0] is not None:
        return ryanair_result

    charles_tyrwhitt_result = is_charles_tyrwhitt_receipt_email(subject, sender_email)
    if charles_tyrwhitt_result[0] is not None:
        return charles_tyrwhitt_result

    ebay_result = is_ebay_receipt_email(subject, sender_email)
    if ebay_result[0] is not None:
        return ebay_result

    amazon_result = is_amazon_receipt_email(subject, sender_email, body_text)
    if amazon_result[0] is not None:
        return amazon_result

    uber_result = is_uber_receipt_email(subject, sender_email)
    if uber_result[0] is not None:
        return uber_result

    paypal_result = is_paypal_receipt_email(subject, sender_email)
    if paypal_result[0] is not None:
        return paypal_result

    microsoft_result = is_microsoft_receipt_email(subject, sender_email)
    if microsoft_result[0] is not None:
        return microsoft_result

    apple_result = is_apple_receipt_email(subject, sender_email)
    if apple_result[0] is not None:
        return apple_result

    lyft_result = is_lyft_receipt_email(subject, sender_email)
    if lyft_result[0] is not None:
        return lyft_result

    deliveroo_result = is_deliveroo_receipt_email(subject, sender_email)
    if deliveroo_result[0] is not None:
        return deliveroo_result

    spotify_result = is_spotify_receipt_email(subject, sender_email)
    if spotify_result[0] is not None:
        return spotify_result

    netflix_result = is_netflix_receipt_email(subject, sender_email)
    if netflix_result[0] is not None:
        return netflix_result

    google_result = is_google_receipt_email(subject, sender_email)
    if google_result[0] is not None:
        return google_result

    ocado_result = is_ocado_receipt_email(subject, sender_email)
    if ocado_result[0] is not None:
        return ocado_result

    citizens_result = is_citizens_of_soil_receipt_email(subject, sender_email)
    if citizens_result[0] is not None:
        return citizens_result

    figma_result = is_figma_receipt_email(subject, sender_email)
    if figma_result[0] is not None:
        return figma_result

    sebago_result = is_sebago_receipt_email(subject, sender_email)
    if sebago_result[0] is not None:
        return sebago_result

    etsy_result = is_etsy_receipt_email(subject, sender_email)
    if etsy_result[0] is not None:
        return etsy_result

    sender_lower = (sender_email or '').lower()
    text = f"{subject} {body_text[:1000]}".lower()

    # Signal 2: List-Unsubscribe header strongly indicates marketing
    if list_unsubscribe:
        # But check if it's from a known receipt sender first
        is_known_receipt_sender = any(
            pattern in sender_lower for pattern in KNOWN_RECEIPT_SENDERS
        )
        if not is_known_receipt_sender:
            return (False, 'Has List-Unsubscribe header (marketing)', 85)

    # Signal 3: Check sender patterns
    # Known marketing senders = reject
    for pattern in KNOWN_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Marketing sender pattern: {pattern}', 90)

    # Known receipt senders = accept (but verify with content)
    is_known_receipt_sender = any(
        pattern in sender_lower for pattern in KNOWN_RECEIPT_SENDERS
    )

    # Signal 4: Content scoring
    score = 0

    # Strong marketing indicators (any one = likely reject)
    for indicator in STRONG_MARKETING_INDICATORS:
        if indicator in text:
            score -= 3
            # If we hit a strong marketing indicator and not from known receipt sender
            if not is_known_receipt_sender:
                return (False, f'Strong marketing indicator: {indicator}', 80)

    # Weak marketing indicators
    for indicator in WEAK_MARKETING_INDICATORS:
        if indicator in text:
            score -= 1

    # Strong receipt indicators
    for indicator in STRONG_RECEIPT_INDICATORS:
        if indicator in text:
            score += 2

    # Weak receipt indicators
    for indicator in WEAK_RECEIPT_INDICATORS:
        if indicator in text:
            score += 1

    # Check for order/invoice number patterns (strong receipt signal)
    has_order_number = bool(re.search(
        r'(?:order|invoice|confirmation|booking|transaction)\s*(?:#|number|no\.?|id)?\s*[:.]?\s*[A-Z0-9-]{5,}',
        text, re.IGNORECASE
    ))
    if has_order_number:
        score += 3

    # Known receipt sender gets a bonus
    if is_known_receipt_sender:
        score += 2

    # Decision threshold
    if score >= 3:
        return (True, f'Receipt score: {score}', min(70 + score * 5, 95))
    elif score <= -2:
        return (False, f'Marketing score: {score}', min(70 + abs(score) * 5, 95))
    else:
        # Ambiguous - lean towards not a receipt to avoid false positives
        return (False, f'Ambiguous score: {score} (defaulting to not receipt)', 50)


def has_schema_order_markup(html_body: str) -> bool:
    """Check if HTML contains Schema.org Order markup (definitive receipt signal)."""
    if not html_body:
        return False
    # Check for JSON-LD Order type
    if '"@type"' in html_body and '"Order"' in html_body:
        return True
    # Check for microdata Order type
    if 'itemtype' in html_body and 'schema.org/Order' in html_body:
        return True
    return False
