'use client'

import { useState, useEffect } from 'react'
import { getDocumentSummary, TopRisk } from '@/lib/api'

interface TopRisksCardProps {
  documentId: number
  onRiskClick?: (clauseIdx: number) => void
}

export default function TopRisksCard({ documentId, onRiskClick }: TopRisksCardProps) {
  const [topRisks, setTopRisks] = useState<TopRisk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadTopRisks()
  }, [documentId])

  const loadTopRisks = async () => {
    setLoading(true)
    setError(null)
    try {
      const summary = await getDocumentSummary(documentId)
      setTopRisks(summary.top_risks)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load top risks')
    } finally {
      setLoading(false)
    }
  }

  const getRiskColor = (riskScore: number | null) => {
    if (riskScore === null) return 'text-gray-500'
    if (riskScore < 30) return 'text-green-600'
    if (riskScore < 60) return 'text-yellow-600'
    if (riskScore < 80) return 'text-orange-600'
    return 'text-red-600'
  }

  const getRiskLabel = (riskScore: number | null) => {
    if (riskScore === null) return 'Unknown'
    if (riskScore < 30) return 'Low'
    if (riskScore < 60) return 'Medium'
    if (riskScore < 80) return 'High'
    return 'Critical'
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Top Risks</h3>
        <div className="text-sm text-gray-600">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Top Risks</h3>
        <div className="text-sm text-red-600">{error}</div>
      </div>
    )
  }

  if (topRisks.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Top Risks</h3>
        <div className="text-sm text-gray-600">No risks found</div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Top Risks</h3>
      <div className="space-y-3">
        {topRisks.map((risk, index) => (
          <div
            key={index}
            onClick={() => onRiskClick?.(risk.idx)}
            className={`border rounded-lg p-3 cursor-pointer hover:bg-gray-50 transition-colors ${
              onRiskClick ? '' : 'cursor-default'
            }`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-gray-700">
                    Clause {risk.idx}
                  </span>
                  {risk.clause_type && (
                    <span className="text-xs bg-primary-100 text-primary-700 px-2 py-1 rounded">
                      {risk.clause_type}
                    </span>
                  )}
                  <span className={`text-xs font-medium ${getRiskColor(risk.risk_score)}`}>
                    {getRiskLabel(risk.risk_score)}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mb-1">
                  Risk: {risk.risk_score !== null && risk.risk_score !== undefined ? `${risk.risk_score.toFixed(0)}/100` : 'N/A'} • Confidence: {Math.round((risk.confidence || 0) * 100)}%
                </div>
                <div className="text-sm text-gray-700 mt-2 line-clamp-2">
                  {risk.preview}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
