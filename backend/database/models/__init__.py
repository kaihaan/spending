# backend/database/models/__init__.py
"""SQLAlchemy models for all database tables."""

from .amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonOrder,
    AmazonReturn,
    TrueLayerAmazonTransactionMatch,
)
from .apple import AppleTransaction, TrueLayerAppleTransactionMatch
from .category import (
    Category,
    CategoryKeyword,
    CategoryRule,
    MatchingJob,
    MerchantNormalization,
)
from .enrichment import EnrichmentCache, TransactionEnrichmentSource
from .gmail import (
    GmailConnection,
    GmailEmailContent,
    GmailReceipt,
    PDFAttachment,
)
from .truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerBalance,
    TrueLayerTransaction,
)
from .user import AccountMapping, User

__all__ = [
    "User",
    "AccountMapping",
    "Category",
    "CategoryKeyword",
    "CategoryRule",
    "MerchantNormalization",
    "MatchingJob",
    "BankConnection",
    "TrueLayerAccount",
    "TrueLayerTransaction",
    "TrueLayerBalance",
    "AmazonOrder",
    "AmazonReturn",
    "AmazonBusinessConnection",
    "AmazonBusinessOrder",
    "AmazonBusinessLineItem",
    "TrueLayerAmazonTransactionMatch",
    "AppleTransaction",
    "TrueLayerAppleTransactionMatch",
    "GmailConnection",
    "GmailReceipt",
    "GmailEmailContent",
    "PDFAttachment",
    "TransactionEnrichmentSource",
    "EnrichmentCache",
]
