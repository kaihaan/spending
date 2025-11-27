interface TrueLayerAccount {
  id: number;
  account_id: string;
  display_name: string;
  account_type: string;
  currency: string;
  last_synced_at?: string | null;
}

interface Props {
  account: TrueLayerAccount;
}

export default function AccountCard({ account }: Props) {
  const formatTimestamp = (timestamp: string | null | undefined): string => {
    if (!timestamp) return 'Never';

    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  };

  const getSyncIndicatorColor = (timestamp: string | null | undefined): string => {
    if (!timestamp) return 'text-error';

    const date = new Date(timestamp);
    const now = new Date();
    const diffHours = (now.getTime() - date.getTime()) / 3600000;

    if (diffHours < 24) return 'text-success';
    if (diffHours < 72) return 'text-warning';
    return 'text-error';
  };

  const getAccountTypeDisplay = (type: string): string => {
    const typeMap: { [key: string]: string } = {
      'TRANSACTION_ACCOUNT': 'Transaction',
      'SAVINGS_ACCOUNT': 'Savings',
      'CREDIT_CARD': 'Credit Card',
      'INVESTMENT_ACCOUNT': 'Investment',
      'LOAN_ACCOUNT': 'Loan',
      'MORTGAGE_ACCOUNT': 'Mortgage',
      'CARD': 'Card',
    };
    return typeMap[type] || type;
  };

  return (
    <div className="card bg-base-200 shadow-sm hover:shadow-md transition-shadow">
      <div className="card-body p-3 gap-2">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <h5 className="font-semibold text-sm">{account.display_name}</h5>
            <p className="text-xs text-base-content/60">{getAccountTypeDisplay(account.account_type)}</p>
          </div>
          <div className={`text-xl ${getSyncIndicatorColor(account.last_synced_at)}`}>
            <span className="tooltip" data-tip={`Last synced: ${formatTimestamp(account.last_synced_at)}`}>
              ●
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="badge badge-sm badge-neutral">{account.currency}</div>
          <span className="text-xs text-base-content/60">
            {formatTimestamp(account.last_synced_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
