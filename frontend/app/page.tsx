'use client'

import { useState, useCallback, useRef } from 'react'
import UploadComponent from '@/components/UploadComponent'
import AnalyzePage from '@/components/AnalyzePage'
import ReportView from '@/components/ReportView'
import { Clause } from '@/lib/api'

export default function Home() {
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'upload' | 'analyze' | 'report'>('upload')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [clausesFromAnalysis, setClausesFromAnalysis] = useState<Clause[] | undefined>(undefined)
  const analysisTriggerRef = useRef(0)

  const handleUploadSuccess = (id: number) => {
    setDocumentId(id)
    setActiveTab('analyze')
    // Reset state for new document
    setClausesFromAnalysis(undefined)
    analysisTriggerRef.current = 0
  }

  const handleAnalysisComplete = useCallback((clauses: Clause[]) => {
    setClausesFromAnalysis(clauses)
    analysisTriggerRef.current += 1
  }, [])

  const handleAnalyzingChange = useCallback((analyzing: boolean) => {
    setIsAnalyzing(analyzing)
  }, [])

  return (
    <main className="min-h-screen bg-bg">
      <header className="bg-bg-card border-b border-border shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex items-baseline gap-3">
            <h1 className="text-3xl font-serif font-bold text-brand">Lexora</h1>
            <div className="h-6 w-px bg-border"></div>
            <p className="text-sm text-text-muted font-sans">Legal Contract Analysis Platform</p>
          </div>
          <div className="mt-2 h-0.5 w-24 bg-brand"></div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs */}
        <div className="mb-8 border-b border-border">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('upload')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'upload'
                  ? 'border-brand text-brand'
                  : 'border-transparent text-text-muted hover:text-text hover:border-border-strong'
              }`}
            >
              Upload
            </button>
            {documentId && (
              <>
                <button
                  onClick={() => setActiveTab('analyze')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === 'analyze'
                      ? 'border-brand text-brand'
                      : 'border-transparent text-text-muted hover:text-text hover:border-border-strong'
                  }`}
                >
                  Analyze
                </button>
                <button
                  onClick={() => setActiveTab('report')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === 'report'
                      ? 'border-brand text-brand'
                      : 'border-transparent text-text-muted hover:text-text hover:border-border-strong'
                  }`}
                >
                  Report
                </button>
              </>
            )}
          </nav>
        </div>

        {/* Content */}
        {activeTab === 'upload' && (
          <div className="max-w-2xl mx-auto">
            <UploadComponent onUploadSuccess={handleUploadSuccess} />
          </div>
        )}

        {activeTab === 'analyze' && documentId && (
          <AnalyzePage
            documentId={documentId}
            isAnalyzing={isAnalyzing}
            onAnalyzingChange={handleAnalyzingChange}
            onAnalysisComplete={handleAnalysisComplete}
            clausesFromAnalysis={clausesFromAnalysis}
            analysisTrigger={analysisTriggerRef.current}
          />
        )}

        {activeTab === 'report' && documentId && (
          <ReportView 
            documentId={documentId}
            refetchTrigger={analysisTriggerRef.current}
          />
        )}
      </div>
    </main>
  )
}
