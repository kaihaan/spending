"""Authentication and multi-user data isolation tests.

Tests the authentication system including:
- User registration
- User login and logout
- Route protection
- Multi-user data isolation
"""

import cache_manager
from sqlalchemy import text


def test_user_registration(client, db_session):
    """Test user registration endpoint."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "test_register@test.com",
            "password": "testpass123",
            "username": "testuser",
        },
    )

    assert response.status_code == 201
    data = response.json
    assert data["success"] is True
    assert "user" in data
    assert data["user"]["email"] == "test_register@test.com"
    assert data["user"]["username"] == "testuser"


def test_user_login(client, db_session):
    """Test user login endpoint."""
    # First register a user
    client.post(
        "/api/auth/register",
        json={
            "email": "test_login@test.com",
            "password": "testpass123",
            "username": "loginuser",
        },
    )

    # Logout
    client.post("/api/auth/logout")

    # Now login (use username, not email - login endpoint expects username)
    response = client.post(
        "/api/auth/login", json={"username": "loginuser", "password": "testpass123"}
    )

    assert response.status_code == 200
    data = response.json
    assert data["success"] is True
    assert "user" in data
    assert data["user"]["email"] == "test_login@test.com"


def test_user_logout(client, db_session):
    """Test user logout endpoint."""
    # Register and login a user
    client.post(
        "/api/auth/register",
        json={
            "email": "test_logout@test.com",
            "password": "testpass123",
            "username": "logoutuser",
        },
    )

    # Logout
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    data = response.json
    assert data["success"] is True


def test_route_protection(client, db_session):
    """Test that protected routes require authentication."""
    # Try to access protected route without auth
    response = client.get("/api/transactions")

    assert response.status_code == 401
    data = response.json
    assert "error" in data or "message" in data


def test_multi_user_data_isolation(client, clean_db):
    """CRITICAL: Verify users only see their own data.

    This test ensures that:
    1. User 1 can create transactions
    2. User 2 sees ZERO transactions (not User 1's data)
    3. User 1's data is still intact after User 2 registers

    Note: Uses clean_db fixture to ensure clean state before test.
    """
    # clean_db fixture truncates all tables in correct order (handles FK constraints)

    # ========== USER 1: Create and add data ==========
    user1_resp = client.post(
        "/api/auth/register",
        json={
            "email": "user1_isolation@test.com",
            "password": "password123",
            "username": "user1",
        },
    )

    assert user1_resp.status_code == 201
    user1_id = user1_resp.json["user"]["id"]

    # Add a TrueLayer transaction for user1 (simulating real data)
    # Note: We need to create the full hierarchy: connection → account → transaction

    # Step 1: Create bank connection for user1
    clean_db.execute(
        text("""
        INSERT INTO bank_connections (
            user_id, provider_id, provider_name, connection_status
        ) VALUES (
            :user_id, :provider_id, :provider_name, :connection_status
        )
    """),
        {
            "user_id": user1_id,
            "provider_id": "test_provider_user1",
            "provider_name": "Test Bank User1",
            "connection_status": "active",
        },
    )
    clean_db.commit()

    # Get the connection ID
    connection_result = clean_db.execute(
        text("""
        SELECT id FROM bank_connections WHERE user_id = :user_id
    """),
        {"user_id": user1_id},
    )
    connection_id = connection_result.scalar()

    # Step 2: Create TrueLayer account
    clean_db.execute(
        text("""
        INSERT INTO truelayer_accounts (
            connection_id, account_id, account_type, display_name, currency
        ) VALUES (
            :connection_id, :account_id, :account_type, :display_name, :currency
        )
    """),
        {
            "connection_id": connection_id,
            "account_id": "test_account_user1",
            "account_type": "TRANSACTION",
            "display_name": "Test Account User1",
            "currency": "GBP",
        },
    )
    clean_db.commit()

    # Get the account ID (internal ID, not account_id string)
    account_result = clean_db.execute(
        text("""
        SELECT id FROM truelayer_accounts WHERE account_id = :account_id
    """),
        {"account_id": "test_account_user1"},
    )
    account_internal_id = account_result.scalar()

    # Step 3: Create transaction
    clean_db.execute(
        text("""
        INSERT INTO truelayer_transactions (
            account_id, transaction_id, normalised_provider_transaction_id,
            description, amount, currency, timestamp, transaction_type, merchant_name
        ) VALUES (
            :account_id, :transaction_id, :normalised_id, :description,
            :amount, :currency, NOW(), :transaction_type, :merchant_name
        )
    """),
        {
            "account_id": account_internal_id,
            "transaction_id": "test_txn_user1_001",
            "normalised_id": "TEST_USER1_001",
            "description": "Test Transaction User 1",
            "amount": -50.00,
            "currency": "GBP",
            "transaction_type": "DEBIT",
            "merchant_name": "Test Merchant",
        },
    )
    clean_db.commit()

    # Clear the transactions cache (direct SQL bypasses normal cache invalidation)
    cache_manager.cache_delete_pattern("transactions:*")

    # Verify user1 sees their transaction
    response = client.get("/api/transactions")
    assert response.status_code == 200
    user1_transactions = response.json  # API returns list directly
    assert len(user1_transactions) >= 1
    assert any(
        t["description"] == "Test Transaction User 1" for t in user1_transactions
    )

    # ========== LOGOUT USER 1 ==========
    client.post("/api/auth/logout")

    # ========== USER 2: Register and verify empty state ==========
    user2_resp = client.post(
        "/api/auth/register",
        json={
            "email": "user2_isolation@test.com",
            "password": "password123",
            "username": "user2",
        },
    )

    assert user2_resp.status_code == 201
    user2_id = user2_resp.json["user"]["id"]

    # CRITICAL: User 2 should see ZERO transactions
    response = client.get("/api/transactions")
    assert response.status_code == 200
    user2_transactions = response.json  # API returns list directly
    assert (
        len(user2_transactions) == 0
    ), f"User 2 should see 0 transactions but sees {len(user2_transactions)}!"

    # Add a transaction for user2 (same hierarchy)

    # Step 1: Create bank connection for user2
    clean_db.execute(
        text("""
        INSERT INTO bank_connections (
            user_id, provider_id, provider_name, connection_status
        ) VALUES (
            :user_id, :provider_id, :provider_name, :connection_status
        )
    """),
        {
            "user_id": user2_id,
            "provider_id": "test_provider_user2",
            "provider_name": "Test Bank User2",
            "connection_status": "active",
        },
    )
    clean_db.commit()

    # Get the connection ID
    connection2_result = clean_db.execute(
        text("""
        SELECT id FROM bank_connections WHERE user_id = :user_id
    """),
        {"user_id": user2_id},
    )
    connection2_id = connection2_result.scalar()

    # Step 2: Create TrueLayer account
    clean_db.execute(
        text("""
        INSERT INTO truelayer_accounts (
            connection_id, account_id, account_type, display_name, currency
        ) VALUES (
            :connection_id, :account_id, :account_type, :display_name, :currency
        )
    """),
        {
            "connection_id": connection2_id,
            "account_id": "test_account_user2",
            "account_type": "TRANSACTION",
            "display_name": "Test Account User2",
            "currency": "GBP",
        },
    )
    clean_db.commit()

    # Get the account ID
    account2_result = clean_db.execute(
        text("""
        SELECT id FROM truelayer_accounts WHERE account_id = :account_id
    """),
        {"account_id": "test_account_user2"},
    )
    account2_internal_id = account2_result.scalar()

    # Step 3: Create transaction
    clean_db.execute(
        text("""
        INSERT INTO truelayer_transactions (
            account_id, transaction_id, normalised_provider_transaction_id,
            description, amount, currency, timestamp, transaction_type, merchant_name
        ) VALUES (
            :account_id, :transaction_id, :normalised_id, :description,
            :amount, :currency, NOW(), :transaction_type, :merchant_name
        )
    """),
        {
            "account_id": account2_internal_id,
            "transaction_id": "test_txn_user2_001",
            "normalised_id": "TEST_USER2_001",
            "description": "Test Transaction User 2",
            "amount": -30.00,
            "currency": "GBP",
            "transaction_type": "DEBIT",
            "merchant_name": "Another Merchant",
        },
    )
    clean_db.commit()

    # Clear the transactions cache (direct SQL bypasses normal cache invalidation)
    cache_manager.cache_delete_pattern("transactions:*")

    # Verify user2 sees only their transaction
    response = client.get("/api/transactions")
    assert response.status_code == 200
    user2_transactions = response.json  # API returns list directly
    assert len(user2_transactions) == 1
    assert user2_transactions[0]["description"] == "Test Transaction User 2"

    # ========== LOGOUT USER 2, LOGIN USER 1 ==========
    client.post("/api/auth/logout")

    # Login uses username, not email
    client.post(
        "/api/auth/login", json={"username": "user1", "password": "password123"}
    )

    # CRITICAL: User 1 should still see their original transaction
    response = client.get("/api/transactions")
    assert response.status_code == 200
    user1_transactions = response.json  # API returns list directly
    assert len(user1_transactions) >= 1
    assert any(
        t["description"] == "Test Transaction User 1" for t in user1_transactions
    )
    # User 1 should NOT see user 2's transaction
    assert not any(
        t["description"] == "Test Transaction User 2" for t in user1_transactions
    )

    print("\n✅ Multi-user data isolation test PASSED!")
    print(
        f"   User 1: {len([t for t in user1_transactions if 'User 1' in t['description']])} transactions"
    )
    print("   User 2: 1 transaction (verified separately)")
    print("   No cross-contamination detected")
