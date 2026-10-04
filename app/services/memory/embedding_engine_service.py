"""
Production-grade Local Embedding Engine using Fast N-Gram Hashing Vectorizer & Cosine Similarity.
Provides zero-external-dependency, zero-latency vector generation for SQLite.
"""
import math
import re
from typing import List, Dict, Any

VECTOR_DIM = 128

class EmbeddingEngineService:
    @staticmethod
    def _hash_ngram(ngram: str) -> int:
        return abs(hash(ngram)) % VECTOR_DIM

    @classmethod
    def generate_embedding(cls, text: str) -> List[float]:
        if not text:
            return [0.0] * VECTOR_DIM
        
        words = re.findall(r"\w+", text.lower())
        vector = [0.0] * VECTOR_DIM
        
        # Unigrams & Bigrams
        ngrams = words + [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
        if not ngrams:
            return vector

        for ng in ngrams:
            idx = cls._hash_ngram(ng)
            vector[idx] += 1.0

        # L2 Normalization
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
            
        return vector

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        return max(0.0, min(1.0, dot))
