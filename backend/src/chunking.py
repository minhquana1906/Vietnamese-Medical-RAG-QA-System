import json

from llama_index.core.node_parser import (SentenceSplitter,
                                          SentenceWindowNodeParser)
from llama_index.core.schema import Document, TextNode
from loguru import logger

from .brain import openai_chat_complete
from .config import CHUNK_OVERLAP, CHUNK_SIZE


def chunk_by_window_sentences(text, metadata=None, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    logger.info("Chunking document by window sentences...")
    try:
        if metadata is not None:
            document = Document(text=text, metadata=metadata)
        else:
            document = Document(text=text)

        splitter = SentenceSplitter.from_defaults(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=". ",
            include_prev_next_rel=True,
            include_metadata=True,
        )
        parser = SentenceWindowNodeParser(
            splitter=splitter,
            window_size=3,
            window_metadata_key="window",
            original_text_metadata_key="original_text",
            include_prev_next_rel=True,
            include_metadata=True,
        )
        nodes = parser.get_nodes_from_documents([document])
        logger.info(f"Document chunked into {len(nodes)} chunks.")
        return nodes
    except Exception as e:
        logger.error(f"Error chunking document: {e}")
        raise


def chunk_by_llm(text, metadata=None):
    logger.info("Chunking document using LLM...")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an assistant that splits text into smaller chunks. "
                    "Each chunk should be no longer than 512 characters, with an overlap of 50 characters. "
                    "Return the result as a JSON array of strings, where each string is a chunk of the text. "
                    "Do not include any markdown formatting (e.g., ```json). Only return the JSON array."
                ),
            },
            {
                "role": "user",
                "content": f"## Input text ##: {text}\n\n"
                f'## Output format ##: ["chunk1", "chunk2", ...]\n\n'
                f"## Output ##: ",
            },
        ]

        llm_response = openai_chat_complete(messages, temperature=0.1, max_tokens=2048)
        logger.info(f"LLM response for chunking: {llm_response}")

        try:
            chunks = json.loads(llm_response)
            if not isinstance(chunks, list):
                raise ValueError("LLM response is not a valid JSON list.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode LLM response as JSON: {e}")

        nodes = [TextNode(text=node, metadata=metadata) if metadata else TextNode(text=node) for node in chunks]
        logger.info(f"Document chunked into {len(nodes)} chunks by LLM.")
        return nodes
    except Exception as e:
        logger.error(f"Error chunking document with LLM: {e}")
        raise


def dynamic_chunking(text, metadata=None):
    if len(text) < CHUNK_SIZE:
        logger.info("Document is smaller than chunk size, creating single chunk.")
        return [TextNode(text=text, metadata=metadata)] if metadata else [TextNode(text=text)]
    elif len(text) < CHUNK_SIZE * 4:
        return chunk_by_window_sentences(text, metadata)
    else:
        return chunk_by_llm(text, metadata)
