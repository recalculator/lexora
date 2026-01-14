'use client'

import { Clause, ExplainResponse } from '@/lib/api'

interface InsightsPanelProps {
  selectedClause: Clause | null
  documentId: number
  onExpand?: () => void
  explanation?: ExplainResponse | null
  loading?: boolean
  error?: string | null
  onGenerateExplanation?: () => void
  isModal?: boolean
}

export default function InsightsPanel({ 
  selectedClause, 
  documentId, 
  onExpand,
  explanation,
  loading = false,
  error: errorProp,
  onGenerateExplanation,
  isModal = false
}: InsightsPanelProps) {

  const getRiskColor = (riskScore: number | null) => {
    if (riskScore === null) return 'text-text-muted'
    if (riskScore < 30) return 'text-risk-low'
    if (riskScore < 60) return 'text-risk-medium'
    if (riskScore < 80) return 'text-risk-high'
    return 'text-risk-critical'
  }

  if (!selectedClause) {
    return (
      <div className="card h-full flex items-center justify-center p-8">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-bg-muted flex items-center justify-center">
            <svg className="w-8 h-8 text-text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-sm font-medium text-text mb-1">Select a clause</h3>
          <p className="text-xs text-text-muted">Choose a clause from the list to see why it was flagged and get negotiation insights.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-serif font-bold text-text">Clause {selectedClause.idx}</h3>
          <div className="flex items-center gap-2">
            {selectedClause.clause_type && (
              <span className="badge-clause">
                {selectedClause.clause_type}
              </span>
            )}
            {onExpand && (
              <button
                onClick={onExpand}
                className="p-1.5 text-text-muted hover:text-text rounded-lg hover:bg-bg-muted transition-colors"
                title="Expand panel"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
              </button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-muted">
          <span className={`font-semibold ${getRiskColor(selectedClause.risk_score)}`}>
            Risk: {selectedClause.risk_score !== null && selectedClause.risk_score !== undefined ? `${selectedClause.risk_score.toFixed(0)}/100` : 'N/A'}
          </span>
          <span>•</span>
          <span>Confidence: {Math.round((selectedClause.confidence || 0) * 100)}%</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Clause Text Excerpt */}
        <div>
          <h4 className="text-xs font-semibold text-text mb-2 uppercase tracking-wide">Clause Text</h4>
          <div className="bg-bg-muted rounded-xl p-3 text-xs text-text leading-relaxed max-h-32 overflow-y-auto border border-border">
            {selectedClause.text.substring(0, 500)}
            {selectedClause.text.length > 500 && '...'}
          </div>
        </div>

        {/* Explanation */}
        {explanation ? (
          <div className="space-y-5">
            <div>
              <h4 className="text-xs font-semibold text-text mb-2 uppercase tracking-wide">Why Flagged</h4>
              <p className="text-xs text-text leading-relaxed">{explanation.explanation}</p>
            </div>

            {explanation.risk_drivers.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-text mb-2 uppercase tracking-wide">Risk Drivers</h4>
                <ul className="space-y-1.5">
                  {explanation.risk_drivers.map((driver, idx) => (
                    <li key={idx} className="text-xs text-text flex items-start gap-2">
                      <span className="text-risk-high mt-1">•</span>
                      <span>{driver}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {explanation.suggested_negotiation_moves.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-text mb-2 uppercase tracking-wide">Suggested Moves</h4>
                <ul className="space-y-1.5">
                  {explanation.suggested_negotiation_moves.map((move, idx) => (
                    <li key={idx} className="text-xs text-text flex items-start gap-2">
                      <span className="text-brand mt-1">→</span>
                      <span>{move}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {explanation.quoted_spans.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-text mb-2 uppercase tracking-wide">Key Quotes</h4>
                <div className="space-y-2">
                  {explanation.quoted_spans.map((span, idx) => (
                    <div key={idx} className="bg-bg-muted border-l-4 border-brand pl-3 py-2 rounded-xl">
                      <p className="text-[11px] font-medium text-text mb-1">"{span.quote}"</p>
                      <p className="text-[10px] text-text-muted">{span.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8">
            {loading ? (
              <div className="space-y-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand mx-auto"></div>
                <p className="text-xs text-text-muted">Generating explanation...</p>
              </div>
            ) : errorProp ? (
              <div className="text-xs text-risk-high">{errorProp}</div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-text-muted">No explanation generated yet.</p>
                {onGenerateExplanation && (
                  <button
                    onClick={onGenerateExplanation}
                    className="btn-primary text-xs"
                  >
                    Generate Explanation
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer Actions */}
      {explanation && onGenerateExplanation && (
        <div className="p-5 border-t border-border flex gap-2 flex-shrink-0">
          <button
            onClick={onGenerateExplanation}
            disabled={loading}
            className="btn-secondary flex-1 text-xs"
          >
            {loading ? 'Regenerating...' : 'Regenerate'}
          </button>
        </div>
      )}
    </div>
  )
}
