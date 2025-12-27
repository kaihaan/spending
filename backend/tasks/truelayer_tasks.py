"""Celery tasks for TrueLayer transaction synchronization."""

from datetime import datetime

import database_postgres as db
from celery_app import celery_app


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def sync_truelayer_task(
    self,
    user_id: int = 1,
    connection_id: int = None,
    date_from: str = None,
    date_to: str = None,
):
    """
    Celery task to sync TrueLayer transactions in the background.

    Args:
        user_id: User ID to sync transactions for
        connection_id: Optional specific connection to sync (if None, syncs all)
        date_from: ISO format start date (YYYY-MM-DD, optional)
        date_to: ISO format end date (YYYY-MM-DD, optional)

    Progress states:
        - 'started': Task initiated
        - 'syncing': Processing accounts
        - 'completed': All accounts synced
        - 'failed': Error occurred

    Returns:
        dict: Sync statistics
    """
    try:
        from mcp.truelayer_sync import sync_all_accounts

        # Initial state
        self.update_state(
            state="STARTED",
            meta={
                "status": "initializing",
                "user_id": user_id,
                "connection_id": connection_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

        # Get connection count for progress tracking
        if connection_id:
            conn = db.get_connection(connection_id)
            if not conn:
                return {"status": "failed", "error": "Connection not found"}
            connections = [conn]
        else:
            connections = db.get_user_connections(user_id)

        if not connections:
            return {
                "status": "completed",
                "stats": {
                    "total_accounts": 0,
                    "total_synced": 0,
                    "total_duplicates": 0,
                    "total_errors": 0,
                },
                "message": "No connections found for user",
            }

        # Count total accounts
        total_accounts = 0
        for conn in connections:
            accounts = db.get_connection_accounts(conn["id"])
            total_accounts += len(accounts)

        # Update progress - syncing started
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "syncing",
                "user_id": user_id,
                "connection_id": connection_id,
                "total_accounts": total_accounts,
                "accounts_processed": 0,
                "transactions_synced": 0,
                "duplicates": 0,
                "errors": 0,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

        # Execute sync
        result = sync_all_accounts(
            user_id=user_id, date_from=date_from, date_to=date_to
        )

        # Final progress update with results
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "completed",
                "user_id": user_id,
                "connection_id": connection_id,
                "total_accounts": result.get("total_accounts", 0),
                "accounts_processed": result.get("total_accounts", 0),
                "transactions_synced": result.get("total_synced", 0),
                "duplicates": result.get("total_duplicates", 0),
                "errors": result.get("total_errors", 0),
                "date_from": date_from,
                "date_to": date_to,
            },
        )

        return {
            "status": "completed",
            "stats": {
                "total_accounts": result.get("total_accounts", 0),
                "total_synced": result.get("total_synced", 0),
                "total_duplicates": result.get("total_duplicates", 0),
                "total_errors": result.get("total_errors", 0),
            },
            "accounts": result.get("accounts", []),
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Log error and return failure status
        import traceback

        error_details = traceback.format_exc()
        print(f"❌ TrueLayer sync task failed: {e}")
        print(error_details)

        return {
            "status": "failed",
            "error": str(e),
            "error_details": error_details,
            "user_id": user_id,
            "connection_id": connection_id,
        }


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def sync_truelayer_account_task(
    self, account_id: int, date_from: str = None, date_to: str = None
):
    """
    Celery task to sync transactions for a specific TrueLayer account.

    Args:
        account_id: Database account ID (not TrueLayer account ID)
        date_from: ISO format start date (YYYY-MM-DD, optional)
        date_to: ISO format end date (YYYY-MM-DD, optional)

    Returns:
        dict: Sync statistics for the account
    """
    try:
        from mcp.truelayer_sync import sync_account_transactions

        self.update_state(
            state="STARTED",
            meta={
                "status": "initializing",
                "account_id": account_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

        # Execute sync for single account
        result = sync_account_transactions(
            account_id=account_id, from_date=date_from, to_date=date_to
        )

        return {
            "status": "completed",
            "stats": {
                "synced": result.get("synced", 0),
                "duplicates": result.get("duplicates", 0),
                "errors": result.get("errors", 0),
            },
            "account_id": account_id,
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"❌ TrueLayer account sync task failed: {e}")
        print(error_details)

        return {
            "status": "failed",
            "error": str(e),
            "error_details": error_details,
            "account_id": account_id,
        }
