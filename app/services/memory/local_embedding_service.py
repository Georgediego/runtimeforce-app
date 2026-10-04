"""
Local Embedding Service with HuggingFace Hub Warning Suppression.
"""
import os
import math
import re
import logging
from typing import List, Optional

# Suppress HuggingFace unauthenticated hub warning
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

from app.core.interfaces.embedding_engine_interface import IEmbeddingEngine

logger = logging.getLogger("runtimeforce.service.memory.local_embedding")

VECTOR_DIM = 384

class LocalEmbeddingService(IEmbeddingEngine):
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.session = None
        self.tokenizer = None
        self._init_onnx()

    def _init_onnx(self):
        try:
            from transformers import AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                "sentence-transformers/all-MiniLM-L6-v2",
                local_files_only=False
            )
            logger.info("AutoTokenizer initialized for all-MiniLM-L6-v2.")
        except Exception as e:
            logger.debug(f"Transformers AutoTokenizer fallback: {e}")
            self.tokenizer = None

        if self.model_path and os.path.exists(self.model_path):
            try:
                import onnxruntime as ort
                self.session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
                logger.info(f"Loaded ONNX Embedding Session from {self.model_path}")
            except Exception as e:
                logger.warning(f"ONNX session load failed, using fallback: {e}")
                self.session = None

    def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * VECTOR_DIM

        if self.session and self.tokenizer:
            try:
                import numpy as np
                inputs = self.tokenizer(text, return_tensors="np", padding=True, truncation=True, max_length=128)
                onnx_inputs = {k: v for k, v in inputs.items() if k in [i.name for i in self.session.get_inputs()]}
                outputs = self.session.run(None, onnx_inputs)
                
                token_embeddings = outputs[0]
                attention_mask = inputs.get("attention_mask")
                
                if attention_mask is not None:
                    input_mask_expanded = np.expand_dims(attention_mask, -1)
                    sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
                    sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
                    pooled = sum_embeddings / sum_mask
                else:
                    pooled = np.mean(token_embeddings, axis=1)

                raw_vec = pooled[0].tolist()
                return self._normalize_vector(raw_vec[:VECTOR_DIM])
            except Exception as e:
                logger.debug(f"ONNX inference failed, using hash fallback: {e}")

        return self._hash_vectorizer_fallback(text)

    def _hash_vectorizer_fallback(self, text: str) -> List[float]:
        words = re.findall(r"\w+", text.lower())
        vector = [0.0] * VECTOR_DIM
        if not words:
            return vector

        ngrams = words + [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
        for ng in ngrams:
            idx = abs(hash(ng)) % VECTOR_DIM
            vector[idx] += 1.0

        return self._normalize_vector(vector)

    @staticmethod
    def _normalize_vector(vector: List[float]) -> List[float]:
        mag = math.sqrt(sum(v * v for v in vector))
        if mag > 0:
            return [v / mag for v in vector]
        return [0.0] * VECTOR_DIM
