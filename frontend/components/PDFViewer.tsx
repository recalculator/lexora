'use client'

import { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/esm/Page/AnnotationLayer.css'
import 'react-pdf/dist/esm/Page/TextLayer.css'

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`

interface PDFViewerProps {
  documentId: number
}

export default function PDFViewer({ documentId }: PDFViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)

  const pdfUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/document/${documentId}/pdf`

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
  }

  // Reset page number when documentId changes
  const onDocumentLoadError = () => {
    setNumPages(null)
    setPageNumber(1)
  }

  return (
    <div className="card h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-border flex items-center justify-between flex-shrink-0">
        <h3 className="text-base font-serif font-bold text-text">Document Viewer</h3>
        {numPages && (
          <span className="text-xs text-text-muted">Page {pageNumber} of {numPages}</span>
        )}
      </div>

      {/* PDF Content */}
      <div className="flex-1 overflow-auto p-5 bg-bg-card">
        <Document
          key={documentId}
          file={pdfUrl}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={
            <div className="flex items-center justify-center h-full">
              <div className="text-sm text-text-muted">Loading PDF...</div>
            </div>
          }
          error={
            <div className="flex items-center justify-center h-full">
              <div className="text-sm text-risk-high">Failed to load PDF</div>
            </div>
          }
        >
          <Page 
            pageNumber={pageNumber} 
            renderTextLayer={true} 
            renderAnnotationLayer={true}
            className="shadow-lg"
          />
        </Document>
      </div>

      {/* Pagination */}
      {numPages && (
        <div className="p-5 border-t border-border flex items-center justify-between flex-shrink-0">
          <button
            onClick={() => setPageNumber(Math.max(1, pageNumber - 1))}
            disabled={pageNumber <= 1}
            className="btn-secondary text-xs px-3 py-1.5"
          >
            Previous
          </button>
          <span className="text-xs text-text-muted">
            Page {pageNumber} of {numPages}
          </span>
          <button
            onClick={() => setPageNumber(Math.min(numPages, pageNumber + 1))}
            disabled={pageNumber >= numPages}
            className="btn-secondary text-xs px-3 py-1.5"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
