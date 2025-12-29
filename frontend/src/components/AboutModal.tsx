/**
 * AboutModal Component
 *
 * Simple modal explaining what the app does and why it's valuable.
 * Written in plain, accessible language.
 */

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function AboutModal({ isOpen, onClose }: AboutModalProps) {
  if (!isOpen) return null;

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-lg">
        <h3 className="font-bold text-xl mb-4">About This App</h3>

        <div className="space-y-4 text-base-content/90">
          <section>
            <h4 className="font-semibold text-primary mb-1">What does it do?</h4>
            <p>
              This app helps you understand where your money goes. It connects
              to your bank and automatically brings in all your transactions,
              then figures out what each one was for.
            </p>
          </section>

          <section>
            <h4 className="font-semibold text-primary mb-1">Why is that helpful?</h4>
            <p>
              Bank statements are often confusing. Instead of seeing "AMZN*123XY",
              you'll see "Amazon - Headphones". Instead of guessing categories,
              the app uses AI to sort everything for you.
            </p>
          </section>

          <section>
            <h4 className="font-semibold text-primary mb-1">What else can it do?</h4>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Match bank charges to Amazon orders and Apple purchases</li>
              <li>Pull receipts from your Gmail inbox</li>
              <li>Show spending trends over time</li>
              <li>Calculate Huququllah (for Baha'is)</li>
            </ul>
          </section>

          <section>
            <h4 className="font-semibold text-primary mb-1">Is my data safe?</h4>
            <p>
              Yes. Everything stays on your own computer. Your bank data is
              never uploaded anywhere. Only you can see it.
            </p>
          </section>
        </div>

        <div className="modal-action">
          <button className="btn btn-primary" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
