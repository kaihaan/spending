import TrueLayerIntegration from '../TrueLayerIntegration';
import AccountMappings from '../AccountMappings';

export default function BankTab() {
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
