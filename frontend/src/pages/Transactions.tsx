import TransactionList from '../components/TransactionList';

export default function Transactions() {
  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <h2 className="card-title text-2xl">💳 Transactions</h2>
          <p className="text-sm text-base-content/70 mb-4">
            View and filter all transactions from imported bank statements
          </p>
          <TransactionList />
        </div>
      </div>
    </div>
  );
}
