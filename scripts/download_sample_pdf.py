"""Download a sample contract PDF for demo."""
import requests
from pathlib import Path

def download_sample_pdf():
    """Download a sample contract PDF."""
    # Use a publicly available sample contract PDF
    # In production, you might want to use a specific sample
    sample_urls = [
        "https://www.sec.gov/files/contracts_sample.pdf",  # Example - replace with actual URL
    ]
    
    output_dir = Path("backend/storage")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "sample-contract.pdf"
    
    # For MVP, create a simple text file that can be used as a test
    # In production, download an actual PDF
    print("Creating sample contract text file...")
    
    sample_text = """CONTRACT AGREEMENT

This Agreement is entered into on [DATE] between Party A and Party B.

1. TERMINATION
Either party may terminate this agreement with 30 days written notice. Upon termination, all rights and obligations shall cease immediately.

2. INDEMNIFICATION
Party A agrees to indemnify and hold harmless Party B from any claims arising from Party A's breach of this agreement.

3. LIABILITY CAP
The maximum liability of either party shall not exceed $100,000. This limitation does not apply to intentional misconduct.

4. CONFIDENTIALITY
Both parties agree to keep all information confidential for a period of 5 years after termination of this agreement.

5. INTELLECTUAL PROPERTY
All intellectual property rights shall remain with the original creator. No license is granted except as expressly stated herein.

6. GOVERNING LAW
This agreement shall be governed by the laws of the State of California, USA.
"""
    
    # Note: This creates a text file, not a PDF
    # For actual PDF, you'd need to use a library like reportlab
    # or download a real PDF from a URL
    print(f"Sample contract text created at {output_path}")
    print("NOTE: For actual PDF files, use a PDF generator or download from a URL.")
    
    return output_path

if __name__ == "__main__":
    download_sample_pdf()
