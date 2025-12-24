import TransactionList from '../components/TransactionList';

export default function Transactions() {
  return (
    <div className="container mx-auto p-4 pr-12">{/* Extra right padding for gear tab */}
      <div className="card bg-base-200 shadow-xl overflow-visible">
        <div className="card-body overflow-visible">
          <TransactionList />
        </div>
      </div>
    </div>
  );
}
