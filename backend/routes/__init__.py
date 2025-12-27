"""Routes package for API endpoints."""

from routes.amazon import amazon_bp, amazon_business_bp
from routes.apple import apple_bp
from routes.auth import auth_bp
from routes.categories import categories_v1_bp, categories_v2_bp, subcategories_v2_bp
from routes.direct_debit import direct_debit_bp
from routes.enrichment import enrichment_bp
from routes.gmail import gmail_bp
from routes.huququllah import huququllah_bp
from routes.matching import matching_bp
from routes.migrations import migrations_bp
from routes.rules import rules_bp
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.truelayer import truelayer_bp
from routes.utilities import utilities_bp

__all__ = [
    "auth_bp",
    "gmail_bp",
    "truelayer_bp",
    "amazon_bp",
    "amazon_business_bp",
    "enrichment_bp",
    "rules_bp",
    "apple_bp",
    "transactions_bp",
    "categories_v1_bp",
    "categories_v2_bp",
    "subcategories_v2_bp",
    "huququllah_bp",
    "direct_debit_bp",
    "matching_bp",
    "settings_bp",
    "migrations_bp",
    "utilities_bp",
]
