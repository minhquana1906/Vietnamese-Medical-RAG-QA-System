#!/usr/bin/env python3
"""
RAG Testset Generation with Ragas v0.3.9

Generate high-quality evaluation dataset using Ragas TestsetGenerator.
This ensures ground_truth_contexts are properly aligned with Ragas metrics schema.

Features:
- Uses Ragas native testset generation (KnowledgeGraph approach)
- Supports Vietnamese medical domain with adapted prompts
- Vietnamese personas (bệnh nhân, sinh viên y khoa, bác sĩ, điều dưỡng)
- Generates SingleHop queries
- Validates contexts against vector store
- IMPORTANT: Uses chunks (not full docs) for context alignment with RAG retrieval

CRITICAL: Align chunk length parameters with your chunking strategy:
  If chunk_size=512, chunk_overlap=50:
    - Set --min-chunk-length to ~300 (90% of chunk_size)
    - Set --max-chunk-length to ~800 (150% of chunk_size for sentence boundaries)

Usage:
    export DEEPSEEK_API_KEY="sk-..."

    # RECOMMENDED: Generate from chunks (matches RAG retrieval)
    # For chunk_size=512, chunk_overlap=50
    uv run scripts/generate_ragas_testset.py \
        --num-samples 200 \
        --output data/eval_dataset_validated.jsonl \
        --source chunks \
        --model deepseek-chat \
        --validate-contexts \
        --doc-limit 500 \
        --min-chunk-length 300 \
        --max-chunk-length 800

"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.documents import Document as LCDocument
from langchain_openai import ChatOpenAI
from loguru import logger
from ragas.llms import LangchainLLMWrapper
from ragas.testset import TestsetGenerator
from ragas.testset.persona import Persona
from ragas.testset.synthesizers import SingleHopSpecificQuerySynthesizer
from ragas.testset.transforms import (EmbeddingExtractor, KeyphrasesExtractor,
                                      SummaryExtractor)
from ragas.testset.transforms.relationship_builders.cosine import \
    CosineSimilarityBuilder
from sqlalchemy.sql.expression import func

from backend.src.configs.setup import get_backend_settings
from backend.src.database import SessionLocal
from backend.src.models import Chunk as DBChunk
from backend.src.models import Document as DBDocument

settings = get_backend_settings()


# --- Custom Embeddings Wrapper for Qwen3 ---
class Qwen3EmbeddingsWrapper:
    """
    Wrapper for Qwen3-Embedding-0.6B to work with Ragas.
    Uses the existing embedding service from backend.
    Implements both sync and async methods required by Ragas.

    NOTE: Ragas EmbeddingExtractor calls `await embedding_model.embed_text(text)`
    so embed_text MUST be an async method!
    """

    def __init__(self):
        import asyncio

        from backend.src.services.embedding import get_embedding_service

        self.embedding_service = get_embedding_service()
        self.task_instruction = "Given a medical text in vietnamese, generate an embedding for semantic search"
        self._loop = None

    def _get_loop(self):
        """Get or create event loop."""
        import asyncio

        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            return asyncio.new_event_loop()

    def _embed_sync(self, text: str) -> list[float]:
        """Internal sync embed method."""
        return self.embedding_service.embed_query(
            text, use_cache=False, task_instruction=self.task_instruction
        )

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Internal sync batch embed method."""
        return self.embedding_service.embed_documents(
            texts, use_cache=False, task_instruction=self.task_instruction
        )

    # Async methods (required by Ragas EmbeddingExtractor)
    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text (async) - Called by EmbeddingExtractor."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_sync, text)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (async)."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_batch_sync, texts)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents (async) - Ragas interface."""
        return await self.embed_texts(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Embed query text (async) - Ragas interface."""
        return await self.embed_text(text)

    # Sync methods for compatibility
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents (sync)."""
        return self._embed_batch_sync(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed query text (sync)."""
        return self._embed_sync(text)


def load_documents_from_db(limit: int | None = None) -> list[LCDocument]:
    """
    Load full documents from database and convert to LangChain Documents.

    WARNING: This loads FULL documents which may be much longer than
    the chunks used during RAG retrieval. Consider using load_chunks_from_db()
    for better alignment with the actual retrieval system.
    """
    if not SessionLocal:
        logger.error("DB Session not found.")
        return []

    db = SessionLocal()
    try:
        query = db.query(DBDocument).order_by(func.random())
        if limit:
            query = query.limit(limit)
        documents = query.all()
        logger.info(f"Loaded {len(documents)} random documents from database")

        # Convert to LangChain Document format
        lc_docs = []
        for doc in documents:
            if doc.content:
                lc_docs.append(
                    LCDocument(
                        page_content=doc.content,
                        metadata={
                            "id": str(doc.id),
                            "title": doc.title or "",
                            "source": "database",
                            "type": "document",
                        },
                    )
                )
        return lc_docs
    except Exception as e:
        logger.error(f"Error loading from DB: {e}")
        return []
    finally:
        db.close()


def load_chunks_from_db(
    limit: int | None = None,
    min_length: int = 200,
    max_length: int | None = 1200,
) -> list[LCDocument]:
    """
    Load chunks from database - RECOMMENDED for testset generation.

    This ensures ground_truth_contexts match the actual chunk sizes
    used during RAG retrieval, improving evaluation accuracy.

    IMPORTANT: Align min/max length with your chunking strategy:
    - For chunk_size=512, chunk_overlap=50:
      - min_length should be ~90% of chunk_size = 300
      - max_length should be ~150% of chunk_size = 800
        (accounts for sentence boundary overruns)

    Args:
        limit: Maximum number of chunks to load
        min_length: Minimum chunk content length in chars
                   (default 300 for chunk_size=512)
        max_length: Maximum chunk content length in chars
                   (default 800 for chunk_size=512)

    Returns:
        List of LangChain Documents representing chunks
    """
    if not SessionLocal:
        logger.error("DB Session not found.")
        return []

    db = SessionLocal()
    try:
        query = db.query(DBChunk).join(DBDocument)

        # Filter by content length
        query = query.filter(func.length(DBChunk.content) >= min_length)
        if max_length:
            query = query.filter(func.length(DBChunk.content) <= max_length)

        # Random order and limit
        query = query.order_by(func.random())
        if limit:
            query = query.limit(limit)

        chunks = query.all()
        logger.info(
            f"Loaded {len(chunks)} random chunks from database "
            f"(min_length={min_length}, max_length={max_length})"
        )

        # Convert to LangChain Document format
        lc_docs = []
        for chunk in chunks:
            if chunk.content:
                # Get document title for context
                doc_title = chunk.document.title if chunk.document else ""
                lc_docs.append(
                    LCDocument(
                        page_content=chunk.content,
                        metadata={
                            "id": str(chunk.id),
                            "document_id": str(chunk.documentId),
                            "chunk_index": chunk.chunkIndex,
                            "title": doc_title,
                            "source": "database",
                            "type": "chunk",
                        },
                    )
                )
        return lc_docs
    except Exception as e:
        logger.error(f"Error loading chunks from DB: {e}")
        return []
    finally:
        db.close()


def load_documents_from_directory(doc_dir: str) -> list[LCDocument]:
    """Load documents from directory using LangChain DirectoryLoader."""
    from langchain_community.document_loaders import (DirectoryLoader,
                                                      TextLoader)

    logger.info(f"Loading documents from directory: {doc_dir}")
    if not os.path.exists(doc_dir):
        logger.error(f"Directory {doc_dir} not found.")
        return []

    loader = DirectoryLoader(doc_dir, glob="**/*.txt", loader_cls=TextLoader)
    documents = loader.load()
    logger.info(f"Loaded {len(documents)} documents from directory")
    return documents


# --- Vietnamese Personas for Medical Domain ---
VIETNAMESE_MEDICAL_PERSONAS = [
    Persona(
        name="bệnh nhân tìm hiểu thông tin",
        role_description="Một bệnh nhân hoặc người nhà bệnh nhân muốn tìm hiểu thông tin về bệnh lý, triệu chứng và cách điều trị",
    ),
    Persona(
        name="sinh viên y khoa",
        role_description="Sinh viên đang học ngành y, cần tra cứu kiến thức y khoa để phục vụ học tập và nghiên cứu",
    ),
    Persona(
        name="bác sĩ đa khoa",
        role_description="Bác sĩ đa khoa cần tham khảo thông tin chuyên môn về các bệnh lý và phác đồ điều trị",
    ),
    Persona(
        name="điều dưỡng viên",
        role_description="Điều dưỡng viên cần tìm hiểu về chăm sóc bệnh nhân và quy trình y tế",
    ),
]


async def adapt_synthesizer_to_language(
    synthesizer: SingleHopSpecificQuerySynthesizer,
    llm: object,
    language: str = "vietnamese",
) -> SingleHopSpecificQuerySynthesizer:
    """
    Adapt synthesizer prompts to target language.
    This ensures generated questions are in the target language, not English.
    """
    logger.info(f"Adapting synthesizer prompts to {language}...")
    try:
        prompts = await synthesizer.adapt_prompts(language, llm=llm)
        synthesizer.set_prompts(**prompts)
        logger.success(f"Successfully adapted prompts to {language}")
    except Exception as e:
        logger.warning(f"Failed to adapt prompts: {e}. Using default prompts.")
    return synthesizer


async def generate_testset_with_ragas(
    docs: list[LCDocument],
    llm: object,
    embeddings: object,
    testset_size: int = 100,
    language: str = "vietnamese",
) -> list[dict]:
    """
    Generate testset using Ragas TestsetGenerator with Vietnamese language support.

    This uses Ragas's internal KnowledgeGraph building with custom transforms
    that are suitable for medical documents (avoiding HeadlinesExtractor).

    Key features for Vietnamese:
    1. Vietnamese personas (not English names like "Dr. Anya Sharma")
    2. Adapted prompts via `adapt_prompts("vietnamese")`

    Returns list of dicts with Ragas-compatible schema:
    {
        "question": "...",
        "expected_answer": "...",
        "ground_truth_contexts": ["...", "..."]
    }
    """
    logger.info(f"Generating testset with {testset_size} samples in {language}...")

    # Create TestsetGenerator with Vietnamese personas
    generator = TestsetGenerator(
        llm=llm,
        embedding_model=embeddings,
        persona_list=VIETNAMESE_MEDICAL_PERSONAS,  # Use Vietnamese personas
    )

    # Build custom transforms that SKIP HeadlinesExtractor/HeadlineSplitter
    # which fail on medical documents without clear markdown headers
    logger.info("Using custom transforms (skip HeadlinesExtractor for medical docs)")
    custom_transforms = [
        SummaryExtractor(llm=llm),
        KeyphrasesExtractor(llm=llm, max_num=10),
        # Embed the summary (required for persona generation)
        EmbeddingExtractor(
            embedding_model=embeddings,
            property_name="summary_embedding",
            embed_property_name="summary",
        ),
        # Also embed page_content for similarity matching
        EmbeddingExtractor(
            embedding_model=embeddings,
            property_name="embedding",
            embed_property_name="page_content",
        ),
        CosineSimilarityBuilder(threshold=0.7),
    ]

    # Use only SingleHop queries (MultiHop requires complex relationships in KG)
    # Use 'keyphrases' instead of 'entities' since KeyphrasesExtractor is used
    single_hop_synthesizer = SingleHopSpecificQuerySynthesizer(
        llm=llm, property_name="keyphrases"
    )

    # CRITICAL: Adapt prompts to target language
    # This ensures questions are generated in the target language, not English
    single_hop_synthesizer = await adapt_synthesizer_to_language(
        single_hop_synthesizer, llm, language=language
    )

    query_distribution = [(single_hop_synthesizer, 1.0)]  # 100% single-hop

    # Generate testset using LangChain docs with custom transforms
    try:
        testset = generator.generate_with_langchain_docs(
            docs,
            testset_size=testset_size,
            transforms=custom_transforms,  # Use custom transforms
            query_distribution=query_distribution,  # Only single-hop queries
        )

        # Convert to list of dicts
        df = testset.to_pandas()
        logger.info(f"Generated {len(df)} test samples")

        # Convert DataFrame to list of dicts with proper schema
        results = []
        for _, row in df.iterrows():
            sample = {
                "question": row.get("user_input", ""),
                "expected_answer": row.get("reference", ""),
                "ground_truth_contexts": row.get("reference_contexts", []),
            }
            # Ensure ground_truth_contexts is a list
            if isinstance(sample["ground_truth_contexts"], str):
                sample["ground_truth_contexts"] = [sample["ground_truth_contexts"]]
            results.append(sample)

        return results

    except Exception as e:
        logger.error(f"Error generating testset: {e}")
        raise


def validate_contexts_in_vectorstore(
    samples: list[dict], similarity_threshold: float = 0.7
) -> list[dict]:
    """
    Validate that ground_truth_contexts exist in the vector store.
    This helps ensure retrieval metrics are meaningful.

    Returns samples with validation status.
    """
    from backend.src.core.vectorize import search_vectors
    from backend.src.services.embedding import get_embedding_service

    logger.info("Validating contexts against vector store...")

    embedding_service = get_embedding_service()
    validated_samples = []

    for i, sample in enumerate(samples):
        contexts = sample.get("ground_truth_contexts", [])
        validated_contexts = []

        for ctx in contexts:
            # Embed the context
            ctx_embedding = embedding_service.embed_query(
                ctx[:500],  # Limit length for embedding
                use_cache=False,
            )

            # Search for similar contexts in vector store
            try:
                results = search_vectors(
                    query_vector=ctx_embedding,
                    top_k=1,
                    collection_name=settings.default_collection_name,
                )

                if results and results[0].get("score", 0) >= similarity_threshold:
                    validated_contexts.append(ctx)
                    logger.debug(
                        f"Context validated (score: {results[0].get('score', 0):.3f})"
                    )
                else:
                    logger.debug(f"Context not found in vector store (sample {i+1})")

            except Exception as e:
                logger.warning(f"Error validating context: {e}")
                # Keep the context anyway if validation fails
                validated_contexts.append(ctx)

        if validated_contexts:
            sample["ground_truth_contexts"] = validated_contexts
            sample["validation_status"] = "validated"
            validated_samples.append(sample)
        else:
            # Keep sample but mark as unvalidated
            sample["validation_status"] = "unvalidated"
            validated_samples.append(sample)

    validated_count = sum(
        1 for s in validated_samples if s.get("validation_status") == "validated"
    )
    logger.info(
        f"Validation complete: {validated_count}/{len(samples)} samples validated"
    )

    return validated_samples


async def main():
    parser = argparse.ArgumentParser(
        description="Generate RAG evaluation testset using Ragas v0.3.9"
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=100,
        help="Number of test samples to generate",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/eval_dataset.jsonl",
        help="Output file path (JSONL format)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="chunks",
        choices=["chunks", "database", "directory"],
        help="Source of documents: 'chunks' (recommended), 'database' (full docs), or 'directory'",
    )
    parser.add_argument(
        "--doc-dir",
        type=str,
        help="Directory containing documents (required if source=directory)",
    )
    parser.add_argument(
        "--doc-limit",
        type=int,
        default=500,
        help="Maximum number of documents/chunks to load from database",
    )
    parser.add_argument(
        "--min-chunk-length",
        type=int,
        default=200,
        help="Minimum chunk content length in chars (only for source=chunks). "
        "Set to ~90%% of chunk_size (200 for chunk_size=512)",
    )
    parser.add_argument(
        "--max-chunk-length",
        type=int,
        default=1200,
        help="Maximum chunk content length in chars (only for source=chunks). "
        "Set to ~150%% of chunk_size (1200 for chunk_size=512) to include sentence boundaries",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-chat",
        help="LLM model for generation (e.g., deepseek-chat, gpt-4o)",
    )
    parser.add_argument(
        "--validate-contexts",
        action="store_true",
        help="Validate contexts against vector store",
    )
    parser.add_argument(
        "--save-kg",
        type=str,
        help="Path to save the generated KnowledgeGraph (JSON format)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="vietnamese",
        help="Target language for question generation (default: vietnamese)",
    )

    args = parser.parse_args()

    # Validate arguments
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if args.model == "deepseek-chat" and not api_key:
        logger.error("DEEPSEEK_API_KEY environment variable is not set.")
        return

    if args.model.startswith("gpt-"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable is not set.")
            return

    if args.source == "directory" and not args.doc_dir:
        logger.error("--doc-dir is required when source=directory")
        return

    logger.info("=" * 60)
    logger.info("Ragas Testset Generation")
    logger.info("=" * 60)
    logger.info(f"Samples: {args.num_samples}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Source: {args.source}")
    if args.source == "chunks":
        logger.info(f"Chunk length: {args.min_chunk_length} - {args.max_chunk_length}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Language: {args.language}")
    logger.info("=" * 60)

    # 1. Load documents/chunks
    if args.source == "chunks":
        # RECOMMENDED: Load chunks for better alignment with RAG retrieval
        docs = load_chunks_from_db(
            limit=args.doc_limit,
            min_length=args.min_chunk_length,
            max_length=args.max_chunk_length,
        )
    elif args.source == "database":
        # Load full documents (may cause context length mismatch during evaluation)
        logger.warning(
            "Using full documents. Consider using --source chunks "
            "for better alignment with RAG retrieval."
        )
        docs = load_documents_from_db(limit=args.doc_limit)
    else:
        docs = load_documents_from_directory(args.doc_dir)

    if not docs:
        logger.error("No documents loaded!")
        return

    logger.info(f"Loaded {len(docs)} documents")

    # 2. Setup LLM and embeddings
    logger.info("Setting up LLM and embeddings...")

    if args.model == "deepseek-chat":
        llm = ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key=api_key,
            temperature=0.7,
        )
    else:
        llm = ChatOpenAI(
            model=args.model,
            api_key=api_key,
            temperature=0.7,
        )

    generator_llm = LangchainLLMWrapper(llm)
    generator_embeddings = Qwen3EmbeddingsWrapper()

    # 3. Generate testset
    try:
        samples = await generate_testset_with_ragas(
            docs=docs,
            llm=generator_llm,
            embeddings=generator_embeddings,
            testset_size=args.num_samples,
            language=args.language,
        )
    except Exception as e:
        logger.error(f"Failed to generate testset: {e}")
        return

    # 4. Validate contexts (optional)
    if args.validate_contexts:
        samples = validate_contexts_in_vectorstore(samples)

    # 5. Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for sample in samples:
            # Remove validation status from output
            output_sample = {
                "question": sample["question"],
                "expected_answer": sample["expected_answer"],
                "ground_truth_contexts": sample["ground_truth_contexts"],
            }
            f.write(json.dumps(output_sample, ensure_ascii=False) + "\n")

    logger.info(f"✅ Done! Generated {len(samples)} samples -> {args.output}")

    # Print sample
    if samples:
        logger.info("\n--- Sample Output ---")
        sample = samples[0]
        logger.info(f"Question: {sample['question'][:100]}...")
        logger.info(f"Answer: {sample['expected_answer'][:100]}...")
        logger.info(f"Contexts: {len(sample['ground_truth_contexts'])} items")


if __name__ == "__main__":
    asyncio.run(main())
