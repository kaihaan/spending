# Workflow for transaction enrichment

## Enrichment prerequisites
- database table of bank transactions (date, description, money_in, money_out, balance)
- database table of amazon payments ("Website","Order ID","Order Date","Purchase Order Number","Currency","Unit Price","Unit Price Tax","Shipping Charge","Total Discounts","Total Owed","Shipment Item Subtotal","Shipment Item Subtotal Tax","ASIN","Product Condition","Quantity","Payment Instrument Type","Order Status","Shipment Status","Ship Date","Shipping Option","Shipping Address","Billing Address","Carrier Name & Tracking Number","Product Name","Gift Message","Gift Sender Name","Gift Recipient Contact Details","Item Serial Number")
- database table of amazon refunds ("OrderID","ReversalID","RefundCompletionDate","Currency","AmountRefunded","Status","DisbursementType")
- database table of Apple App Store payments (order_id,order_date,total_amount,currency,app_names,publishers,item_count)

## Enrichment Types
1. Amazon: enrich with Amazon transaction data
  - payments: for each match to an amazon payment record in the bank transactions enrich with...
    - is_amz_pay_match boolean flag
    - product_name text
  - refunds: 
    - item_refunded: for each match of a bank account outgoing payment to an amazon refund record enrich with...
      - is_returned (boolean)
      - order_id
      - refund_id
      - order_date
    - refund_disbursement: for each match of a bank account income item to ab amazon refund record  enrich with...
      - is_refund
      - refund_date
      - order_id
      - refund_id
2. Apple App Store: for each match of a bank account payment to an Apple App Store transaction, enrich with...
    - order_id
    - order_date
    - app_names
    - publishers
3. LLM: For every transactionm enrich using LLM
    - Send to the LLM
      - Bank account transaction description
      - Amazon product name
      - Apple App Name & Publisher
    - DO NOT SEND any transaction amount information
    - Return: the LLM will return  
      - primary_category: One of: Groceries, Transport, Clothing, Dining, Streaming, Shopping, Healthcare, Utilities, Income, Taxes, Insurance, Education, Holiday, Personal Care, Gifts, Pet Care, Home & Garden, Electronics, Sports & Outdoors, Books & Media, Office Supplies, Automotive, Banking Fees, Other
      - subcategory: More specific classification (e.g., "Coffee Shop", "Supermarket", "Taxi Service")
      - merchant_clean_name: Standardized merchant name (e.g., "Amazon", "Starbucks", "TfL", not "AMZN*MKTP" or "TESCO STORES")
      - merchant_type: Type of merchant (e.g., "supermarket", "coffee shop", "public transport", "utility provider", "council tax", "restaurant", "music streaming", "airline")
      - essential_discretionary: Either "Essential" (necessary for living) or "Discretionary" (optio    nal/luxury)
      - method: The payment method (Credit Card, Debit Card, Faster Payment, Bank Giro, Apple Pay, Direct Debit, Transfer, Cash, Che    ck)
      - method_subtype: Subtype if applicable (e.g., "Apple Pay via Zettle", "Apple Pay via Sumup", "Visa", "Mastercard")
      - actor: The company/person/entity being paid, or sending the disbursement or remittance
      - origin_date: The date the purchase was made (YYYY-MM-DD), may differ from the transaction date shown with the bank
      - confidence_score: Your confidence in this classification from 0.0 to 1.0

## Enrichment Workflows
1. The user should be able view analytics on enrichment & see which transactions have been enriched
2. When a user importats new bank transactions they should be automatically enriched
3. For LLM enrichment: 
  - Enrichment progress should be visible to the user
  - Cost of enrichment should be shown afterwards along with statsitics
  - The user should have control over batch size to send for LLM enrichment.
  - User should be able to cancel the LLM enrichment
  - Enrichment data should be perisitent so that duplicate LLM calls are not needed
2. Either when transactions are ingested or on user request:
  - the original transaction data must be retained
  - Lookup based enrichment
    - matches from lookup tables (e.g. Amazon and Apple App Store payment tables) are used to enrich the bank account data
    - some data fields are duplicated into the main transactions table for speed of lookup 
    - a relational link is made to the enrichment source table
  - LLM based inference enrichment
    - descriptive information about the transaction already enriched from LOOKUP sources (BUT NOT THE AMOUNT) is sent to an LLM for further enrichment by LLM Inference