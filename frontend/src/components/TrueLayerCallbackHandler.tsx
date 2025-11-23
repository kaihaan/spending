import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

export default function TrueLayerCallbackHandler() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [message, setMessage] = useState('Processing authorization...');

  useEffect(() => {
    const handleCallback = async () => {
      try {
        const code = searchParams.get('code');
        const state = searchParams.get('state');
        const error = searchParams.get('error');
        const error_description = searchParams.get('error_description');

        if (error) {
          setStatus('error');
          setMessage(`Authorization failed: ${error_description || error}`);
          return;
        }

        if (!code || !state) {
          setStatus('error');
          setMessage('Invalid callback parameters');
          return;
        }

        // Retrieve stored state and code_verifier from sessionStorage
        const storedState = sessionStorage.getItem('truelayer_state');
        const codeVerifier = sessionStorage.getItem('truelayer_code_verifier');

        if (state !== storedState) {
          setStatus('error');
          setMessage('State mismatch - authorization failed');
          sessionStorage.removeItem('truelayer_state');
          sessionStorage.removeItem('truelayer_code_verifier');
          return;
        }

        if (!codeVerifier) {
          setStatus('error');
          setMessage('Missing code verifier - authorization failed');
          return;
        }

        // Exchange code for token
        const response = await axios.get(`${API_URL}/truelayer/callback`, {
          params: { code, state, code_verifier: codeVerifier }
        });

        // Clear stored values
        sessionStorage.removeItem('truelayer_state');
        sessionStorage.removeItem('truelayer_code_verifier');

        if (response.data.status === 'authorized') {
          setStatus('success');
          setMessage('Bank account connected successfully! Redirecting...');

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
          err.response?.data?.error ||
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
