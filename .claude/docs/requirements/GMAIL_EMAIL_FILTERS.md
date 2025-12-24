# Gmail Email Filters Reference

This document describes the vendor-specific email filters used during Gmail sync to import only actual receipt emails and reject marketing/promotional content.

## Overview

Filters are applied at **two stages**:
1. **Sync stage** (`gmail_sync.py`): Early filtering before storing emails in database
2. **Parse stage** (`gmail_parser.py`): Additional filtering during receipt parsing

The filter functions return a tuple: `(is_receipt: bool, reason: str, confidence: int)`
- `True` = Import email (receipt)
- `False` = Reject email (marketing/notification)
- `None` = Not applicable (email not from this vendor)

---

## Vendor Filters

### Amazon

**File:** `gmail_parser.py:210-305`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `store-news@amazon`, `deals@amazon`, `recommendations@amazon`, `marketing@amazon`, `promo@amazon` |
| **REJECT** | Subject (Shipment) | `has been dispatched`, `has been shipped`, `has shipped`, `out for delivery`, `arriving today`, `arriving tomorrow`, `delivered:`, `dispatched:` |
| **ACCEPT** | Subject (Receipt) | `ordered:` (95%), `your amazon.co.uk order` (90%), `your amazon.com order` (90%), `your amazon.de order` (90%), `your amazon.fr order` (90%), `your amazon fresh order` (95%), `your refund for` (95%) |
| **ACCEPT** | Sender | `return@amazon` (refunds) |
| **REJECT** | Subject (Marketing) | `deals for you`, `recommended for you`, `based on your`, `trending now`, `flash sale`, `daily deals`, `save on`, `prime day`, `items you viewed`, `customers also bought`, `you might like`, `special offer`, `price drop`, `back in stock`, `new for you`, `just dropped` |
| **ACCEPT** | Sender (Default) | `auto-confirm@amazon`, `order-update@amazon` (75%) |
| **REJECT** | Default | Any other Amazon email (60%) |

**Notes:**
- Shipment patterns are checked FIRST to reject dispatch/delivery notifications even if they contain "your amazon order"
- `shipment-tracking@amazon` is NOT accepted as a receipt sender
- Orders and refunds are imported; cancellations are NOT imported

---

### eBay

**File:** `gmail_parser.py:142-207`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `newsletter@ebay`, `promotions@ebay`, `deals@ebay`, `marketing@ebay`, `offers@ebay` |
| **ACCEPT** | Subject | `order confirmed`, `your order is confirmed`, `your ebay order is confirmed`, `thanks for your order`, `order details`, `you paid for your item`, `payment sent`, `you've paid for your order`, `you've paid` |
| **REJECT** | Subject | `watchlist`, `price drop`, `deals`, `ending soon`, `recommended`, `top picks`, `you might like`, `saved search`, `save on`, `daily deals`, `best sellers`, `trending now`, `flash sale`, `clearance`, `explore`, `discover`, `based on your`, `items you viewed`, `similar to`, `back in stock` |
| **ACCEPT** | Sender (Default) | `ebay@ebay.com` (70%) |
| **REJECT** | Default | Any other eBay email (60%) |

---

### Uber (Rides & Uber Eats)

**File:** `gmail_parser.py:308-375`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `marketing@uber`, `promo@uber`, `promotions@uber`, `deals@uber`, `news@uber` |
| **ACCEPT** | Subject | `trip with uber` (95%), `order with uber eats` (95%), `your uber receipt` (95%), `your uber eats order` (95%), `thanks for riding` (90%), `thanks for your order` (90%), `your ride with uber` (90%), `your trip on` (90%) |
| **REJECT** | Subject | `save on your next`, `promo code`, `discount`, `free ride`, `free delivery`, `offer expires`, `limited time`, `special offer`, `invite friends`, `refer a friend`, `earn credits`, `reward`, `try uber`, `introducing`, `new in your area` |
| **ACCEPT** | Sender | `receipts@uber` (90%), `noreply@uber` (70%) |
| **REJECT** | Default | Any other Uber email (60%) |

---

### PayPal

**File:** `gmail_parser.py:378-438`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `marketing@paypal`, `promo@paypal`, `promotions@paypal`, `deals@paypal`, `offers@paypal`, `newsletter@paypal` |
| **ACCEPT** | Subject | `receipt for your payment` (95%), `your paypal receipt` (95%), `receipt for your paypal payment` (95%), `you sent a payment` (90%), `payment confirmation` (90%), `you paid` (90%) |
| **REJECT** | Subject | `special offer`, `limited time`, `save on`, `discount`, `earn rewards`, `refer a friend`, `introducing`, `new feature`, `update your`, `verify your` |
| **ACCEPT** | Sender | `service@paypal` (85%) |
| **REJECT** | Default | Any other PayPal email (60%) |

---

### Microsoft

**File:** `gmail_parser.py:441-502`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `marketing@microsoft`, `promo@microsoft`, `newsletter@microsoft`, `offers@microsoft`, `xbox@microsoft` |
| **ACCEPT** | Subject | `your purchase of` (95%), `has been processed` (90%), `order confirmation` (95%), `your order` (90%), `subscription renewed` (90%), `payment received` (90%), `receipt for your` (95%) |
| **REJECT** | Subject | `special offer`, `save on`, `exclusive deal`, `limited time`, `try for free`, `introducing`, `new features`, `update available`, `security alert`, `sign-in activity`, `verify your` |
| **ACCEPT** | Sender | `microsoft-noreply@microsoft` (85%) |
| **REJECT** | Default | Any other Microsoft email (60%) |

---

### Apple

**File:** `gmail_parser.py:505-568`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | Sender | `news@apple`, `news@email.apple`, `marketing@apple`, `promo@apple`, `store@apple` |
| **ACCEPT** | Subject | `your receipt from apple` (95%), `your invoice from apple` (95%), `subscription confirmation` (90%), `your apple store order` (95%), `order confirmation` (90%), `your purchase` (90%), `your renewal` (90%) |
| **REJECT** | Subject | `new in the app store`, `discover`, `special offer`, `try apple`, `get more from`, `introducing`, `free trial`, `upgrade to`, `what's new` |
| **ACCEPT** | Sender | `no_reply@email.apple` (80%), `noreply@apple` (80%) |
| **REJECT** | Default | Any other Apple email (60%) |

---

### Lyft

**File:** `gmail_parser.py:571-614`

| Decision | Type | Patterns |
|----------|------|----------|
| **ACCEPT** | Subject | `your receipt for rides` (95%), `your lyft ride receipt` (95%), `receipt for your ride` (95%), `your ride on` (90%) |
| **REJECT** | Subject | `earn credits`, `refer a friend`, `special offer`, `free ride`, `promo code`, `discount` |
| **REJECT** | Default | Any other Lyft email (60%) |

---

### Deliveroo

**File:** `gmail_parser.py:617-665`

| Decision | Type | Patterns |
|----------|------|----------|
| **ACCEPT** | Subject | `your order is on its way` (95%), `order confirmation` (95%), `your deliveroo receipt` (95%), `thanks for your order` (90%), `your order from` (90%) |
| **REJECT** | Subject | `hungry?`, `free delivery`, `order now`, `craving`, `discount`, `off your next`, `refer a friend` |
| **ACCEPT** | Sender | `orders@deliveroo` (85%) |
| **REJECT** | Default | Any other Deliveroo email (60%) |

---

### Spotify

**File:** `gmail_parser.py:668-689`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | All | Always rejected (95%) - Spotify does not send receipt emails via Gmail |

**Note:** Spotify handles billing through their app/website only.

---

### Netflix

**File:** `gmail_parser.py:692-713`

| Decision | Type | Patterns |
|----------|------|----------|
| **REJECT** | All | Always rejected (95%) - Netflix does not send receipt emails via Gmail |

**Note:** Netflix handles billing through their website only.

---

### Google (Play Store & Payments)

**File:** `gmail_parser.py:716-773`

| Decision | Type | Patterns |
|----------|------|----------|
| **ACCEPT** | Sender + Subject | `googleplay-noreply@google.com` or `payments-noreply@google.com` WITH subject containing `receipt`, `invoice`, `order`, or `payment` (95%) |
| **ACCEPT** | Subject | `google play order receipt` (95%), `your invoice is available` (95%), `payment confirmation` (90%), `order confirmation` (90%), `your receipt` (90%) |
| **REJECT** | Subject | `new features`, `introducing`, `try google`, `upgrade to`, `get more`, `special offer` |
| **REJECT** | Default | Any other Google email (60%) |

---

## Generic Indicators

For vendors not covered by specific filters, generic scoring is used:

### Strong Receipt Indicators (+2 each)
- `order confirmed`, `order confirmation`, `your order has been`
- `payment received`, `payment confirmation`, `receipt for your`
- `invoice #`, `invoice number`, `order #`, `order number`
- `transaction id`, `confirmation number`, `booking confirmed`
- `thank you for your order`, `thank you for your purchase`
- `your receipt`, `e-receipt`, `digital receipt`

### Weak Receipt Indicators (+1 each)
- `order`, `receipt`, `invoice`, `confirmation`, `purchase`
- `payment`, `transaction`, `booking`, `subscription`

### Strong Marketing Indicators (-3 each, any one = reject)
- `shop now`, `buy now`, `order now`, `get yours`
- `sale ends`, `limited time`, `flash sale`, `black friday`, `cyber monday`
- `exclusive deal`, `special offer`, `save up to`, `up to % off`
- `deals you`, `deals for`, `gift ideas`, `gift guide`, `perfect gift`
- `don't miss`, `last chance`, `hurry`
- `view in browser`, `email preferences`, `manage preferences`

### Weak Marketing Indicators (-1 each)
- `unsubscribe`, `newsletter`, `promotional`, `marketing`
- `sale`, `discount`, `offer`, `promo`, `savings`

### Known Marketing Senders (always reject)
- `store-news@amazon`, `deals@amazon`, `recommendations@amazon`
- `marketing@`, `promo@`, `newsletter@`
- `deals@`, `offers@`, `sales@`, `promotions@`
- `campaign@`, `email@`, `hello@`

### List-Unsubscribe Header
- Presence of `List-Unsubscribe` header strongly indicates marketing (reject)
- Exception: If from a known receipt sender, allow through

---

## Decision Thresholds

| Score | Decision |
|-------|----------|
| >= 3 | Accept as receipt (confidence: 70% + score*5, max 95%) |
| <= -2 | Reject as marketing (confidence: 70% + |score|*5, max 95%) |
| -1 to 2 | Ambiguous - default to reject (confidence: 50%) |

---

## Implementation Notes

1. **Early filtering** in `gmail_sync.py` prevents non-receipts from being stored
2. **Parse-time filtering** in `gmail_parser.py` provides additional validation
3. Vendor-specific filters take precedence over generic scoring
4. Shipment/delivery notifications are rejected even from receipt senders
5. Confidence scores (%) indicate filter certainty
6. All pattern matching is case-insensitive

---

## Maintenance

To add a new vendor filter:
1. Create `is_<vendor>_receipt_email()` function in `gmail_parser.py`
2. Add import in `gmail_sync.py`
3. Add to `filters` list in `should_import_email()` function
4. Update this document

Last updated: 2024-12-22
