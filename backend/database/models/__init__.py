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
from .category import Category, CategoryKeyword
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
from .user import User

__all__ = [
    "User",
    "Category",
    "CategoryKeyword",
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
]
