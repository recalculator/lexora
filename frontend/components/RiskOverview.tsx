'use client'

import { useState, useEffect } from 'react'
import { getDocumentSummary, TopRisk } from '@/lib/api'

interface RiskOverviewProps {
  documentId: number
  onRiskClick?: (clauseIdx: number) => void
  isAnalyzing?: boolean
}

export default function RiskOverview({ documentId, onRiskClick, isAnalyzing }: RiskOverviewProps) {
  const [topRisks, setTopRisks] = useState<TopRisk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overallRisk, setOverallRisk] = useState<'low' | 'medium' | 'high' | 'critical'>('low')

  useEffect(() => {
    if (!isAnalyzing && documentId) {
      loadTopRisks()
    }
  }, [documentId, isAnalyzing])

  const loadTopRisks = async () => {
    setLoading(true)
    setError(null)
    try {
      const summary = await getDocumentSummary(documentId)
      setTopRisks(summary.top_risks)
      
      // Calculate overall risk from top risks
      const avgRisk = summary.top_risks.reduce((sum, r) => sum + (r.risk_score || 0), 0) / summary.top_risks.length
      if (avgRisk < 30) setOverallRisk('low')
      else if (avgRisk < 60) setOverallRisk('medium')
      else if (avgRisk < 80) setOverallRisk('high')
      else setOverallRisk('critical')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load top risks')
    } finally {
      setLoading(false)
    }
  }

  const getRiskBadgeClass = (riskScore: number | null) => {
    if (riskScore === null) return 'badge-risk-low opacity-50'
    if (riskScore < 30) return 'badge-risk-low'
    if (riskScore < 60) return 'badge-risk-medium'
    if (riskScore < 80) return 'badge-risk-high'
    return 'badge-risk-critical'
  }

  const getRiskLabel = (riskScore: number | null) => {
    if (riskScore === null) return 'Unknown'
    if (riskScore < 30) return 'Low'
    if (riskScore < 60) return 'Medium'
    if (riskScore < 80) return 'High'
    return 'Critical'
  }

  const getOverallRiskBadge = () => {
    const styles = {
      low: 'badge-risk-low',
      medium: 'badge-risk-medium',
      high: 'badge-risk-high',
      critical: 'badge-risk-critical',
    }
    return styles[overallRisk]
  }

  if (isAnalyzing) {
    return (
      <div className="card p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-bg-muted rounded w-1/4"></div>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-24 bg-bg-muted rounded-xl"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="card p-6">
        <div className="text-sm text-text-muted">Loading risk overview...</div>
      </div>
    )
  }

  if (error || topRisks.length === 0) {
    return null
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center">
            <svg className="w-5 h-5 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-serif font-bold text-text">Risk Overview</h3>
            <p className="text-xs text-text-muted mt-0.5">Top 5 highest-risk clauses</p>
          </div>
        </div>
        <div className={`px-3 py-1.5 rounded-full text-xs font-semibold ${getOverallRiskBadge()}`}>
          {overallRisk.toUpperCase()} RISK
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {topRisks.map((risk, index) => (
          <button
            key={index}
            onClick={() => onRiskClick?.(risk.idx)}
            className="text-left p-4 rounded-xl border border-border hover:border-brand hover:bg-bg-muted transition-all group card-inner"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-text-muted">Clause #{risk.idx}</span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${getRiskBadgeClass(risk.risk_score)}`}>
                {getRiskLabel(risk.risk_score)}
              </span>
            </div>
            {risk.clause_type && (
              <div className="text-sm font-semibold text-text mb-2 truncate">
                {risk.clause_type}
              </div>
            )}
            <div className="text-xs text-text-muted line-clamp-2 mb-3">
              {risk.preview}
            </div>
            {/* Risk bar */}
            <div className="w-full bg-bg-muted rounded-full h-1.5 overflow-hidden">
              <div 
                className={`h-full transition-all ${
                  (risk.risk_score || 0) < 30 ? 'bg-risk-low' :
                  (risk.risk_score || 0) < 60 ? 'bg-risk-medium' :
                  (risk.risk_score || 0) < 80 ? 'bg-risk-high' : 'bg-risk-critical'
                }`}
                style={{ width: `${Math.min(risk.risk_score || 0, 100)}%` }}
              />
            </div>
            <div className="mt-2 text-xs text-text-subtle">
              Risk: {risk.risk_score !== null && risk.risk_score !== undefined ? `${risk.risk_score.toFixed(0)}/100` : 'N/A'}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
