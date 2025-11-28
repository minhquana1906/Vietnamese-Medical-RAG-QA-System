from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from loguru import logger

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


def fixed_semantic_chunking(
    text: str,
    metadata: dict = None,
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
):
    logger.info(
        f"Chunking document with fixed semantic strategy (size={chunk_size}, overlap={chunk_overlap})..."
    )

    try:
        # Create document with metadata
        if metadata is not None:
            document = Document(text=text, metadata=metadata)
        else:
            document = Document(text=text)

        # Use SentenceSplitter with sentence boundary awareness
        splitter = SentenceSplitter.from_defaults(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=". ",  # Sentence separator for Vietnamese
            include_prev_next_rel=True,  # Include chunk relationships
            include_metadata=True,
        )

        nodes = splitter.get_nodes_from_documents([document])

        logger.info(
            f"Document chunked into {len(nodes)} chunks "
            f"(avg size: {sum(len(n.text) for n in nodes) // len(nodes) if nodes else 0} chars)"
        )
        return nodes

    except Exception as e:
        logger.error(f"Error in fixed semantic chunking: {e}")
        raise
