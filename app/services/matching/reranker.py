"""
Reranker Service - Re-score and re-rank candidate profiles.

Modular design: supports multiple backends (Jina, Cohere, etc.)
Swap implementations to compare via LangSmith evals.
"""

import os
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()


@dataclass
class RankedResult:
    """A single reranked result."""
    index: int           # Original index in input list
    text: str            # The document text
    score: float         # Relevance score (0-1)
    lead_id: Optional[str] = None  # Optional reference to lead


class BaseReranker(ABC):
    """Abstract base class for rerankers."""
    
    @abstractmethod
    def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_n: Optional[int] = None,
        lead_ids: Optional[List[str]] = None
    ) -> List[RankedResult]:
        """
        Rerank documents by relevance to query.
        
        Args:
            query: The search query (ICP description)
            documents: List of document texts (profile summaries)
            top_n: Number of results to return (None = return ALL)
            lead_ids: Optional list of lead IDs matching documents
        
        Returns:
            List of RankedResult, sorted by score descending
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this reranker for logging/tracing."""
        pass


class JinaReranker(BaseReranker):
    """Jina AI Reranker implementation."""
    
    API_URL = "https://api.jina.ai/v1/rerank"
    MODEL = "jina-reranker-v2-base-multilingual"
    
    def __init__(self):
        self.api_key = os.getenv("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("Missing JINA_API_KEY environment variable")
    
    @property
    def name(self) -> str:
        return "jina"
    
    def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_n: Optional[int] = None,
        lead_ids: Optional[List[str]] = None
    ) -> List[RankedResult]:
        """Rerank using Jina API."""
        
        if not documents:
            return []
        
        # If top_n not specified, return ALL documents
        if top_n is None:
            top_n = len(documents)
        else:
            top_n = min(top_n, len(documents))
        
        try:
            response = httpx.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.MODEL,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for item in data.get("results", []):
                idx = item.get("index", 0)
                results.append(RankedResult(
                    index=idx,
                    text=documents[idx] if idx < len(documents) else "",
                    score=item.get("relevance_score", 0.0),
                    lead_id=lead_ids[idx] if lead_ids and idx < len(lead_ids) else None
                ))
            
            # Sort by score descending (should already be sorted, but ensure)
            results.sort(key=lambda x: x.score, reverse=True)
            
            print(f"[Jina Reranker] Reranked {len(documents)} docs -> {len(results)} results")
            
            return results
            
        except httpx.HTTPStatusError as e:
            print(f"[Jina Reranker] HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            print(f"[Jina Reranker] Error: {e}")
            raise


class NoOpReranker(BaseReranker):
    """
    No-op reranker - returns documents in original order.
    Useful for A/B testing: compare with vs without reranker.
    """
    
    @property
    def name(self) -> str:
        return "noop"
    
    def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_n: Optional[int] = None,
        lead_ids: Optional[List[str]] = None
    ) -> List[RankedResult]:
        """Return documents in original order with default scores."""
        # If top_n not specified, return ALL documents
        docs_to_process = documents if top_n is None else documents[:top_n]
        
        results = []
        for i, doc in enumerate(docs_to_process):
            results.append(RankedResult(
                index=i,
                text=doc,
                score=1.0 - (i * 0.01),  # Decreasing scores
                lead_id=lead_ids[i] if lead_ids and i < len(lead_ids) else None
            ))
        return results


# Future implementations:
# class CohereReranker(BaseReranker): ...
# class ZeroEntropyReranker(BaseReranker): ...


def get_reranker(name: str = "jina") -> BaseReranker:
    """
    Factory function to get a reranker by name.
    
    Args:
        name: Reranker name ("jina", "cohere", "noop", etc.)
    
    Returns:
        Reranker instance
    """
    rerankers = {
        "jina": JinaReranker,
        "noop": NoOpReranker,
        # "cohere": CohereReranker,  # Future
        # "zeroentropy": ZeroEntropyReranker,  # Future
    }
    
    if name not in rerankers:
        raise ValueError(f"Unknown reranker: {name}. Available: {list(rerankers.keys())}")
    
    return rerankers[name]()
