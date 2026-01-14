"""Seed sample data."""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Document, DocumentText
from datetime import datetime

def seed_data():
    """Seed sample data."""
    db: Session = SessionLocal()
    
    try:
        # Check if already seeded
        existing = db.query(Document).first()
        if existing:
            print("Database already contains data. Skipping seed.")
            return
        
        # Create a sample document (text-only for demo)
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
        
        doc = Document(
            filename="sample-contract.pdf",
            original_filename="sample-contract.pdf",
            created_at=datetime.utcnow(),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        doc_text = DocumentText(
            document_id=doc.id,
            text=sample_text,
            json_chunks=None,
        )
        db.add(doc_text)
        db.commit()
        
        print(f"Seeded sample document with ID: {doc.id}")
        
    except Exception as e:
        print(f"Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
