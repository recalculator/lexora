"""PDF text extraction service."""
import pdfplumber
import pypdf
from pathlib import Path
from typing import Tuple
from app.core.logging import get_logger

logger = get_logger()


def extract_text(pdf_path: str) -> Tuple[str, bool]:
    """
    Extract text from PDF.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Tuple of (extracted_text, success_flag)
    """
    pdf_path_obj = Path(pdf_path)
    if not pdf_path_obj.exists():
        logger.error("PDF file not found", pdf_path=pdf_path)
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    text = ""
    success = False
    
    # Try pdfplumber first (better for formatted text)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            text = "\n\n".join(pages_text)
            success = True
            logger.info("Extracted text using pdfplumber", pages=len(pdf.pages), text_length=len(text))
    except Exception as e:
        logger.warning("pdfplumber extraction failed, trying pypdf", error=str(e))
        
        # Fallback to pypdf
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = pypdf.PdfReader(file)
                pages_text = []
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                text = "\n\n".join(pages_text)
                success = True
                logger.info("Extracted text using pypdf", pages=len(pdf_reader.pages), text_length=len(text))
        except Exception as e2:
            logger.error("Both PDF extraction methods failed", pdfplumber_error=str(e), pypdf_error=str(e2))
            raise ValueError(f"Failed to extract text from PDF: {str(e2)}")
    
    if not text.strip():
        logger.warning("Extracted text is empty", pdf_path=pdf_path)
        raise ValueError("Extracted text is empty")
    
    return text, success
