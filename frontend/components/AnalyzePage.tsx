'use client'

import { useState, useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Clause, analyzeDocument, getReport, explainClause, getDocumentSummary } from '@/lib/api'
import RiskOverview from './RiskOverview'
import ClauseList from './ClauseList'
import PDFViewer from './PDFViewer'
import InsightsPanel from './InsightsPanel'
import { XMarkIcon } from '@heroicons/react/20/solid'

interface AnalyzePageProps {
  documentId: number
  isAnalyzing: boolean
  onAnalyzingChange: (analyzing: boolean) => void
  onAnalysisComplete: (clauses: Clause[]) => void
  clausesFromAnalysis?: Clause[]
  analysisTrigger: number
}

export default function AnalyzePage({
  documentId,
  isAnalyzing,
  onAnalyzingChange,
  onAnalysisComplete,
  clausesFromAnalysis,
  analysisTrigger
}: AnalyzePageProps) {
  const [selectedClause, setSelectedClause] = useState<Clause | null>(null)
  const [documentInfo, setDocumentInfo] = useState<{ filename: string; lastAnalyzed: Date | null } | null>(null)
  const [overallRisk, setOverallRisk] = useState<'low' | 'medium' | 'high' | 'critical'>('low')
  const [error, setError] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [explanation, setExplanation] = useState<any>(null)
  const [explanationLoading, setExplanationLoading] = useState(false)
  const [explanationError, setExplanationError] = useState<string | null>(null)
  const [modelStatus, setModelStatus] = useState<'onnx' | 'sklearn' | 'dummy'>('dummy')

  // Load document info
  const loadDocumentInfo = useCallback(async () => {
    try {
      const report = await getReport(documentId)
      setDocumentInfo({
        filename: report.document.filename,
        lastAnalyzed: report.clauses.length > 0 ? new Date() : null
      })
      
      // Calculate overall risk
      if (report.clauses.length > 0) {
        const avgRisk = report.clauses.reduce((sum, c) => sum + (c.risk_score || 0), 0) / report.clauses.length
        if (avgRisk < 30) setOverallRisk('low')
        else if (avgRisk < 60) setOverallRisk('medium')
        else if (avgRisk < 80) setOverallRisk('high')
        else setOverallRisk('critical')
      }
    } catch (err) {
      // Ignore errors, will show placeholder
    }
  }, [documentId])

  // Load document info on mount and when documentId changes
  useEffect(() => {
    // Reset state when documentId changes
    setDocumentInfo(null)
    setOverallRisk('low')
    setError(null)
    setExplanation(null)
    setExplanationError(null)
    setExplanationLoading(false)
    
    // Load new document info
    loadDocumentInfo()
    loadModelStatus()
  }, [documentId, loadDocumentInfo])

  const loadModelStatus = useCallback(async () => {
    try {
      const summary = await getDocumentSummary(documentId)
      if (summary.model_info?.model_status) {
        setModelStatus(summary.model_info.model_status)
      }
    } catch (err) {
      // Ignore errors, will show default
    }
  }, [documentId])

  const handleAnalyze = async () => {
    onAnalyzingChange(true)
    setError(null)
    try {
      const response = await analyzeDocument(documentId)
      
      // Check if already analyzed
      if (response.status === 'already_analyzed') {
        // Reload document info to get existing clauses
        await loadDocumentInfo()
        return
      }
      
      onAnalysisComplete(response.clauses)
      setDocumentInfo(prev => prev ? { ...prev, lastAnalyzed: new Date() } : null)
      
      // Update model status from response
      if (response.model_status) {
        setModelStatus(response.model_status)
      }
      
      // Calculate overall risk
      if (response.clauses.length > 0) {
        const avgRisk = response.clauses.reduce((sum, c) => sum + (c.risk_score || 0), 0) / response.clauses.length
        if (avgRisk < 30) setOverallRisk('low')
        else if (avgRisk < 60) setOverallRisk('medium')
        else if (avgRisk < 80) setOverallRisk('high')
        else setOverallRisk('critical')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze document')
    } finally {
      onAnalyzingChange(false)
    }
  }
  
  // Check if document has already been analyzed
  const isAlreadyAnalyzed = (clausesFromAnalysis && clausesFromAnalysis.length > 0) || documentInfo?.lastAnalyzed !== null

  const handleRiskClick = (clauseIdx: number) => {
    const clauses = clausesFromAnalysis || []
    const clause = clauses.find(c => c.idx === clauseIdx)
    if (clause) {
      setSelectedClause(clause)
      // Scroll to clause in list
      const element = document.querySelector(`[data-clause-idx="${clauseIdx}"]`)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }

  // Clear explanation when clause changes
  useEffect(() => {
    setExplanation(null)
    setExplanationError(null)
    setExplanationLoading(false)
  }, [selectedClause?.idx])

  const handleGenerateExplanation = async () => {
    if (!selectedClause) return

    setExplanationLoading(true)
    setExplanationError(null)

    try {
      const result = await explainClause(documentId, selectedClause.idx, 'detailed')
      setExplanation(result)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to generate explanation'
      setExplanationError(errorMessage)
    } finally {
      setExplanationLoading(false)
    }
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card p-6">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <h2 className="text-2xl font-serif font-bold text-text mb-2">
              {documentInfo?.filename || 'Document'}
            </h2>
            <div className="flex items-center gap-4 text-sm text-text-muted">
              {documentInfo?.lastAnalyzed && (
                <span>Last analyzed: {documentInfo.lastAnalyzed.toLocaleString()}</span>
              )}
              {!documentInfo?.lastAnalyzed && (
                <span className="text-text-subtle">Not analyzed yet</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {documentInfo?.lastAnalyzed && (
              <div className={`px-4 py-2 rounded-full text-sm font-semibold ${getOverallRiskBadge()}`}>
                {overallRisk.toUpperCase()} RISK
              </div>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={handleAnalyze}
                disabled={isAnalyzing || isAlreadyAnalyzed}
                className="btn-primary"
                title={isAlreadyAnalyzed ? 'Document has already been analyzed' : ''}
              >
                {isAnalyzing ? 'Analyzing...' : isAlreadyAnalyzed ? 'Already Analyzed' : 'Analyze Document'}
              </button>
            </div>
          </div>
        </div>
        {error && (
          <div className="mt-4 text-sm text-risk-high bg-risk-high-bg p-4 rounded-xl border border-risk-high">
            {error}
          </div>
        )}
      </div>

      {/* Risk Overview */}
      {(clausesFromAnalysis && clausesFromAnalysis.length > 0) && (
        <RiskOverview
          documentId={documentId}
          onRiskClick={handleRiskClick}
          isAnalyzing={isAnalyzing}
        />
      )}

      {/* Main Grid - 3 Panels */}
      <div className="grid grid-cols-12 gap-6" style={{ height: 'calc(100vh - 350px)', minHeight: '600px' }}>
        {/* Left: Clauses (3 cols) */}
        <div className="col-span-12 lg:col-span-3 h-full overflow-hidden">
          <ClauseList
            documentId={documentId}
            analysisTrigger={analysisTrigger}
            isAnalyzing={isAnalyzing}
            clausesFromAnalysis={clausesFromAnalysis}
            selectedClauseIdx={selectedClause?.idx || null}
            onClauseSelect={setSelectedClause}
          />
        </div>

        {/* Center: PDF Viewer (6 cols) */}
        <div className="col-span-12 lg:col-span-6 h-full overflow-hidden">
          <PDFViewer documentId={documentId} />
        </div>

        {/* Right: Insights Panel (3 cols) */}
        <div className="col-span-12 lg:col-span-3 h-full overflow-hidden">
          <InsightsPanel
            selectedClause={selectedClause}
            documentId={documentId}
            onExpand={() => setIsExpanded(true)}
            explanation={explanation}
            loading={explanationLoading}
            error={explanationError}
            onGenerateExplanation={handleGenerateExplanation}
          />
        </div>
      </div>

      {/* Expanded Insights Modal - Rendered via portal at body level */}
      {isExpanded && selectedClause && typeof document !== 'undefined' && createPortal(
        <div 
          className="fixed top-0 left-0 w-screen h-screen z-[9999] bg-black bg-opacity-50 backdrop-blur-sm flex items-center justify-center p-4" 
          onClick={() => setIsExpanded(false)}
          style={{ 
            position: 'fixed', 
            top: 0, 
            left: 0, 
            width: '100vw', 
            height: '100vh',
            zIndex: 9999
          }}
        >
          <div 
            className="bg-bg-card rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden border border-border" 
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-border flex items-center justify-between flex-shrink-0 bg-bg-card">
              <h2 className="text-xl font-serif font-bold text-text">Clause {selectedClause.idx} - {selectedClause.clause_type || 'Details'}</h2>
              <button
                onClick={() => setIsExpanded(false)}
                className="p-2 text-text-muted hover:text-text rounded-lg hover:bg-bg-muted transition-colors"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 bg-bg-card">
              <InsightsPanel
                selectedClause={selectedClause}
                documentId={documentId}
                explanation={explanation}
                loading={explanationLoading}
                error={explanationError}
                onGenerateExplanation={handleGenerateExplanation}
                isModal={true}
              />
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
