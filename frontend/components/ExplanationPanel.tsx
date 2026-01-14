'use client'

import { ExplainResponse, QuotedSpan } from '@/lib/api'

interface ExplanationPanelProps {
  explanation: ExplainResponse | null
  loading: boolean
  onClose: () => void
}

export default function ExplanationPanel({ explanation, loading, onClose }: ExplanationPanelProps) {
  if (!explanation && !loading) {
    return null
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Why Flagged?</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-4 text-gray-600">Generating explanation...</p>
            </div>
          ) : explanation ? (
            <div className="space-y-6">
              {/* Explanation */}
              <div>
                <h4 className="font-semibold text-gray-900 mb-2">Explanation</h4>
                <p className="text-gray-700">{explanation.explanation}</p>
              </div>

              {/* Risk Drivers */}
              {explanation.risk_drivers.length > 0 && (
                <div>
                  <h4 className="font-semibold text-gray-900 mb-2">Risk Drivers</h4>
                  <ul className="list-disc list-inside space-y-1 text-gray-700">
                    {explanation.risk_drivers.map((driver, idx) => (
                      <li key={idx}>{driver}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Suggested Negotiation Moves */}
              {explanation.suggested_negotiation_moves.length > 0 && (
                <div>
                  <h4 className="font-semibold text-gray-900 mb-2">Suggested Negotiation Moves</h4>
                  <ul className="list-disc list-inside space-y-1 text-gray-700">
                    {explanation.suggested_negotiation_moves.map((move, idx) => (
                      <li key={idx}>{move}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Quoted Spans */}
              {explanation.quoted_spans.length > 0 && (
                <div>
                  <h4 className="font-semibold text-gray-900 mb-2">Key Quotes</h4>
                  <div className="space-y-3">
                    {explanation.quoted_spans.map((span, idx) => (
                      <div key={idx} className="border-l-4 border-primary-500 pl-4 py-2 bg-gray-50">
                        <p className="text-sm font-medium text-gray-900 mb-1">"{span.quote}"</p>
                        <p className="text-xs text-gray-600">{span.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="pt-4 border-t text-xs text-gray-500">
                <p>Clause {explanation.clause_idx} • Risk: {explanation.risk_score.toFixed(0)}/100 • Confidence: {Math.round(explanation.confidence * 100)}%</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
