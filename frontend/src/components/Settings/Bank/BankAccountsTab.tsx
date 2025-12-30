/**
 * BankAccountsTab Component
 *
 * Contains the existing bank account management functionality:
 * - TrueLayer account linking and sync
 * - Account mappings (friendly names for accounts)
 */

import TrueLayerIntegration from '../../TrueLayerIntegration';
import AccountMappings from '../../AccountMappings';

export default function BankAccountsTab() {
  return (
    <div className="space-y-8">
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body">
          <TrueLayerIntegration />
        </div>
      </div>
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body">
          <AccountMappings />
        </div>
      </div>
    </div>
  );
}
