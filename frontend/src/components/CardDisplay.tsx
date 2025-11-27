interface TrueLayerCard {
  id: number;
  card_id: string;
  card_name: string;
  card_type: string;
  last_four?: string;
  issuer?: string;
  last_synced_at?: string | null;
}

interface Props {
  card: TrueLayerCard;
}

export default function CardDisplay({ card }: Props) {
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

  const getCardTypeDisplay = (type: string): string => {
    const typeMap: { [key: string]: string } = {
      'CREDIT_CARD': 'Credit Card',
      'DEBIT_CARD': 'Debit Card',
      'PREPAID_CARD': 'Prepaid Card',
      'CHARGE_CARD': 'Charge Card',
    };
    return typeMap[type] || type;
  };

  return (
    <div className="card bg-base-200 shadow-sm hover:shadow-md transition-shadow">
      <div className="card-body p-3 gap-2">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <h5 className="font-semibold text-sm">{card.card_name}</h5>
            <p className="text-xs text-base-content/60">{getCardTypeDisplay(card.card_type)}</p>
          </div>
          <div className={`text-xl ${getSyncIndicatorColor(card.last_synced_at)}`}>
            <span className="tooltip" data-tip={`Last synced: ${formatTimestamp(card.last_synced_at)}`}>
              ●
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {card.last_four && (
            <div className="badge badge-sm badge-neutral">•••• {card.last_four}</div>
          )}
          {card.issuer && (
            <div className="badge badge-sm badge-outline">{card.issuer}</div>
          )}
          <span className="text-xs text-base-content/60 ml-auto">
            {formatTimestamp(card.last_synced_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
