import { useState } from 'react';
import axios from 'axios';

interface PDFAttachment {
  id: number;
  filename: string;
  size_bytes: number;
  mime_type: string;
  object_key: string;
  created_at: string;
}

interface Props {
  attachments: PDFAttachment[];
}

// Format file size for display
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

export default function PDFAttachmentViewer({ attachments }: Props) {
  const [viewingPdf, setViewingPdf] = useState<{
    url: string;
    filename: string;
  } | null>(null);
  const [loading, setLoading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleViewPdf = async (attachment: PDFAttachment) => {
    setLoading(attachment.id);
    setError(null);

    try {
      // Get presigned URL from backend
      const response = await axios.get(`/api/attachments/${attachment.id}/url`);
      const url = response.data.url;

      setViewingPdf({
        url,
        filename: attachment.filename,
      });
    } catch (err) {
      console.error('Failed to get PDF URL:', err);
      setError('Failed to load PDF');
    } finally {
      setLoading(null);
    }
  };

  const handleDownload = async (attachment: PDFAttachment) => {
    setLoading(attachment.id);
    setError(null);

    try {
      // Get presigned URL and open in new tab for download
      const response = await axios.get(`/api/attachments/${attachment.id}/url`);
      window.open(response.data.url, '_blank');
    } catch (err) {
      console.error('Failed to download PDF:', err);
      setError('Failed to download PDF');
    } finally {
      setLoading(null);
    }
  };

  if (!attachments || attachments.length === 0) {
    return null;
  }

  return (
    <>
      <div className="mt-4">
        <h4 className="font-semibold text-sm text-base-content/60 mb-2 flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          PDF Attachments ({attachments.length})
        </h4>

        {error && (
          <div className="alert alert-error alert-sm mb-2">
            <span className="text-sm">{error}</span>
          </div>
        )}

        <div className="space-y-2">
          {attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="flex items-center justify-between bg-base-200 rounded-lg p-3"
            >
              <div className="flex items-center gap-3">
                {/* PDF Icon */}
                <div className="w-10 h-12 bg-error/10 rounded flex items-center justify-center">
                  <span className="text-error text-xs font-bold">PDF</span>
                </div>
                <div>
                  <p className="font-medium text-sm truncate max-w-[200px]" title={attachment.filename}>
                    {attachment.filename}
                  </p>
                  <p className="text-xs text-base-content/50">
                    {formatFileSize(attachment.size_bytes)}
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                {/* View button */}
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => handleViewPdf(attachment)}
                  disabled={loading === attachment.id}
                  title="View PDF"
                >
                  {loading === attachment.id ? (
                    <span className="loading loading-spinner loading-xs"></span>
                  ) : (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                      />
                    </svg>
                  )}
                </button>

                {/* Download button */}
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => handleDownload(attachment)}
                  disabled={loading === attachment.id}
                  title="Download PDF"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* PDF Viewer Modal */}
      {viewingPdf && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setViewingPdf(null)}
          />

          {/* Modal Content */}
          <div className="relative bg-base-100 rounded-lg shadow-2xl w-[90vw] h-[90vh] max-w-5xl flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-base-300">
              <div className="flex items-center gap-3">
                <span className="text-error font-bold">PDF</span>
                <span className="font-medium truncate max-w-md">{viewingPdf.filename}</span>
              </div>
              <div className="flex items-center gap-2">
                {/* Open in new tab */}
                <a
                  href={viewingPdf.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-sm btn-ghost"
                  title="Open in new tab"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                </a>
                {/* Close button */}
                <button
                  className="btn btn-sm btn-circle btn-ghost"
                  onClick={() => setViewingPdf(null)}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
            </div>

            {/* PDF iframe */}
            <div className="flex-1 overflow-hidden">
              <iframe
                src={viewingPdf.url}
                className="w-full h-full border-0"
                title={viewingPdf.filename}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
