import { useState, useEffect } from 'react';
import axios from 'axios';
import BankAccordionItem from './BankAccordionItem';

const API_URL = 'http://localhost:5000/api';

interface TrueLayerAccount {
  id: number;
  account_id: string;
  display_name: string;
  account_type: string;
  currency: string;
  last_synced_at?: string | null;
}

interface TrueLayerCard {
  id: number;
  card_id: string;
  card_name: string;
  card_type: string;
  last_four?: string;
  issuer?: string;
  last_synced_at?: string | null;
}

interface TrueLayerConnection {
  id: number;
  connection_id: number;
  provider_id: string;
  connection_status: string;
  last_synced_at?: string | null;
  accounts?: TrueLayerAccount[];
}

interface CardsConnection {
  user_id: number;
  connections: {
    connection_id: number;
    provider_id: string;
    connection_status: string;
    last_synced_at?: string | null;
    cards: TrueLayerCard[];
  }[];
}

interface BankData {
  bank_name: string;
  provider_id: string;
  connection_id: number;
  connection_status: string;
  last_synced_at?: string | null;
  accounts: TrueLayerAccount[];
  cards: TrueLayerCard[];
}

export default function BankIntegrationDetails() {
  const [banks, setBanks] = useState<BankData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchBankDetails();

    // Listen for bank connection/sync updates
    const handleBankConnected = () => {
      fetchBankDetails();
    };

    window.addEventListener('bank-connected', handleBankConnected);
    window.addEventListener('transactions-updated', handleBankConnected);

    return () => {
      window.removeEventListener('bank-connected', handleBankConnected);
      window.removeEventListener('transactions-updated', handleBankConnected);
    };
  }, []);

  const fetchBankDetails = async () => {
    try {
      setError(null);
      // Fetch accounts
      const accountsRes = await axios.get<{ connections: TrueLayerConnection[] }>(
        `${API_URL}/truelayer/accounts`
      );

      // Fetch cards
      const cardsRes = await axios.get<CardsConnection>(
        `${API_URL}/truelayer/cards`
      );

      // Combine data by connection
      const bankMap = new Map<number, BankData>();

      // Add accounts
      if (accountsRes.data.connections) {
        for (const conn of accountsRes.data.connections) {
          const connectionId = conn.id;
          if (!bankMap.has(connectionId)) {
            bankMap.set(connectionId, {
              bank_name: conn.provider_id === 'truelayer' ? 'TrueLayer Bank' : conn.provider_id,
              provider_id: conn.provider_id,
              connection_id: connectionId,
              connection_status: conn.connection_status,
              last_synced_at: conn.last_synced_at,
              accounts: conn.accounts || [],
              cards: []
            });
          } else {
            const bank = bankMap.get(connectionId)!;
            bank.accounts = conn.accounts || [];
          }
        }
      }

      // Add cards
      if (cardsRes.data.connections) {
        for (const conn of cardsRes.data.connections) {
          const connectionId = conn.connection_id;
          if (!bankMap.has(connectionId)) {
            bankMap.set(connectionId, {
              bank_name: conn.provider_id === 'truelayer' ? 'TrueLayer Bank' : conn.provider_id,
              provider_id: conn.provider_id,
              connection_id: connectionId,
              connection_status: conn.connection_status,
              last_synced_at: conn.last_synced_at,
              accounts: [],
              cards: conn.cards || []
            });
          } else {
            const bank = bankMap.get(connectionId)!;
            bank.cards = conn.cards || [];
          }
        }
      }

      const banksArray = Array.from(bankMap.values());
      setBanks(banksArray);
    } catch (err) {
      console.error('Failed to fetch bank details:', err);
      setError('Failed to load bank integration details');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshAccounts = async () => {
    try {
      setRefreshing(true);
      setError(null);

      // Trigger account sync
      await axios.post(`${API_URL}/truelayer/fetch-accounts`, {
        user_id: 1
      });

      // Trigger card sync
      await axios.post(`${API_URL}/truelayer/fetch-cards`, {
        user_id: 1
      });

      // Refresh the display
      await fetchBankDetails();
    } catch (err) {
      console.error('Failed to refresh accounts:', err);
      setError('Failed to refresh account and card list');
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  const totalAccounts = banks.reduce((sum, bank) => sum + bank.accounts.length, 0);
  const totalCards = banks.reduce((sum, bank) => sum + bank.cards.length, 0);

  return (
    <div className="space-y-4">
      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      {banks.length === 0 ? (
        <div className="alert alert-info">
          <span>No connected banks found. Connect a bank to see accounts and cards here.</span>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <div className="flex gap-4 text-sm">
              <div className="badge badge-primary">{totalAccounts} Accounts</div>
              <div className="badge badge-secondary">{totalCards} Cards</div>
            </div>
            <button
              className="btn btn-sm btn-outline"
              onClick={handleRefreshAccounts}
              disabled={refreshing}
            >
              {refreshing ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Refreshing...
                </>
              ) : (
                'Refresh Accounts & Cards'
              )}
            </button>
          </div>

          <div className="join join-vertical w-full">
            {banks.map((bank, index) => (
              <BankAccordionItem key={bank.connection_id} bank={bank} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
