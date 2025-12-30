# backend/database/models/__init__.py
"""SQLAlchemy models for all database tables."""

from .amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonDigitalOrder,
    AmazonOrder,
    AmazonReturn,
    TrueLayerAmazonTransactionMatch,
)
from .apple import AppleTransaction, TrueLayerAppleTransactionMatch
from .category import (
    Category,
    CategoryKeyword,
    CategoryRule,
    CustomCategory,
    MatchingJob,
    MerchantNormalization,
    NormalizedCategory,
    NormalizedSubcategory,
    SubcategoryMapping,
)
from .enrichment import (
    EnrichmentCache,
    LLMEnrichmentResult,
    RuleEnrichmentResult,
    TransactionEnrichmentSource,
)
from .gmail import (
    GmailConnection,
    GmailEmailContent,
    GmailReceipt,
    PDFAttachment,
)
from .truelayer import (
    BankConnection,
    OAuthState,
    TrueLayerAccount,
    TrueLayerBalance,
    TrueLayerCard,
    TrueLayerCardBalanceSnapshot,
    TrueLayerCardTransaction,
    TrueLayerEnrichmentJob,
    TrueLayerImportJob,
    TrueLayerImportProgress,
    TrueLayerTransaction,
    WebhookEvent,
)
from .user import AccountMapping, User

__all__ = [
    "User",
    "AccountMapping",
    "Category",
    "CategoryKeyword",
    "CategoryRule",
    "CustomCategory",
    "MerchantNormalization",
    "MatchingJob",
    "NormalizedCategory",
    "NormalizedSubcategory",
    "SubcategoryMapping",
    "BankConnection",
    "TrueLayerAccount",
    "TrueLayerTransaction",
    "TrueLayerBalance",
    "WebhookEvent",
    "OAuthState",
    "TrueLayerCard",
    "TrueLayerCardTransaction",
    "TrueLayerCardBalanceSnapshot",
    "TrueLayerImportJob",
    "TrueLayerImportProgress",
    "TrueLayerEnrichmentJob",
    "AmazonOrder",
    "AmazonReturn",
    "AmazonDigitalOrder",
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
    "RuleEnrichmentResult",
    "LLMEnrichmentResult",
]
