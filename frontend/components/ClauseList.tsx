'use client'

import { useState, useEffect, useMemo } from 'react'
import { Clause, getReport } from '@/lib/api'
import ClauseCard from './ClauseCard'

interface ClauseListProps {
  documentId: number
  analysisTrigger?: number
  isAnalyzing?: boolean
  clausesFromAnalysis?: Clause[]
  selectedClauseIdx: number | null
  onClauseSelect: (clause: Clause) => void
}

export default function ClauseList({ 
  documentId, 
  analysisTrigger, 
  isAnalyzing, 
  clausesFromAnalysis,
  selectedClauseIdx,
  onClauseSelect
}: ClauseListProps) {
  const [clauses, setClauses] = useState<Clause[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterType, setFilterType] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'risk' | 'index'>('risk')

  const loadClauses = async () => {
    setLoading(true)
    setError(null)
    try {
      const report = await getReport(documentId)
      setClauses(report.clauses)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load clauses')
    } finally {
      setLoading(false)
    }
  }

  // Use clauses from analysis if provided (highest priority)
  useEffect(() => {
    if (clausesFromAnalysis && clausesFromAnalysis.length > 0) {
      setClauses(clausesFromAnalysis)
      setLoading(false)
      setError(null)
      return
    }
    
    if (documentId && !isAnalyzing) {
      loadClauses()
    }
  }, [documentId, clausesFromAnalysis, isAnalyzing]) // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when analysis trigger changes
  useEffect(() => {
    if (analysisTrigger !== undefined && analysisTrigger > 0 && !clausesFromAnalysis && !isAnalyzing) {
      loadClauses()
    }
  }, [analysisTrigger]) // eslint-disable-line react-hooks/exhaustive-deps

  // Get unique clause types
  const clauseTypes = useMemo(() => {
    const types = new Set(clauses.map(c => c.clause_type).filter(Boolean))
    return Array.from(types) as string[]
  }, [clauses])

  // Filter and sort clauses
  const filteredClauses = useMemo(() => {
    let filtered = [...clauses]

    // Filter by type
    if (filterType !== 'all') {
      filtered = filtered.filter(c => c.clause_type === filterType)
    }

    // Filter by search
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(c => 
        c.text.toLowerCase().includes(query) ||
        c.clause_type?.toLowerCase().includes(query) ||
        c.idx.toString().includes(query)
      )
    }

    // Sort
    if (sortBy === 'risk') {
      filtered.sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
    } else {
      filtered.sort((a, b) => a.idx - b.idx)
    }

    return filtered
  }, [clauses, filterType, searchQuery, sortBy])

  // Show loading state
  if (loading || isAnalyzing) {
    return (
      <div className="card h-full flex flex-col">
        <div className="p-5 border-b border-border flex-shrink-0">
          <h2 className="text-lg font-serif font-bold text-text">Clauses</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="border border-border rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-bg-muted rounded w-1/4 mb-2"></div>
              <div className="h-3 bg-bg-muted rounded w-1/2 mb-2"></div>
              <div className="h-3 bg-bg-muted rounded w-full"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-6">
        <h2 className="text-lg font-serif font-bold text-text mb-2">Clauses</h2>
        <div className="text-sm text-risk-high">{error}</div>
      </div>
    )
  }

  if (clauses.length === 0) {
    return (
      <div className="card h-full flex items-center justify-center p-8">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-bg-muted flex items-center justify-center">
            <svg className="w-8 h-8 text-text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-sm font-medium text-text mb-1">No clauses found</h3>
          <p className="text-xs text-text-muted">Analyze the document to extract clauses.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-serif font-bold text-text">Clauses</h2>
          <span className="text-xs text-text-muted">{filteredClauses.length} of {clauses.length}</span>
        </div>

        {/* Search */}
        <div className="mb-3">
          <input
            type="text"
            placeholder="Search clauses..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full text-sm px-3 py-2 border border-border rounded-lg bg-bg-card focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand transition-colors text-text"
          />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="flex-1 text-xs px-2 py-1.5 border border-border rounded-lg bg-bg-card focus:outline-none focus:ring-2 focus:ring-brand text-text"
          >
            <option value="all">All Types</option>
            {clauseTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'risk' | 'index')}
            className="flex-1 text-xs px-2 py-1.5 border border-border rounded-lg bg-bg-card focus:outline-none focus:ring-2 focus:ring-brand text-text"
          >
            <option value="risk">Risk ↓</option>
            <option value="index">Index ↑</option>
          </select>
        </div>
      </div>

      {/* Clause List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {filteredClauses.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-sm text-text-muted">No clauses match your filters.</p>
          </div>
        ) : (
          filteredClauses.map((clause) => (
            <ClauseCard
              key={clause.idx}
              clause={clause}
              isSelected={selectedClauseIdx === clause.idx}
              onClick={() => onClauseSelect(clause)}
              onExplain={(e) => {
                e.stopPropagation()
                onClauseSelect(clause)
              }}
              explaining={false}
            />
          ))
        )}
      </div>
    </div>
  )
}
