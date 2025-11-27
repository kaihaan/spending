#!/usr/bin/env python3
"""Debug script to test sync directly and see actual errors."""

import sys
import os

# Add backend to path
sys.path.insert(0, '/mnt/c/dev/spending/backend')
os.chdir('/mnt/c/dev/spending/backend')

# Load env vars
from dotenv import load_dotenv
load_dotenv(override=True)

import database_postgres as database
from mcp.truelayer_sync import sync_account_transactions
from mcp.truelayer_auth import decrypt_token

# Test with connection 3, account 3 (the one with errors)
connection_id = 3
account_id = 3  # db id
truelayer_account_id = "99870992ed72f10af5ce9fa3534b91a0"

print("=" * 60)
print(f"Testing sync for account: {truelayer_account_id}")
print("=" * 60)

try:
    # Get connection
    connection = database.get_connection(connection_id)
    print(f"Connection found: {connection['id']}")
    print(f"Token expires at: {connection['token_expires_at']}")

    # Try to decrypt token
    encrypted_token = connection['access_token']
    print(f"Encrypted token length: {len(encrypted_token)}")

    try:
        access_token = decrypt_token(encrypted_token)
        print(f"✅ Token decrypted successfully ({len(access_token)} chars)")
    except Exception as e:
        print(f"❌ Token decryption failed: {e}")
        sys.exit(1)

    # Run sync for this specific account
    print(f"\nSyncing account {truelayer_account_id}...")
    result = sync_account_transactions(
        connection_id=connection_id,
        truelayer_account_id=truelayer_account_id,
        db_account_id=account_id,
        access_token=access_token,
        days_back=90
    )

    print(f"\nSync Result:")
    print(f"  Synced: {result.get('synced_count', 0)}")
    print(f"  Duplicates: {result.get('duplicate_count', 0)}")
    print(f"  Errors: {result.get('error_count', 0)}")
    print(f"  Total processed: {result.get('total_processed', 0)}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ Test completed successfully!")
