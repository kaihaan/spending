"""
Categories Service - Business Logic

Orchestrates category management including:
- Legacy v1 API: Category promotion, hiding, and spending summaries
- Normalized v2 API: Full CRUD for categories and subcategories
- Category-subcategory hierarchy management
- Cascade updates for name changes

Supports two API versions:
- v1: Legacy promotion/hiding system (preserved for backward compatibility)
- v2: Normalized category tables with foreign key relationships

Separates business logic from HTTP routing concerns.
"""

from database import categories as db_categories

# ============================================================================
# Legacy v1 Category API
# ============================================================================


def get_all_categories() -> list:
    """
    Get all categories (legacy v1 API).

    Returns:
        List of category dicts
    """
    return db_categories.get_all_categories()


def get_category_spending_summary(date_from: str = None, date_to: str = None) -> dict:
    """
    Get all categories with spending totals.

    Args:
        date_from: Optional start date filter (YYYY-MM-DD)
        date_to: Optional end date filter (YYYY-MM-DD)

    Returns:
        Dict with categories and hidden_categories lists
    """
    categories = db_categories.get_category_spending_summary(date_from, date_to)
    hidden_categories = db_categories.get_custom_categories(category_type="hidden")

    return {
        "categories": categories,
        "hidden_categories": [
            {"name": c["name"], "id": c["id"]} for c in hidden_categories
        ],
    }


def get_subcategory_spending(
    category_name: str, date_from: str = None, date_to: str = None
) -> dict:
    """
    Get subcategories for a specific category with spending totals.

    Args:
        category_name: Category name (URL-decoded)
        date_from: Optional start date filter
        date_to: Optional end date filter

    Returns:
        Dict with category name and subcategories list
    """
    subcategories = db_categories.get_subcategory_spending(
        category_name, date_from, date_to
    )

    return {"category": category_name, "subcategories": subcategories}


def promote_category(new_category_name: str, subcategories: list) -> dict:
    """
    Create a promoted category from selected subcategories.

    Args:
        new_category_name: Name for the new promoted category
        subcategories: List of subcategory patterns to promote

    Returns:
        Success dict with category_id and transactions_updated count

    Raises:
        ValueError: If validation fails
    """
    if not new_category_name:
        raise ValueError("new_category_name is required")

    if not subcategories:
        raise ValueError("At least one subcategory is required")

    result = db_categories.create_promoted_category(new_category_name, subcategories)

    return {
        "success": True,
        "category_id": result["category_id"],
        "transactions_updated": result["transactions_updated"],
        "message": f"Created category '{new_category_name}' and updated {result['transactions_updated']} transactions",
    }


def hide_category(category_name: str) -> dict:
    """
    Hide a category and reset its transactions for re-enrichment.

    Args:
        category_name: Category name to hide

    Returns:
        Success dict with category_id and transactions_reset count

    Raises:
        ValueError: If category_name missing
    """
    if not category_name:
        raise ValueError("category_name is required")

    result = db_categories.hide_category(category_name)

    return {
        "success": True,
        "category_id": result["category_id"],
        "transactions_reset": result["transactions_reset"],
        "message": f"Hidden category '{category_name}' and reset {result['transactions_reset']} transactions for re-enrichment",
    }


def unhide_category(category_name: str) -> dict:
    """
    Restore a hidden category.

    Args:
        category_name: Category name to restore

    Returns:
        Success dict or error if not found

    Raises:
        ValueError: If category_name missing or not found
    """
    if not category_name:
        raise ValueError("category_name is required")

    success = db_categories.unhide_category(category_name)

    if not success:
        raise ValueError(f"Category '{category_name}' was not found in hidden list")

    return {"success": True, "message": f"Category '{category_name}' has been restored"}


def get_custom_categories(category_type: str = None) -> dict:
    """
    Get all custom categories (promoted and hidden).

    Args:
        category_type: Optional filter - 'promoted', 'hidden', or None for all

    Returns:
        Dict with categories list
    """
    categories = db_categories.get_custom_categories(category_type=category_type)

    return {"categories": [dict(c) for c in categories]}


# ============================================================================
# Normalized v2 Categories API
# ============================================================================


def get_normalized_categories(
    active_only: bool = False, include_counts: bool = True
) -> dict:
    """
    Get all normalized categories with optional counts.

    Args:
        active_only: Filter to active categories only
        include_counts: Include transaction and subcategory counts

    Returns:
        Dict with categories list
    """
    categories = db_categories.get_normalized_categories(
        active_only=active_only, include_counts=include_counts
    )

    return {"categories": [dict(c) for c in categories]}


def get_normalized_category(category_id: int) -> dict:
    """
    Get a single normalized category with subcategories.

    Args:
        category_id: Category ID

    Returns:
        Dict with category data

    Raises:
        ValueError: If category not found
    """
    category = db_categories.get_normalized_category_by_id(category_id)

    if not category:
        raise ValueError("Category not found")

    return {"category": dict(category)}


def create_normalized_category(
    name: str, description: str = None, is_essential: bool = False, color: str = None
) -> dict:
    """
    Create a new normalized category.

    Args:
        name: Category name (required)
        description: Optional description
        is_essential: Whether category is essential (default: False)
        color: Optional color hex code

    Returns:
        Dict with created category

    Raises:
        ValueError: If name missing or category already exists
    """
    if not name:
        raise ValueError("Name is required")

    category = db_categories.create_normalized_category(
        name=name, description=description, is_essential=is_essential, color=color
    )

    if not category:
        raise ValueError("Category with this name already exists")

    return {"category": dict(category), "message": "Category created successfully"}


def update_normalized_category(
    category_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    is_essential: bool = None,
    color: str = None,
) -> dict:
    """
    Update a normalized category. Cascades name changes to all transactions.

    Args:
        category_id: Category ID to update
        name: New name (optional)
        description: New description (optional)
        is_active: Active status (optional)
        is_essential: Essential status (optional)
        color: Color hex code (optional)

    Returns:
        Dict with updated category and cascade counts

    Raises:
        ValueError: If category not found
    """
    result = db_categories.update_normalized_category(
        category_id=category_id,
        name=name,
        description=description,
        is_active=is_active,
        is_essential=is_essential,
        color=color,
    )

    if not result:
        raise ValueError("Category not found")

    return {
        "category": dict(result["category"]),
        "transactions_updated": result["transactions_updated"],
        "rules_updated": result["rules_updated"],
        "old_name": result.get("old_name"),
        "new_name": result.get("new_name"),
        "message": "Category updated successfully",
    }


def delete_normalized_category(
    category_id: int, reassign_to_category_id: int = None
) -> dict:
    """
    Delete a normalized category. System categories cannot be deleted.

    Args:
        category_id: Category ID to delete
        reassign_to_category_id: Optional category ID to reassign transactions to

    Returns:
        Dict with deletion results

    Raises:
        ValueError: If category not found or is system category
    """
    result = db_categories.delete_normalized_category(
        category_id=category_id, reassign_to_category_id=reassign_to_category_id
    )

    if not result:
        raise ValueError("Category not found")

    if result.get("error"):
        raise ValueError(result["error"])

    return {
        "deleted_category": result["deleted_category"],
        "transactions_reassigned": result["transactions_reassigned"],
        "message": "Category deleted successfully",
    }


# ============================================================================
# Normalized v2 Subcategories API
# ============================================================================


def get_normalized_subcategories(
    category_id: int = None, include_counts: bool = True
) -> dict:
    """
    Get all normalized subcategories, optionally filtered by category.

    Args:
        category_id: Optional category ID filter
        include_counts: Include transaction counts

    Returns:
        Dict with subcategories list
    """
    subcategories = db_categories.get_normalized_subcategories(
        category_id=category_id, include_counts=include_counts
    )

    return {"subcategories": [dict(s) for s in subcategories]}


def get_normalized_subcategory(subcategory_id: int) -> dict:
    """
    Get a single normalized subcategory.

    Args:
        subcategory_id: Subcategory ID

    Returns:
        Dict with subcategory data

    Raises:
        ValueError: If subcategory not found
    """
    subcategory = db_categories.get_normalized_subcategory_by_id(subcategory_id)

    if not subcategory:
        raise ValueError("Subcategory not found")

    return {"subcategory": dict(subcategory)}


def create_normalized_subcategory(
    category_id: int, name: str, description: str = None
) -> dict:
    """
    Create a new normalized subcategory under a category.

    Args:
        category_id: Parent category ID
        name: Subcategory name (required)
        description: Optional description

    Returns:
        Dict with created subcategory

    Raises:
        ValueError: If name missing, category not found, or subcategory already exists
    """
    if not name:
        raise ValueError("Name is required")

    # Verify category exists
    category = db_categories.get_normalized_category_by_id(category_id)
    if not category:
        raise ValueError("Category not found")

    subcategory = db_categories.create_normalized_subcategory(
        category_id=category_id, name=name, description=description
    )

    if not subcategory:
        raise ValueError("Subcategory with this name already exists in this category")

    return {
        "subcategory": dict(subcategory),
        "message": "Subcategory created successfully",
    }


def update_normalized_subcategory(
    subcategory_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    category_id: int = None,
) -> dict:
    """
    Update a normalized subcategory. Cascades name changes to transactions.

    Args:
        subcategory_id: Subcategory ID to update
        name: New name (optional)
        description: New description (optional)
        is_active: Active status (optional)
        category_id: New parent category ID for moving (optional)

    Returns:
        Dict with updated subcategory and cascade counts

    Raises:
        ValueError: If subcategory not found
    """
    result = db_categories.update_normalized_subcategory(
        subcategory_id=subcategory_id,
        name=name,
        description=description,
        is_active=is_active,
        category_id=category_id,
    )

    if not result:
        raise ValueError("Subcategory not found")

    return {
        "subcategory": dict(result["subcategory"]),
        "transactions_updated": result["transactions_updated"],
        "old_name": result.get("old_name"),
        "new_name": result.get("new_name"),
        "message": "Subcategory updated successfully",
    }


def delete_normalized_subcategory(subcategory_id: int) -> dict:
    """
    Delete a normalized subcategory.

    Args:
        subcategory_id: Subcategory ID to delete

    Returns:
        Dict with deletion results

    Raises:
        ValueError: If subcategory not found
    """
    result = db_categories.delete_normalized_subcategory(subcategory_id)

    if not result:
        raise ValueError("Subcategory not found")

    return {
        "deleted_subcategory": result["deleted_subcategory"],
        "category_name": result["category_name"],
        "transactions_cleared": result["transactions_cleared"],
        "message": "Subcategory deleted successfully",
    }
