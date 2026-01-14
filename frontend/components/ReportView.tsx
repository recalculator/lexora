'use client'

import { useState, useEffect } from 'react'
import { getReport, generatePlaybook, generateRedlines, getDocumentSummary, ModelInfo } from '@/lib/api'

interface ReportViewProps {
  documentId: number
  refetchTrigger?: number
}

type Status = 'idle' | 'loading' | 'done' | 'error'

export default function ReportView({ documentId, refetchTrigger }: ReportViewProps) {
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [playbookStatus, setPlaybookStatus] = useState<Status>('idle')
  const [redlinesStatus, setRedlinesStatus] = useState<Status>('idle')
  const [generatingPlaybook, setGeneratingPlaybook] = useState(false)
  const [generatingRedlines, setGeneratingRedlines] = useState(false)

  useEffect(() => {
    loadReport()
    loadModelInfo()
  }, [documentId, refetchTrigger])

  const loadReport = async () => {
    setLoading(true)
    setError(null)
    try {
      const reportData = await getReport(documentId)
      setReport(reportData)
      
      setPlaybookStatus(reportData.playbook ? 'done' : 'idle')
      setRedlinesStatus(reportData.redlines ? 'done' : 'idle')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report')
    } finally {
      setLoading(false)
    }
  }

  const loadModelInfo = async () => {
    try {
      const summary = await getDocumentSummary(documentId)
      setModelInfo(summary.model_info)
    } catch (err) {
      // Ignore errors
    }
  }

  const handleGeneratePlaybook = async () => {
    setGeneratingPlaybook(true)
    setPlaybookStatus('loading')
    setError(null)
    try {
      await generatePlaybook(documentId)
      await loadReport() // Reload to show the generated playbook
    } catch (err) {
      setPlaybookStatus('error')
      setError(err instanceof Error ? err.message : 'Failed to generate playbook')
    } finally {
      setGeneratingPlaybook(false)
    }
  }

  const handleGenerateRedlines = async () => {
    setGeneratingRedlines(true)
    setRedlinesStatus('loading')
    setError(null)
    try {
      await generateRedlines(documentId)
      await loadReport() // Reload to show the generated redlines
    } catch (err) {
      setRedlinesStatus('error')
      setError(err instanceof Error ? err.message : 'Failed to generate redlines')
    } finally {
      setGeneratingRedlines(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card p-6 animate-pulse">
            <div className="h-6 bg-bg-muted rounded w-1/4 mb-4"></div>
            <div className="h-4 bg-bg-muted rounded w-full mb-2"></div>
            <div className="h-4 bg-bg-muted rounded w-3/4"></div>
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-6 border-risk-high">
        <div className="text-sm text-risk-high">{error}</div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="card p-6">
        <div className="text-sm text-text-muted">No report available</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Document Info */}
      <div className="card p-6">
        <h2 className="text-xl font-serif font-bold text-text mb-5">Document Information</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5 text-sm mb-4">
          <div>
            <div className="text-xs text-text-muted mb-1.5">Filename</div>
            <div className="font-semibold text-text truncate">{report.document.filename}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1.5">Uploaded</div>
            <div className="font-semibold text-text">{new Date(report.document.created_at).toLocaleDateString()}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1.5">Text Length</div>
            <div className="font-semibold text-text">{report.text.length.toLocaleString()} chars</div>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1.5">Clauses</div>
            <div className="font-semibold text-text">{report.clauses.length}</div>
          </div>
        </div>
      </div>

      {/* Playbook */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-serif font-bold text-text">Negotiation Playbook</h2>
          <span className={`text-xs font-semibold px-3 py-1.5 rounded-full ${
            playbookStatus === 'done' ? 'badge-risk-low' :
            playbookStatus === 'loading' ? 'badge-risk-medium' :
            playbookStatus === 'error' ? 'badge-risk-high' :
            'bg-bg-muted text-text-muted'
          }`}>
            {playbookStatus === 'done' ? '✓ Generated' :
             playbookStatus === 'loading' ? 'Generating...' :
             playbookStatus === 'error' ? 'Error' :
             'Not generated'}
          </span>
        </div>
        
        {report.playbook ? (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">Summary</h3>
              <p className="text-sm text-text leading-relaxed">{report.playbook.document_summary}</p>
            </div>
            
            <div>
              <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">Overall Risk Assessment</h3>
              <p className="text-sm text-text leading-relaxed">{report.playbook.overall_risk_assessment}</p>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-text mb-3 uppercase tracking-wide">Priority Clauses</h3>
              <div className="space-y-4">
                {report.playbook.priority_clauses.map((clause: any, idx: number) => (
                  <div key={idx} className="border-l-4 border-brand pl-4 py-3 bg-bg-muted rounded-r-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-semibold text-text">
                        Clause {clause.clause_index}
                      </span>
                      {clause.clause_type && (
                        <span className="badge-clause">
                          {clause.clause_type}
                        </span>
                      )}
                      <span className="text-xs font-medium text-text-muted">Risk: {clause.risk_level}</span>
                    </div>
                    <div className="text-sm text-text mb-2"><strong>Concern:</strong> {clause.concern}</div>
                    <div className="text-sm text-text mb-2"><strong>Recommendation:</strong> {clause.recommendation}</div>
                    <div className="text-sm text-text mb-1"><strong>Strategy:</strong> {clause.negotiation_strategy}</div>
                    <div className="text-xs text-text-subtle mt-2 italic">{clause.citation}</div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">General Recommendations</h3>
              <ul className="space-y-2">
                {report.playbook.general_recommendations.map((rec: string, idx: number) => (
                  <li key={idx} className="text-sm text-text flex items-start gap-2">
                    <span className="text-brand mt-1">→</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>

            {report.playbook.key_provisions && report.playbook.key_provisions.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">Key Provisions</h3>
                <ul className="space-y-2">
                  {report.playbook.key_provisions.map((prov: string, idx: number) => (
                    <li key={idx} className="text-sm text-text flex items-start gap-2">
                      <span className="text-brand mt-1">•</span>
                      <span>{prov}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-bg-muted flex items-center justify-center">
              <svg className="w-8 h-8 text-text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm text-text mb-1">No playbook generated yet</p>
            <p className="text-xs text-text-muted mb-4">Generate a negotiation playbook with AI-powered insights</p>
            <button
              onClick={handleGeneratePlaybook}
              disabled={generatingPlaybook}
              className="btn-primary"
            >
              {generatingPlaybook ? 'Generating...' : 'Generate Playbook'}
            </button>
          </div>
        )}
      </div>

      {/* Redlines */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-serif font-bold text-text">Redline Suggestions</h2>
          <span className={`text-xs font-semibold px-3 py-1.5 rounded-full ${
            redlinesStatus === 'done' ? 'badge-risk-low' :
            redlinesStatus === 'loading' ? 'badge-risk-medium' :
            redlinesStatus === 'error' ? 'badge-risk-high' :
            'bg-bg-muted text-text-muted'
          }`}>
            {redlinesStatus === 'done' ? '✓ Generated' :
             redlinesStatus === 'loading' ? 'Generating...' :
             redlinesStatus === 'error' ? 'Error' :
             'Not generated'}
          </span>
        </div>
        
        {report.redlines ? (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">Summary</h3>
              <p className="text-sm text-text leading-relaxed">{report.redlines.summary}</p>
            </div>

            {report.redlines.priority_redlines && report.redlines.priority_redlines.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-text mb-3 uppercase tracking-wide">Priority Redlines</h3>
                <div className="space-y-4">
                  {report.redlines.priority_redlines.map((redline: any, idx: number) => (
                    <div key={idx} className="border border-border rounded-xl p-4 bg-bg-muted">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-sm font-semibold text-text">
                          Clause {redline.clause_index}
                        </span>
                        {redline.clause_type && (
                          <span className="badge-clause">
                            {redline.clause_type}
                          </span>
                        )}
                      </div>
                      <div className="space-y-3">
                        <div>
                          <div className="text-xs font-medium text-text-muted mb-1">Original</div>
                          <div className="text-sm text-text bg-risk-high-bg p-3 rounded-xl border-l-4 border-risk-high">
                            <span className="line-through">{redline.original_text.substring(0, 300)}</span>
                            {redline.original_text.length > 300 && '...'}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-text-muted mb-1">Suggested</div>
                          <div className="text-sm text-text bg-risk-low-bg p-3 rounded-xl border-l-4 border-risk-low">
                            {redline.suggested_change.substring(0, 300)}
                            {redline.suggested_change.length > 300 && '...'}
                          </div>
                        </div>
                        <div className="text-sm text-text">
                          <strong>Rationale:</strong> {redline.rationale}
                        </div>
                        <div className="text-sm text-text">
                          <strong>Risk Reduction:</strong> {redline.risk_reduction}
                        </div>
                        <div className="text-xs text-text-subtle italic">{redline.citation}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {report.redlines.optional_redlines && report.redlines.optional_redlines.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-text mb-3 uppercase tracking-wide">Optional Redlines</h3>
                <div className="space-y-4">
                  {report.redlines.optional_redlines.map((redline: any, idx: number) => (
                    <div key={idx} className="border border-border rounded-xl p-4 bg-bg-muted opacity-90">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-sm font-semibold text-text">
                          Clause {redline.clause_index}
                        </span>
                        {redline.clause_type && (
                          <span className="badge-clause opacity-75">
                            {redline.clause_type}
                          </span>
                        )}
                      </div>
                      <div className="space-y-2 text-sm text-text-muted">
                        <div><strong>Original:</strong> <span className="line-through">{redline.original_text.substring(0, 200)}...</span></div>
                        <div><strong>Suggested:</strong> {redline.suggested_change.substring(0, 200)}...</div>
                        <div><strong>Rationale:</strong> {redline.rationale}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {report.redlines.general_notes && report.redlines.general_notes.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-text mb-2 uppercase tracking-wide">General Notes</h3>
                <ul className="space-y-2">
                  {report.redlines.general_notes.map((note: string, idx: number) => (
                    <li key={idx} className="text-sm text-text flex items-start gap-2">
                      <span className="text-brand mt-1">•</span>
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-bg-muted flex items-center justify-center">
              <svg className="w-8 h-8 text-text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </div>
            <p className="text-sm text-text mb-1">No redlines generated yet</p>
            <p className="text-xs text-text-muted mb-4">Generate AI-powered redline suggestions for your contract</p>
            <button
              onClick={handleGenerateRedlines}
              disabled={generatingRedlines}
              className="btn-primary"
            >
              {generatingRedlines ? 'Generating...' : 'Generate Redlines'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
