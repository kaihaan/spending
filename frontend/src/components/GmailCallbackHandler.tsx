import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

export default function GmailCallbackHandler() {
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
        const email = searchParams.get('email');

        if (error) {
          setStatus('error');
          setMessage(`Authorization failed: ${decodeURIComponent(error)}`);
          return;
        }

        if (statusParam === 'authorized' && connectionId) {
          setStatus('success');
          const emailDisplay = email ? ` (${decodeURIComponent(email)})` : '';
          setMessage(`Gmail account${emailDisplay} connected successfully! Redirecting...`);

          // Clear stored sessionStorage values
          sessionStorage.removeItem('gmail_state');
          sessionStorage.removeItem('gmail_code_verifier');

          // Redirect to settings after 2 seconds
          setTimeout(() => {
            navigate('/settings?tab=gmail');
            window.dispatchEvent(new Event('gmail-connected'));
          }, 2000);
        } else {
          setStatus('error');
          setMessage('Failed to connect Gmail account');
        }
      } catch (err: any) {
        setStatus('error');
        setMessage(
          err.message ||
          'An error occurred during authorization'
        );
        console.error('Gmail OAuth callback error:', err);
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
              <h2 className="card-title">Connecting Gmail</h2>
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
                onClick={() => navigate('/settings?tab=gmail')}
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
