'use client'

import { useState, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { analyzeDocument, generatePlaybook, generateRedlines } from '@/lib/api'
import TopRisksCard from './TopRisksCard'
import 'react-pdf/dist/esm/Page/AnnotationLayer.css'
import 'react-pdf/dist/esm/Page/TextLayer.css'

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`

interface DocumentViewProps {
  documentId: number
  onRiskClick?: (clauseIdx: number) => void
  onAnalysisComplete?: (clauses: any[]) => void
  isAnalyzing?: boolean
  onAnalyzingChange?: (analyzing: boolean) => void
}

export default function DocumentView({ documentId, onRiskClick, onAnalysisComplete, isAnalyzing: externalAnalyzing, onAnalyzingChange }: DocumentViewProps) {
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [internalAnalyzing, setInternalAnalyzing] = useState(false)
  const [generatingPlaybook, setGeneratingPlaybook] = useState(false)
  const [generatingRedlines, setGeneratingRedlines] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [lastAnalyzed, setLastAnalyzed] = useState<Date | null>(null)
  
  const analyzing = externalAnalyzing !== undefined ? externalAnalyzing : internalAnalyzing

  const pdfUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/document/${documentId}/pdf`

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
  }

  const handleAnalyze = async () => {
    const setAnalyzingState = (value: boolean) => {
      if (externalAnalyzing === undefined) {
        setInternalAnalyzing(value)
      }
      onAnalyzingChange?.(value)
    }
    
    setAnalyzingState(true)
    setError(null)
    try {
      const response = await analyzeDocument(documentId)
      setAnalysisComplete(true)
      setLastAnalyzed(new Date())
      
      // Notify parent with clauses from response
      if (response.clauses && response.clauses.length > 0) {
        onAnalysisComplete?.(response.clauses)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze document')
    } finally {
      setAnalyzingState(false)
    }
  }

  const handleGeneratePlaybook = async () => {
    setGeneratingPlaybook(true)
    setError(null)
    try {
      await generatePlaybook(documentId)
      // Trigger refetch in ReportView via parent callback if needed
      // For now, just show success - user can navigate to Report tab
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate playbook')
    } finally {
      setGeneratingPlaybook(false)
    }
  }

  const handleGenerateRedlines = async () => {
    setGeneratingRedlines(true)
    setError(null)
    try {
      await generateRedlines(documentId)
      // Trigger refetch in ReportView via parent callback if needed
      // For now, just show success - user can navigate to Report tab
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate redlines')
    } finally {
      setGeneratingRedlines(false)
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4">Document Viewer</h2>
      
      <div className="mb-4 flex gap-2 flex-wrap">
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="bg-primary-600 text-white px-4 py-2 rounded-md hover:bg-primary-700 disabled:bg-gray-400"
        >
          {analyzing ? 'Analyzing...' : 'Analyze Document'}
        </button>
        <button
          onClick={handleGeneratePlaybook}
          disabled={generatingPlaybook}
          className="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700 disabled:bg-gray-400"
        >
          {generatingPlaybook ? 'Generating...' : 'Generate Playbook'}
        </button>
        <button
          onClick={handleGenerateRedlines}
          disabled={generatingRedlines}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
        >
          {generatingRedlines ? 'Generating...' : 'Generate Redlines'}
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 p-3 rounded mb-4">
          {error}
        </div>
      )}

      {analysisComplete && (
        <div className="mb-4">
          <TopRisksCard documentId={documentId} onRiskClick={onRiskClick} />
          {lastAnalyzed && (
            <div className="text-xs text-gray-500 mt-2">
              Last analyzed: {lastAnalyzed.toLocaleTimeString()}
            </div>
          )}
        </div>
      )}

      <div className="border rounded-lg overflow-auto max-h-[800px]">
        <Document
          file={pdfUrl}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={<div className="p-4">Loading PDF...</div>}
          error={<div className="p-4 text-red-600">Failed to load PDF. The PDF may not be accessible directly.</div>}
        >
          <Page pageNumber={pageNumber} renderTextLayer={true} renderAnnotationLayer={true} />
        </Document>
      </div>

      {numPages && (
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}
            disabled={pageNumber <= 1}
            className="px-4 py-2 bg-gray-200 rounded-md hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {pageNumber} of {numPages}
          </span>
          <button
            onClick={() => setPageNumber(Math.min(numPages, pageNumber + 1))}
            disabled={pageNumber >= numPages}
            className="px-4 py-2 bg-gray-200 rounded-md hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
