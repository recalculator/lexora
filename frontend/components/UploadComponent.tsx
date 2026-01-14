'use client'

import { useState } from 'react'
import { uploadDocument, getSampleContract } from '@/lib/api'

interface UploadComponentProps {
  onUploadSuccess: (documentId: number) => void
}

export default function UploadComponent({ onUploadSuccess }: UploadComponentProps) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [loadingSample, setLoadingSample] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      if (selectedFile.type !== 'application/pdf') {
        setError('Please select a PDF file')
        return
      }
      setFile(selectedFile)
      setError(null)
    }
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file')
      return
    }

    setUploading(true)
    setError(null)

    try {
      const result = await uploadDocument(file)
      onUploadSuccess(result.document_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload document')
    } finally {
      setUploading(false)
    }
  }

  const handleLoadSample = async () => {
    setLoadingSample(true)
    setError(null)

    try {
      const blob = await getSampleContract()
      const sampleFile = new File([blob], 'sample_contract.pdf', { type: 'application/pdf' })
      setFile(sampleFile)
      
      // Automatically upload the sample
      const result = await uploadDocument(sampleFile)
      onUploadSuccess(result.document_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample contract')
    } finally {
      setLoadingSample(false)
    }
  }

  return (
    <div className="card p-8">
      {/* Hero copy */}
      <div className="mb-8 text-center">
        <h2 className="text-3xl font-serif font-bold text-text mb-3">Upload a Contract</h2>
        <p className="text-text-muted">
          Lexora scores clause-level risk and generates negotiation playbooks.
        </p>
      </div>

      {/* Load Sample Contract button */}
      <div className="mb-6">
        <button
          onClick={handleLoadSample}
          disabled={loadingSample || uploading}
          className="btn-secondary w-full"
        >
          {loadingSample ? 'Loading Sample Contract...' : 'Load Sample Contract'}
        </button>
      </div>

      <div className="relative mb-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-border"></div>
        </div>
        <div className="relative flex justify-center text-sm">
          <span className="px-3 bg-bg-card text-text-muted">Or upload your own</span>
        </div>
      </div>
      
      <div className="space-y-5">
        <div>
          <label htmlFor="file-upload" className="block text-sm font-medium text-text mb-2">
            Select PDF file
          </label>
          <input
            id="file-upload"
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            className="block w-full text-sm text-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-bg-muted file:text-brand hover:file:bg-border transition-colors"
          />
        </div>

        {file && (
          <div className="text-sm text-text-muted bg-bg-muted p-3 rounded-xl border border-border">
            <span className="font-medium">Selected:</span> {file.name} ({(file.size / 1024).toFixed(2)} KB)
          </div>
        )}

        {error && (
          <div className="text-sm text-risk-high bg-risk-high-bg p-4 rounded-xl border border-risk-high">
            {error}
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="btn-primary w-full"
        >
          {uploading ? 'Uploading...' : 'Upload and Extract Text'}
        </button>
      </div>
    </div>
  )
}
