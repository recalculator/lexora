'use client'

import { Clause } from '@/lib/api'
import clsx from 'clsx'

interface ClauseCardProps {
  clause: Clause
  isSelected: boolean
  onClick: () => void
  onExplain?: (e: React.MouseEvent) => void
  explaining?: boolean
}

export default function ClauseCard({ clause, isSelected, onClick, onExplain, explaining }: ClauseCardProps) {
  const getRiskBarColor = (riskScore: number | null) => {
    if (riskScore === null) return 'bg-bg-muted'
    if (riskScore < 30) return 'bg-risk-low'
    if (riskScore < 60) return 'bg-risk-medium'
    if (riskScore < 80) return 'bg-risk-high'
    return 'bg-risk-critical'
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

  const confidencePercent = Math.round((clause.confidence || 0) * 100)

  return (
    <div
      onClick={onClick}
      className={clsx(
        'card-inner border p-4 cursor-pointer transition-all',
        isSelected
          ? 'ring-2 ring-brand bg-bg-muted border-brand'
          : 'border-border hover:border-brand-light hover:bg-bg-muted'
      )}
      data-clause-idx={clause.idx}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-sm font-semibold text-text">Clause {clause.idx}</span>
            {clause.clause_type && (
              <span className="badge-clause">
                {clause.clause_type}
              </span>
            )}
            <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full', getRiskBadgeClass(clause.risk_score))}>
              {getRiskLabel(clause.risk_score)}
            </span>
          </div>
          
          <div className="flex items-center gap-3 text-xs text-text-muted mb-3">
            <span>Risk: {clause.risk_score !== null && clause.risk_score !== undefined ? `${clause.risk_score.toFixed(0)}/100` : 'N/A'}</span>
            <span>•</span>
            <span>Confidence: {confidencePercent}%</span>
          </div>

          {/* Confidence meter */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-text-subtle">Confidence</span>
              <span className="text-xs font-medium text-text">{confidencePercent}%</span>
            </div>
            <div className="w-full h-1.5 bg-bg-muted rounded-full overflow-hidden">
              <div
                className={clsx('h-full transition-all', 
                  confidencePercent >= 70 ? 'bg-risk-low' : 
                  confidencePercent >= 50 ? 'bg-risk-medium' : 
                  'bg-yellow-500'
                )}
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={onExplain}
              disabled={explaining}
              className="text-xs text-brand hover:text-brand-light disabled:text-text-subtle font-medium transition-colors"
            >
              {explaining ? 'Loading...' : 'Why flagged?'}
            </button>
          </div>
        </div>

        {/* Risk bar */}
        <div className="ml-3 flex-shrink-0">
          <div className="w-2 h-16 bg-bg-muted rounded-full overflow-hidden">
            <div
              className={clsx('w-full transition-all', getRiskBarColor(clause.risk_score))}
              style={{
                height: `${Math.min(clause.risk_score || 0, 100)}%`,
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
