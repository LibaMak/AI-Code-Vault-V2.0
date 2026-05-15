"""Pluggable embedding provider.

Tries to use `sentence-transformers` locally if installed; otherwise
falls back to a deterministic SHA256->random vector generator.

API:
- get_embedding(text: str) -> List[float]
- get_embeddings(texts: List[str]) -> List[List[float]]
"""
from typing import List
import os

_model = None
_use_local = False

try:
    from sentence_transformers import SentenceTransformer
    _use_local = True
except Exception:
    _use_local = False

# Default model name for sentence-transformers fallback
_DEFAULT_MODEL = os.getenv('LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')

import hashlib
import numpy as np


def _init_local_model():
    global _model
    if _model is None and _use_local:
        try:
            _model = SentenceTransformer(_DEFAULT_MODEL)
        except Exception:
            _model = None


def get_embedding(text: str) -> List[float]:
    """Return an embedding for a single text."""
    if not text:
        return [0.0] * 1536

    if _use_local:
        _init_local_model()
        if _model is not None:
            try:
                vec = _model.encode(text)
                # Convert to Python floats
                return [float(x) for x in vec.tolist()]
            except Exception:
                pass

    # Deterministic SHA256 -> seeded random fallback (1536 dims)
    hash_obj = hashlib.sha256(text.encode('utf-8'))
    seed = int(hash_obj.hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    return rng.rand(1536).tolist()


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Batch embedding function."""
    if _use_local:
        _init_local_model()
        if _model is not None:
            try:
                vecs = _model.encode(texts)
                return [[float(x) for x in v.tolist()] for v in vecs]
            except Exception:
                pass

    return [get_embedding(t) for t in texts]
