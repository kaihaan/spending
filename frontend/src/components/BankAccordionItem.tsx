import AccountCard from './AccountCard';
import CardDisplay from './CardDisplay';

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

interface BankData {
  bank_name: string;
  provider_id: string;
  connection_id: number;
  connection_status: string;
  last_synced_at?: string | null;
  accounts: TrueLayerAccount[];
  cards: TrueLayerCard[];
}

interface Props {
  bank: BankData;
}

export default function BankAccordionItem({ bank }: Props) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'badge-success';
      case 'inactive':
        return 'badge-warning';
      case 'expired':
        return 'badge-error';
      default:
        return 'badge-ghost';
    }
  };

  const getStatusText = (status: string) => {
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  return (
    <div className="collapse collapse-arrow border border-base-300 bg-base-100">
      <input type="radio" name="bank-accordion" />
      <div className="collapse-title flex items-center justify-between p-4">
        <div className="flex items-center gap-3 flex-1">
          <div className="flex-1">
            <h3 className="font-semibold text-base">{bank.bank_name}</h3>
            <p className="text-sm text-base-content/60">
              {bank.accounts.length} accounts • {bank.cards.length} cards
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={`badge ${getStatusColor(bank.connection_status)}`}>
            {getStatusText(bank.connection_status)}
          </div>
        </div>
      </div>

      <div className="collapse-content px-4 py-4 space-y-6">
        {/* Accounts Section */}
        {bank.accounts.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h4 className="font-semibold text-sm">Accounts ({bank.accounts.length})</h4>
              <div className="flex-1 border-t border-base-300"></div>
            </div>
            <div className="space-y-2">
              {bank.accounts.map((account) => (
                <AccountCard key={account.id} account={account} />
              ))}
            </div>
          </div>
        )}

        {/* Cards Section */}
        {bank.cards.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h4 className="font-semibold text-sm">Cards ({bank.cards.length})</h4>
              <div className="flex-1 border-t border-base-300"></div>
            </div>
            <div className="space-y-2">
              {bank.cards.map((card) => (
                <CardDisplay key={card.id} card={card} />
              ))}
            </div>
          </div>
        )}

        {bank.accounts.length === 0 && bank.cards.length === 0 && (
          <div className="text-center text-base-content/50 py-4">
            No accounts or cards found
          </div>
        )}
      </div>
    </div>
  );
}
