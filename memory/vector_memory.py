"""
JARVIS AI — Vector Semantic Memory (Phase 6)

Retrieves unstructured conversational past memory using
pure NumPy cosine similarity and dense embeddings (SentenceTransformers).
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import List, Tuple

from loguru import logger
import numpy as np

# Lazy import for transformers
_st = None


class VectorMemory:
    """NumPy-backed similarity search for conversation history."""

    def __init__(self, storage_dir: str = "logs/memory/vectors"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = str(self.storage_dir / "embeddings.pkl")
        self.metadata_path = str(self.storage_dir / "metadata.json")
        
        self.model_name = "all-MiniLM-L6-v2"
        self._model = None
        self._embeddings: np.ndarray = np.empty((0, 384), dtype=np.float32)
        self._metadata: List[str] = []
        self._dimension = 384  # MiniLM size

    def initialize(self) -> None:
        """Load embeddings model and vector indices."""
        global _st
        if _st is None:
            from sentence_transformers import SentenceTransformer
            _st = SentenceTransformer
            
        logger.info(f"Loading semantic memory model ({self.model_name})...")
        self._model = _st(self.model_name)
        
        # Load indices
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            with open(self.index_path, "rb") as f:
                self._embeddings = pickle.load(f)
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            logger.info(f"Loaded {len(self._metadata)} vector memories.")
        else:
            self._embeddings = np.empty((0, self._dimension), dtype=np.float32)
            self._metadata = []

    def add_memory(self, memory_text: str) -> None:
        """Embed and append memory to the NumPy index."""
        if not self._model:
            self.initialize()
            
        # Encode
        vec = self._model.encode([memory_text], convert_to_numpy=True)
        
        # Append
        self._embeddings = np.vstack((self._embeddings, vec))
        self._metadata.append(memory_text)
        
        # Save to disk
        self._save()
        logger.debug("Core memory encoded & stored.")

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Search similar memories using cosine similarity."""
        if not self._model:
            self.initialize()
            
        if len(self._metadata) == 0:
            return []
            
        k = min(top_k, len(self._metadata))
        
        # Encode query
        vec = self._model.encode([query], convert_to_numpy=True)
        
        # Normalize
        q_norm = vec / np.linalg.norm(vec, axis=1, keepdims=True)
        db_norm = self._embeddings / np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        
        # Cosine similarity (1.0 = exact match)
        similarities = np.dot(db_norm, q_norm.T).flatten()
        
        # Sort indices by highest similarity
        top_indices = np.argsort(similarities)[::-1][:k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            # Filter if score is very low (e.g. < 0.3)
            if score > 0.3:
                results.append((self._metadata[idx], score))
                
        return results

    def _save(self) -> None:
        """Serialize memory to disk."""
        with open(self.index_path, "wb") as f:
            pickle.dump(self._embeddings, f)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f)
