import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface AddOllamaModelProps {
  isOpen: boolean;
  onClose: () => void;
  onModelAdded: (model: string) => void;
}

export default function AddOllamaModel({ isOpen, onClose, onModelAdded }: AddOllamaModelProps) {
  const [modelName, setModelName] = useState('');
  const [autoPull, setAutoPull] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [pulling, setPulling] = useState(false);
  const [suggestions] = useState([
    'mistral:7b',
    'llama2:7b',
    'llama2:13b',
    'neural-chat:7b',
    'dolphin-mixtral',
  ]);

  useEffect(() => {
    if (!isOpen) {
      // Reset form when modal closes
      setModelName('');
      setError('');
      setSuccess('');
      setPulling(false);
    }
  }, [isOpen]);

  const handleAddModel = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!modelName.trim()) {
      setError('Model name is required');
      return;
    }

    if (!modelName.includes(':')) {
      setError('Model format should be "name:tag" (e.g., "mistral:7b")');
      return;
    }

    try {
      setLoading(true);
      if (autoPull) {
        setPulling(true);
      }

      const response = await axios.post(`${API_URL}/llm/add-ollama-model`, {
        model_name: modelName.trim(),
        auto_pull: autoPull,
      });

      if (response.data.success) {
        setSuccess(response.data.message);
        setTimeout(() => {
          onModelAdded(modelName.trim());
          onClose();
        }, 1500);
      } else {
        setError(response.data.message || 'Failed to add model');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || err.message || 'Failed to add model';
      setError(errorMessage);
    } finally {
      setLoading(false);
      setPulling(false);
    }
  };

  const handleSuggestion = (suggestion: string) => {
    setModelName(suggestion);
  };

  if (!isOpen) return null;

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-md">
        <h3 className="font-bold text-lg mb-4">Add Ollama Model</h3>

        <form onSubmit={handleAddModel} className="space-y-4">
          {/* Model Name Input */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-semibold">Model Name</span>
            </label>
            <input
              type="text"
              placeholder="e.g., mistral:7b"
              className="input input-bordered"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <label className="label">
              <span className="label-text-alt text-xs text-base-content/70">
                Format: model_name:tag (e.g., mistral:7b, llama2:13b)
              </span>
            </label>
          </div>

          {/* Suggestions */}
          <div>
            <label className="label">
              <span className="label-text-alt text-sm font-semibold">Popular Models:</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="badge badge-outline hover:badge-primary cursor-pointer transition-all"
                  onClick={() => handleSuggestion(suggestion)}
                  disabled={loading}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          {/* Auto-Pull Toggle */}
          <div className="form-control">
            <label className="label cursor-pointer">
              <span className="label-text">Auto-pull from Ollama</span>
              <input
                type="checkbox"
                className="checkbox"
                checked={autoPull}
                onChange={(e) => setAutoPull(e.target.checked)}
                disabled={loading}
              />
            </label>
            <label className="label">
              <span className="label-text-alt">
                {autoPull
                  ? 'Model will be automatically pulled (downloaded) if not available'
                  : 'You must pull the model manually via CLI'}
              </span>
            </label>
          </div>

          {/* Status Messages */}
          {error && (
            <div className="alert alert-error alert-sm">
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="alert alert-success alert-sm">
              <span>{success}</span>
            </div>
          )}

          {pulling && (
            <div className="alert alert-info alert-sm">
              <span>🔄 Pulling model from Ollama (this may take a few minutes)...</span>
            </div>
          )}

          {/* Action Buttons */}
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className={`btn ${loading ? 'btn-disabled' : 'btn-primary'}`}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  {pulling ? 'Pulling...' : 'Adding...'}
                </>
              ) : (
                '✨ Add Model'
              )}
            </button>
          </div>
        </form>

        {/* Help Text */}
        <div className="text-xs text-base-content/60 mt-4 p-3 bg-base-200 rounded">
          <p className="font-semibold mb-1">💡 Need help?</p>
          <p>
            You can find more models at{' '}
            <a
              href="https://ollama.ai/library"
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary"
            >
              ollama.ai/library
            </a>
          </p>
        </div>
      </div>

      {/* Backdrop */}
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
