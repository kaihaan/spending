"""
TrueLayer Mock Module for Local Testing

Simulates TrueLayer API responses for testing without external connectivity.
Use TRUELAYER_MOCK_MODE=true environment variable to enable.
"""

from datetime import datetime, timedelta
import uuid
from typing import Dict, List

# Mock bank providers
MOCK_PROVIDERS = {
    'barclays': 'Barclays Bank',
    'hsbc': 'HSBC',
    'lloyds': 'Lloyds Banking Group',
    'natwest': 'NatWest',
    'santander': 'Santander UK',
}

# Mock accounts per provider
MOCK_ACCOUNTS = {
    'barclays': [
        {
            'account_id': 'acc_barclays_1',
            'display_name': 'Barclays Current Account',
            'account_type': 'TRANSACTION',
            'account_subtype': 'SAVINGS',
            'currency': 'GBP',
        }
    ],
    'hsbc': [
        {
            'account_id': 'acc_hsbc_1',
            'display_name': 'HSBC Checking',
            'account_type': 'TRANSACTION',
            'account_subtype': 'CURRENT',
            'currency': 'GBP',
        }
    ],
    'natwest': [
        {
            'account_id': 'acc_natwest_1',
            'display_name': 'NatWest Premier Account',
            'account_type': 'TRANSACTION',
            'account_subtype': 'PREMIER',
            'currency': 'GBP',
        }
    ],
}


def mock_exchange_code_for_token(authorization_code: str, code_verifier: str) -> dict:
    """
    Mock OAuth token exchange response.
    Simulates TrueLayer's token endpoint response.
    """
    return {
        'access_token': f'mock_access_{uuid.uuid4().hex[:16]}',
        'refresh_token': f'mock_refresh_{uuid.uuid4().hex[:16]}',
        'expires_at': (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        'token_type': 'Bearer',
        'scope': 'accounts transactions balance',
    }


def mock_get_accounts(access_token: str) -> List[Dict]:
    """
    Mock get accounts response.
    Returns list of demo bank accounts.
    """
    return [
        {
            'account_id': 'acc_demo_1',
            'display_name': 'Demo Checking Account',
            'account_type': 'TRANSACTION',
            'account_subtype': 'CURRENT',
            'currency': 'GBP',
            'provider': 'barclays',
        },
        {
            'account_id': 'acc_demo_2',
            'display_name': 'Demo Savings Account',
            'account_type': 'SAVINGS',
            'account_subtype': 'ISA',
            'currency': 'GBP',
            'provider': 'hsbc',
        }
    ]


def mock_get_transactions(account_id: str, days_back: int = 90) -> List[Dict]:
    """
    Mock transaction fetch response.
    Returns realistic demo transactions for testing.
    """
    base_date = datetime.utcnow()
    transactions = []

    # Sample transaction descriptions
    descriptions = [
        {'desc': 'Tesco Stores 2145', 'merchant': 'Tesco', 'amount': 45.50, 'type': 'DEBIT'},
        {'desc': 'Amazon EU S.a.r.L', 'merchant': 'Amazon', 'amount': 29.99, 'type': 'DEBIT'},
        {'desc': 'Salary Deposit', 'merchant': 'Employer Ltd', 'amount': 2500.00, 'type': 'CREDIT'},
        {'desc': 'EDF Energy Bill', 'merchant': 'EDF Energy', 'amount': 120.30, 'type': 'DEBIT'},
        {'desc': 'Uber B.V', 'merchant': 'Uber', 'amount': 15.75, 'type': 'DEBIT'},
        {'desc': 'Tesco Stores 3421', 'merchant': 'Tesco', 'amount': 67.20, 'type': 'DEBIT'},
        {'desc': 'Sainsburys 5645', 'merchant': 'Sainsburys', 'amount': 38.45, 'type': 'DEBIT'},
        {'desc': 'Shell Petrol Station', 'merchant': 'Shell', 'amount': 60.00, 'type': 'DEBIT'},
        {'desc': 'Netflix Subscription', 'merchant': 'Netflix', 'amount': 14.99, 'type': 'DEBIT'},
        {'desc': 'Gym Direct Payment', 'merchant': 'Fitness First', 'amount': 45.00, 'type': 'DEBIT'},
    ]

    running_balance = 5000.00

    for i in range(min(50, days_back)):
        for j, desc_data in enumerate(descriptions[:3]):  # Multiple of same merchant
            txn_date = base_date - timedelta(days=i)
            amount = desc_data['amount']

            if desc_data['type'] == 'DEBIT':
                running_balance -= amount
            else:
                running_balance += amount

            transactions.append({
                'transaction_id': f'txn_{i}_{j}_{uuid.uuid4().hex[:8]}',
                'normalised_provider_transaction_id': f'norm_txn_{i}_{j}_{uuid.uuid4().hex[:8]}',
                'timestamp': txn_date.isoformat(),
                'description': desc_data['desc'],
                'merchant_name': desc_data['merchant'],
                'transaction_type': desc_data['type'],
                'amount': amount,
                'currency': 'GBP',
                'running_balance': running_balance,
                'transaction_category': None,
                'transaction_code': 'DEBIT' if desc_data['type'] == 'DEBIT' else 'CREDIT',
                'meta': {},
            })

    return transactions


def mock_get_balance(account_id: str) -> Dict:
    """
    Mock balance query response.
    Returns simulated account balance.
    """
    return {
        'currency': 'GBP',
        'current_balance': 4250.75,
        'available_balance': 4000.00,
        'overdraft_limit': 500.00,
    }


def mock_validate_authorization(state: str, code: str) -> bool:
    """
    Mock state validation.
    Always returns True for testing (in production, validate real state).
    """
    return bool(state and code)
