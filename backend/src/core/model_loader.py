"""
Qwen3 Model Registry - Implements official Qwen3 best practices
Loads embedding, reranking, and guardrails models with proper Qwen3 specifications.

References:
- Qwen3-Embedding: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- Qwen3-Reranker: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- Qwen3Guard: https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B
"""

import torch
import torch.nn.functional as F
from loguru import logger
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
from typing import Optional, List, Tuple, Dict, Any
import re

from .model_config import (
    get_embedding_model,
    get_reranking_model,
    get_guardrails_model,
)


class ModelRegistry:
    """Qwen3 Model Registry following official specifications"""

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

        # Qwen3-Embedding-0.6B
        self.embedding_model = None
        self.embedding_tokenizer = None

        # Qwen3-Reranker-0.6B
        self.rerank_model = None
        self.rerank_tokenizer = None

        # Qwen3Guard-Gen-0.6B
        self.guard_model = None
        self.guard_tokenizer = None

        self._initialized = True
        logger.info(f"🔧 Qwen3 ModelRegistry initialized (device={self.device})")

    def load_models(self):
        """Load all Qwen3 models at startup"""
        logger.info("📦 Loading Qwen3 models...")

        try:
            # Qwen3-Embedding-0.6B
            embedding_repo = get_embedding_model()
            logger.info(f"Loading Qwen3-Embedding: {embedding_repo}")
            self.embedding_tokenizer = AutoTokenizer.from_pretrained(embedding_repo)
            self.embedding_model = AutoModel.from_pretrained(
                embedding_repo, trust_remote_code=True
            ).to(self.device)
            self.embedding_model.eval()
            logger.info(f"✅ Qwen3-Embedding loaded (1024-dim, instruction-aware)")

            # Qwen3-Reranker-0.6B
            rerank_repo = get_reranking_model()
            logger.info(f"Loading Qwen3-Reranker: {rerank_repo}")
            self.rerank_tokenizer = AutoTokenizer.from_pretrained(rerank_repo)
            self.rerank_model = AutoModel.from_pretrained(
                rerank_repo, trust_remote_code=True
            ).to(self.device)
            self.rerank_model.eval()
            logger.info(f"✅ Qwen3-Reranker loaded (yes/no token scoring)")

            # Qwen3Guard-Gen-0.6B
            guard_repo = get_guardrails_model()
            logger.info(f"Loading Qwen3Guard: {guard_repo}")
            self.guard_tokenizer = AutoTokenizer.from_pretrained(guard_repo)
            # Qwen3Guard requires AutoModelForCausalLM (generation model, not embedding model)
            self.guard_model = AutoModelForCausalLM.from_pretrained(
                guard_repo, trust_remote_code=True, torch_dtype="auto"
            ).to(self.device)
            self.guard_model.eval()
            logger.info(f"✅ Qwen3Guard loaded (3-tier severity, 9 categories)")

            logger.info("🎉 All Qwen3 models loaded successfully!")

        except Exception as e:
            logger.error(f"❌ Failed to load Qwen3 models: {e}")
            raise

    def is_ready(self) -> bool:
        """Check if all models are loaded"""
        return (
            self.embedding_model is not None
            and self.rerank_model is not None
            and self.guard_model is not None
        )

    # ============= Qwen3-Embedding Methods =============

    def _mean_pooling(self, model_output, attention_mask):
        """Mean pooling with attention mask"""
        token_embeddings = model_output[0]
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

    def embed_texts(
        self,
        texts: List[str],
        normalize: bool = True,
        is_query: bool = False,
        instruction: str = "Given a medical query, retrieve relevant passages that answer the query",
    ) -> List[List[float]]:
        """
        Generate Qwen3 embeddings with instruction-awareness.

        Args:
            texts: List of texts to embed
            normalize: Apply L2 normalization (REQUIRED for Qwen3)
            is_query: If True, prepend instruction (for queries only)
            instruction: Task instruction (only used if is_query=True)

        Returns:
            List of 1024-dim embeddings

        Note: Qwen3-Embedding requires:
        - Queries: "Instruct: {instruction}\nQuery: {text}"
        - Documents: "{text}" (NO instruction)
        """
        if self.embedding_model is None or self.embedding_tokenizer is None:
            raise RuntimeError("Qwen3-Embedding model not loaded")

        # Format texts according to Qwen3 spec
        formatted_texts = []
        for text in texts:
            if is_query:
                # Query format: instruction prefix
                formatted = f"Instruct: {instruction}\nQuery: {text}"
            else:
                # Document format: no prefix
                formatted = text
            formatted_texts.append(formatted)

        # Tokenize
        encoded = self.embedding_tokenizer(
            formatted_texts,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        ).to(self.device)

        # Inference
        with torch.no_grad():
            outputs = self.embedding_model(**encoded)
            embeddings = self._mean_pooling(outputs, encoded["attention_mask"])

            # L2 normalization (MANDATORY for Qwen3)
            if normalize:
                embeddings = F.normalize(embeddings, p=2, dim=1)

        return embeddings.cpu().tolist()

    # ============= Qwen3-Reranker Methods =============

    def rerank_documents(
        self,
        query: str,
        documents: List[str],
        top_n: int = 5,
        instruction: str = "Given a medical query, determine if the passage contains the answer",
    ) -> Tuple[List[float], List[int]]:
        """
        Rerank documents using Qwen3-Reranker with yes/no token scoring.

        Args:
            query: Search query
            documents: List of documents to rerank
            top_n: Number of top results to return
            instruction: Task instruction for better relevance

        Returns:
            (scores, sorted_indices) - Scores based on yes/no token logprobs

        Note: Qwen3-Reranker uses special format:
        "<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
        """
        if self.rerank_model is None or self.rerank_tokenizer is None:
            raise RuntimeError("Qwen3-Reranker model not loaded")

        # Format pairs with Qwen3 template
        formatted_pairs = []
        for doc in documents:
            pair_text = (
                f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
            )
            formatted_pairs.append(pair_text)

        # Tokenize
        encoded = self.rerank_tokenizer(
            formatted_pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        ).to(self.device)

        # Inference with yes/no token scoring
        with torch.no_grad():
            outputs = self.rerank_model(**encoded, return_dict=True)
            logits = outputs.logits

            # Extract yes/no token probabilities
            # Qwen3-Reranker: score = P(yes) - P(no)
            yes_token_id = self.rerank_tokenizer.convert_tokens_to_ids("yes")
            no_token_id = self.rerank_tokenizer.convert_tokens_to_ids("no")

            yes_logits = logits[:, yes_token_id]
            no_logits = logits[:, no_token_id]

            # Relevance score: difference of probabilities
            scores = (yes_logits - no_logits).cpu().tolist()

        # Sort by relevance
        sorted_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_n]

        sorted_scores = [scores[i] for i in sorted_indices]

        return sorted_scores, sorted_indices

    # ============= Qwen3Guard Methods =============

    def _parse_qwen3guard_output(self, text: str) -> Dict[str, Any]:
        """
        Parse Qwen3Guard output format:
        Safety: Safe|Unsafe|Controversial
        Categories: [cat1, cat2, ...]
        Refusal: Yes|No
        """
        result = {
            "severity": "Safe",
            "categories": [],
            "is_refusal": False,
        }

        # Parse severity
        severity_match = re.search(
            r"Safety:\s*(Safe|Unsafe|Controversial)", text, re.IGNORECASE
        )
        if severity_match:
            result["severity"] = severity_match.group(1).capitalize()

        # Parse categories
        categories_match = re.search(r"Categories:\s*\[(.*?)\]", text, re.IGNORECASE)
        if categories_match:
            cats_str = categories_match.group(1)
            result["categories"] = [
                cat.strip().strip("'\"") for cat in cats_str.split(",") if cat.strip()
            ]

        # Parse refusal
        refusal_match = re.search(r"Refusal:\s*(Yes|No)", text, re.IGNORECASE)
        if refusal_match:
            result["is_refusal"] = refusal_match.group(1).lower() == "yes"

        return result

    def check_safety(
        self, text: str, check_type: str = "input"
    ) -> Tuple[bool, str, List[str], bool, str]:
        """
        Check content safety using Qwen3Guard-Gen-0.6B.

        Args:
            text: Content to check
            check_type: "input" or "output"

        Returns:
            (is_safe, severity, categories, is_refusal, raw_output)
            - is_safe: True if Safe, False if Unsafe/Controversial
            - severity: "Safe" | "Controversial" | "Unsafe"
            - categories: List of 0-9 categories from Qwen3Guard
            - is_refusal: True if model refuses to answer
            - raw_output: Raw model output for debugging

        Note: Qwen3Guard categories:
        0. Violent Acts
        1. Non-violent Illegal Acts
        2. Sexual Content
        3. PII
        4. Suicide & Self-Harm
        5. Unethical Acts
        6. Politically Sensitive
        7. Copyright
        8. Jailbreak
        """
        if self.guard_model is None or self.guard_tokenizer is None:
            raise RuntimeError("Qwen3Guard model not loaded")

        # Prepare messages using Qwen3Guard format (official specification)
        if check_type == "input":
            # Prompt moderation: user message only
            messages = [{"role": "user", "content": text}]
        else:
            # Response moderation: NOT SUPPORTED yet (needs query + response)
            # For now, treat as input moderation
            messages = [{"role": "user", "content": text}]

        # Apply chat template (Qwen3 specification)
        prompt = self.guard_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False
        )

        # Tokenize
        model_inputs = self.guard_tokenizer(
            [prompt], return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(self.device)

        # Generate safety assessment (Qwen3Guard specification)
        with torch.no_grad():
            generated_ids = self.guard_model.generate(
                **model_inputs,
                max_new_tokens=128,  # Qwen3Guard uses 128 tokens
                temperature=0.7,
                top_p=0.8,
                do_sample=True,
            )

        # Decode output (skip input prompt)
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]) :].tolist()
        output_text = self.guard_tokenizer.decode(output_ids, skip_special_tokens=True)

        # Parse Qwen3Guard output
        parsed = self._parse_qwen3guard_output(output_text)

        # Determine if safe
        is_safe = parsed["severity"] == "Safe"

        return (
            is_safe,
            parsed["severity"],
            parsed["categories"],
            parsed["is_refusal"],
            output_text,  # Return raw output for service layer parsing
        )


# Global instance
_model_registry = None


def get_model_registry() -> ModelRegistry:
    """Get singleton Qwen3 model registry"""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry
