import { render, screen } from '@testing-library/react'
import UploadComponent from '../UploadComponent'

describe('UploadComponent', () => {
  it('renders upload form', () => {
    const mockOnUploadSuccess = jest.fn()
    render(<UploadComponent onUploadSuccess={mockOnUploadSuccess} />)
    
    expect(screen.getByText('Upload Contract PDF')).toBeInTheDocument()
    expect(screen.getByText('Select PDF file')).toBeInTheDocument()
  })
})
