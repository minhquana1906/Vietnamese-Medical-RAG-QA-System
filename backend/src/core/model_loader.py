"""
Singleton model loader for local inference.
Loads embedding, reranking, and guardrails models once at startup.
"""

import torch
from loguru import logger
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer
from typing import Optional, List, Tuple

from .model_config import (
    get_embedding_model,
    get_reranking_model,
    get_guardrails_model,
    get_guardrails_threshold,
)


class ModelRegistry:
    """Singleton registry for loaded models"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedding_model: Optional[SentenceTransformer] = None
        self.rerank_model = None
        self.rerank_tokenizer = None
        self.guard_model = None
        self.guard_tokenizer = None
        self._initialized = True

        logger.info(f"🔧 ModelRegistry initialized (device={self.device})")

    def load_models(self):
        """Load all models at startup"""
        logger.info("📦 Loading models...")

        try:
            # Embedding model
            embedding_repo = get_embedding_model()
            logger.info(f"Loading embedding: {embedding_repo}")
            self.embedding_model = SentenceTransformer(
                embedding_repo, device=self.device
            )
            logger.info(f"✅ Embedding model loaded")

            # Reranking model
            rerank_repo = get_reranking_model()
            logger.info(f"Loading reranking: {rerank_repo}")
            self.rerank_tokenizer = AutoTokenizer.from_pretrained(rerank_repo)
            self.rerank_model = AutoModel.from_pretrained(rerank_repo).to(self.device)
            self.rerank_model.eval()
            logger.info(f"✅ Reranking model loaded")

            # Guardrails model
            guard_repo = get_guardrails_model()
            logger.info(f"Loading guardrails: {guard_repo}")
            self.guard_tokenizer = AutoTokenizer.from_pretrained(guard_repo)
            self.guard_model = AutoModel.from_pretrained(guard_repo).to(self.device)
            self.guard_model.eval()
            logger.info(f"✅ Guardrails model loaded")

            logger.info("🎉 All models loaded successfully!")

        except Exception as e:
            logger.error(f"❌ Failed to load models: {e}")
            raise

    def is_ready(self) -> bool:
        """Check if all models are loaded"""
        return (
            self.embedding_model is not None
            and self.rerank_model is not None
            and self.guard_model is not None
        )

    # ============= Embedding Methods =============

    def embed_texts(
        self, texts: List[str], normalize: bool = True
    ) -> List[List[float]]:
        """Generate embeddings for texts"""
        if self.embedding_model is None:
            raise RuntimeError("Embedding model not loaded")

        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            batch_size=32,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    # ============= Reranking Methods =============

    def rerank_documents(
        self, query: str, documents: List[str], top_n: int = 5
    ) -> Tuple[List[float], List[int]]:
        """
        Rerank documents based on query relevance.
        Returns (scores, sorted_indices)
        """
        if self.rerank_model is None or self.rerank_tokenizer is None:
            raise RuntimeError("Reranking model not loaded")

        # Prepare pairs
        pairs = [[query, doc] for doc in documents]

        # Tokenize
        inputs = self.rerank_tokenizer(
            pairs, padding=True, truncation=True, return_tensors="pt", max_length=512
        ).to(self.device)

        # Inference
        with torch.no_grad():
            outputs = self.rerank_model(**inputs)

            # Extract relevance scores
            if hasattr(outputs, "logits"):
                scores = outputs.logits.squeeze()
            else:
                # Use [CLS] token pooling
                scores = outputs.last_hidden_state[:, 0, :].mean(dim=-1)

        # Convert to list
        scores_list = scores.cpu().tolist()

        # Sort by relevance
        sorted_indices = sorted(
            range(len(scores_list)), key=lambda i: scores_list[i], reverse=True
        )[:top_n]

        sorted_scores = [scores_list[i] for i in sorted_indices]

        return sorted_scores, sorted_indices

    # ============= Guardrails Methods =============

    def check_safety(
        self, text: str, check_type: str = "input"
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Check content safety.
        Returns (is_safe, safety_score, category)
        """
        if self.guard_model is None or self.guard_tokenizer is None:
            raise RuntimeError("Guardrails model not loaded")

        # Tokenize
        inputs = self.guard_tokenizer(
            text, padding=True, truncation=True, return_tensors="pt", max_length=512
        ).to(self.device)

        # Inference
        with torch.no_grad():
            outputs = self.guard_model(**inputs)

            # Extract safety score
            if hasattr(outputs, "logits"):
                logits = outputs.logits.squeeze()
                # Binary classification: [unsafe, safe]
                safety_score = torch.softmax(logits, dim=-1)[-1].item()
            else:
                # Fallback: use [CLS] token
                cls_embedding = outputs.last_hidden_state[:, 0, :].squeeze()
                safety_score = torch.sigmoid(cls_embedding.mean()).item()

        # Check threshold
        threshold = get_guardrails_threshold()
        is_safe = safety_score >= threshold

        # Determine category if unsafe
        category = None
        if not is_safe:
            text_lower = text.lower()
            if any(word in text_lower for word in ["suicide", "self-harm", "kill"]):
                category = "harmful"
            elif any(word in text_lower for word in ["sexual", "offensive"]):
                category = "inappropriate"
            else:
                category = "unsafe_content"

        return is_safe, safety_score, category


# Global instance
_model_registry = None


def get_model_registry() -> ModelRegistry:
    """Get singleton model registry"""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry
