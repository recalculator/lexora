"""Retrieval service using TF-IDF."""
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from app.core.logging import get_logger

logger = get_logger()


class TFIDFRetrieval:
    """TF-IDF based retrieval for RAG."""
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
        )
        self.document_vectors = None
        self.documents = []
    
    def index_documents(self, documents: List[str]):
        """
        Index documents for retrieval.
        
        Args:
            documents: List of document texts (clauses)
        """
        self.documents = documents
        if not documents:
            logger.warning("No documents to index")
            return
        
        try:
            self.document_vectors = self.vectorizer.fit_transform(documents)
            logger.info("Indexed documents for retrieval", num_docs=len(documents))
        except Exception as e:
            logger.error("Failed to index documents", error=str(e))
            self.document_vectors = None
    
    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[int, str, float]]:
        """
        Retrieve top-k most relevant documents.
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of tuples (doc_index, doc_text, similarity_score)
        """
        if self.document_vectors is None or not self.documents:
            logger.warning("No documents indexed, returning empty results")
            return []
        
        try:
            # Vectorize query
            query_vector = self.vectorizer.transform([query])
            
            # Compute similarities
            similarities = cosine_similarity(query_vector, self.document_vectors)[0]
            
            # Get top-k
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0:
                    results.append((
                        int(idx),
                        self.documents[idx],
                        float(similarities[idx])
                    ))
            
            logger.info("Retrieved documents", query_length=len(query), num_results=len(results))
            return results
        except Exception as e:
            logger.error("Retrieval failed", error=str(e))
            return []


def create_retrieval(clauses: List[Dict[str, any]]) -> TFIDFRetrieval:
    """Create and populate retrieval index from clauses."""
    retrieval = TFIDFRetrieval()
    documents = [clause.get("text", "") for clause in clauses]
    retrieval.index_documents(documents)
    return retrieval
