# Information Architecture

## Context
Receipts send by email may have the following basic information:
1. Issuer:
    - Always abailable
    - inferred from URL e.g. amazon, paypal, british gas, easyjet
2. Seller:
    - Almost always available
    - Needs custom parsing for each seller's email template
    - If not present, may be inferred to be same as Issuer
    - Issuer = Amamzon: Seller = Amazon Business | Anazon Fresh | Amazon UK
    - Issuer = Paypal: Seller = Blacksheep Coffee | Bluehost
    - Issuer = Bitish Gas: Seller = British Gas
4. Line-Items:
    - Almost always available
    - Needs custom parsing for each seller's email template
    - May be single item, or several line items
    - e.g. Sure Mens Ultimate, Google Cloud Subscription
5. Amount
    - may be in any currency (using currnecy symbol or abbreviation)
    - may be in different formats (e.g. comma instead of fullstop decimal separator)
    - may be made up of sub-totals
    - may show tax added as a line item
    - may show shipping cost as a line item
6. Date
    - may be in different international formats
    - if not stated in email body, then may be inferred from email receipt date
7. Order reference:
    - in email body
    - usually prefixed by text such as Order, Order Number, Ref, Reference, Order Reference
