const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Document {
  id: number
  filename: string
  created_at: string
}

export interface Clause {
  idx: number
  text: string
  clause_type: string | null
  risk_score: number | null
  confidence: number | null
}

export interface UploadResponse {
  document_id: number
  filename: string
  status: string
  text_length: number
}

export interface AnalyzeResponse {
  document_id: number
  status: string
  num_clauses: number
  clauses: Clause[]
  model_status?: 'onnx' | 'sklearn' | 'dummy'
}

export interface PlaybookResponse {
  document_summary: string
  overall_risk_assessment: string
  priority_clauses: Array<{
    clause_index: number
    clause_type: string | null
    risk_level: string
    concern: string
    recommendation: string
    negotiation_strategy: string
    citation: string
  }>
  general_recommendations: string[]
  key_provisions: string[]
}

export interface RedlinesResponse {
  summary: string
  priority_redlines: Array<{
    clause_index: number
    clause_type: string | null
    original_text: string
    suggested_change: string
    rationale: string
    risk_reduction: string
    citation: string
  }>
  optional_redlines: Array<{
    clause_index: number
    clause_type: string | null
    original_text: string
    suggested_change: string
    rationale: string
    risk_reduction: string
    citation: string
  }>
  general_notes: string[]
}

export interface ReportResponse {
  document: Document
  text: {
    length: number
    has_text: boolean
  }
  clauses: Clause[]
  playbook: PlaybookResponse | null
  redlines: RedlinesResponse | null
}

export interface TopRisk {
  idx: number
  clause_type: string | null
  risk_score: number | null
  confidence: number | null
  preview: string
}

export interface ModelInfo {
  clause_model: string
  version: string
  supported_clause_types: string[]
  avg_confidence: number
  low_confidence_count: number
  low_conf_threshold: number
  model_status: 'onnx' | 'sklearn' | 'dummy'
}

export interface SummaryResponse {
  document_id: number
  top_risks: TopRisk[]
  model_info: ModelInfo
}

export interface QuotedSpan {
  quote: string
  reason: string
}

export interface ExplainResponse {
  document_id: number
  clause_idx: number
  clause_type: string | null
  risk_score: number
  confidence: number
  explanation: string
  risk_drivers: string[]
  suggested_negotiation_moves: string[]
  quoted_spans: QuotedSpan[]
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_URL}/api/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error('Failed to upload document')
  }

  return response.json()
}

export async function analyzeDocument(documentId: number): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_URL}/api/analyze/${documentId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error('Failed to analyze document')
  }

  return response.json()
}

export async function generatePlaybook(documentId: number): Promise<PlaybookResponse> {
  const response = await fetch(`${API_URL}/api/playbook/${documentId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error('Failed to generate playbook')
  }

  return response.json()
}

export async function generateRedlines(documentId: number): Promise<RedlinesResponse> {
  const response = await fetch(`${API_URL}/api/redlines/${documentId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error('Failed to generate redlines')
  }

  return response.json()
}

export async function getReport(documentId: number): Promise<ReportResponse> {
  const response = await fetch(`${API_URL}/api/report/${documentId}`)

  if (!response.ok) {
    throw new Error('Failed to get report')
  }

  return response.json()
}

export async function getDocumentSummary(documentId: number): Promise<SummaryResponse> {
  const response = await fetch(`${API_URL}/api/document/${documentId}/summary`)

  if (!response.ok) {
    throw new Error('Failed to get document summary')
  }

  return response.json()
}

export async function explainClause(
  documentId: number,
  clauseIdx: number,
  style: 'concise' | 'detailed' = 'concise'
): Promise<ExplainResponse> {
  const response = await fetch(`${API_URL}/api/explain/${documentId}/${clauseIdx}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ style }),
  })

  if (!response.ok) {
    throw new Error('Failed to explain clause')
  }

  return response.json()
}

export async function getSampleContract(): Promise<Blob> {
  const response = await fetch(`${API_URL}/api/sample_contract`)

  if (!response.ok) {
    throw new Error('Failed to get sample contract')
  }

  return response.blob()
}
