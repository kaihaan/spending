interface Props {
  isEnriched: boolean;
  confidenceScore?: number;
  enrichedAt?: string;
}

export default function EnrichmentStatusIndicator({
  isEnriched,
  confidenceScore,
  enrichedAt
}: Props) {
  if (!isEnriched) {
    return (
      <div className="tooltip" data-tip="Not enriched">
        <span className="text-base-content/50 text-lg">—</span>
      </div>
    );
  }

  const confidence = confidenceScore || 0;
  const isHighConfidence = confidence >= 0.7;
  const isLowConfidence = confidence < 0.7 && confidence >= 0.5;

  const formattedDate = enrichedAt ? new Date(enrichedAt).toLocaleDateString() : 'Unknown';
  const confidencePercent = Math.round(confidence * 100);
  const tooltipText = `Enriched on ${formattedDate} (${confidencePercent}% confidence)`;

  if (isHighConfidence) {
    return (
      <div className="tooltip" data-tip={tooltipText}>
        <span className="badge badge-success badge-sm">High</span>
      </div>
    );
  }

  if (isLowConfidence) {
    return (
      <div className="tooltip" data-tip={tooltipText}>
        <span className="badge badge-warning badge-sm">Low</span>
      </div>
    );
  }

  // Very low confidence (< 0.5)
  return (
    <div className="tooltip" data-tip={tooltipText}>
      <span className="badge badge-error badge-sm">Poor</span>
    </div>
  );
}
