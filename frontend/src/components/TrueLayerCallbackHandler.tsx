import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

export default function TrueLayerCallbackHandler() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [message, setMessage] = useState('Processing authorization...');

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // Backend has already processed the OAuth callback and redirected here with results
        const statusParam = searchParams.get('status');
        const error = searchParams.get('error');
        const connectionId = searchParams.get('connection_id');

        if (error) {
          setStatus('error');
          setMessage(`Authorization failed: ${error}`);
          return;
        }

        if (statusParam === 'authorized' && connectionId) {
          setStatus('success');
          setMessage('Bank account connected successfully! Redirecting...');

          // Clear stored sessionStorage values
          sessionStorage.removeItem('truelayer_state');
          sessionStorage.removeItem('truelayer_code_verifier');

          // Redirect to settings after 2 seconds
          setTimeout(() => {
            navigate('/settings?tab=truelayer');
            window.dispatchEvent(new Event('bank-connected'));
          }, 2000);
        } else {
          setStatus('error');
          setMessage('Failed to authorize bank account');
        }
      } catch (err: any) {
        setStatus('error');
        setMessage(
          err.message ||
          'An error occurred during authorization'
        );
        console.error('OAuth callback error:', err);
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="card bg-base-200 shadow-xl max-w-md w-full">
        <div className="card-body items-center text-center">
          {status === 'processing' && (
            <>
              <span className="loading loading-spinner loading-lg text-primary mb-4"></span>
              <h2 className="card-title">Connecting Your Bank</h2>
              <p className="text-base-content/70">{message}</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="text-5xl mb-4">✅</div>
              <h2 className="card-title text-success">Success!</h2>
              <p className="text-base-content/70">{message}</p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="text-5xl mb-4">❌</div>
              <h2 className="card-title text-error">Error</h2>
              <p className="text-base-content/70">{message}</p>
              <button
                className="btn btn-primary mt-4"
                onClick={() => window.location.href = '/settings'}
              >
                Return to Settings
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
