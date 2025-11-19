#!/usr/bin/env python3
"""
Load Vietnamese Medical Dataset from HuggingFace Hub

Downloads and prepares:
- quannguyen204/vietnamese_medical_corpus_dataset - Comprehensive Vietnamese medical corpus for RAG indexing

Dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset

Usage:
    python -m backend.scripts.load_dataset --output-dir ./data
    python -m backend.scripts.load_dataset --output-dir ./data --cache-dir /custom/cache
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

from datasets import load_dataset
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)


def load_vietnamese_medical_corpus(
    output_dir: Path, 
    cache_dir: Optional[Path] = None,
    streaming: bool = False
) -> None:
    """
    Load quannguyen204/vietnamese_medical_corpus_dataset from HuggingFace Hub.

    This dataset contains comprehensive Vietnamese medical documents for RAG indexing,
    including medical articles, clinical guidelines, drug information, and health resources.

    Dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset

    Args:
        output_dir: Directory to save the dataset (ignored if streaming=True)
        cache_dir: Optional cache directory for HuggingFace datasets
        streaming: If True, use streaming mode (no local download, process on-the-fly)
                  Recommended for large datasets or one-time indexing
    
    Returns:
        Dataset object (either full dataset or IterableDataset if streaming)
    """
    mode = "STREAMING" if streaming else "DOWNLOAD"
    logger.info(
        f"Loading quannguyen204/vietnamese_medical_corpus_dataset from HuggingFace Hub ({mode} mode)..."
    )

    try:
        # Load dataset from HuggingFace Hub
        dataset = load_dataset(
            "quannguyen204/vietnamese_medical_corpus_dataset",
            cache_dir=str(cache_dir) if cache_dir else None,
            streaming=streaming,
        )

        if streaming:
            # Streaming mode: no download, process on-the-fly
            logger.info(
                f"✓ Successfully initialized streaming dataset (quannguyen204/vietnamese_medical_corpus_dataset)"
            )
            logger.info(
                f"  Dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset"
            )
            logger.info(f"  Mode: STREAMING (no local download, on-the-fly processing)")
            logger.info(f"  Memory: Efficient (loads batches incrementally)")
            
            # Log available splits
            logger.info(f"  Available splits: {list(dataset.keys())}")
            
        else:
            # Download mode: save to disk for reuse
            dataset_path = output_dir / "vietnamese_medical_corpus"
            dataset_path.mkdir(parents=True, exist_ok=True)

            dataset.save_to_disk(str(dataset_path))

            logger.info(
                f"✓ Successfully downloaded quannguyen204/vietnamese_medical_corpus_dataset"
            )
            logger.info(f"  Saved to: {dataset_path}")
            logger.info(
                f"  Dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset"
            )

            # Log split information
            for split_name, split_data in dataset.items():
                logger.info(f"  {split_name.capitalize()} samples: {len(split_data)}")
        
        return dataset

    except Exception as e:
        logger.error(
            f"✗ Failed to load quannguyen204/vietnamese_medical_corpus_dataset: {e}"
        )
        logger.info(
            "Note: If dataset is not available on HuggingFace Hub, you may need to:"
        )
        logger.info(
            "  1. Check dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset"
        )
        logger.info("  2. Set HF_TOKEN environment variable if dataset is private")
        logger.info(
            "  3. Verify your HuggingFace authentication: huggingface-cli login"
        )
        raise


def main():
    """Main entry point for dataset loading."""
    parser = argparse.ArgumentParser(
        description="Load Vietnamese Medical Corpus Dataset from HuggingFace Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Download mode (default): Save to disk for reuse
    python -m backend.scripts.load_dataset

    # Streaming mode: No download, process on-the-fly (recommended for large datasets)
    python -m backend.scripts.load_dataset --streaming

    # Specify custom output directory (download mode only)
    python -m backend.scripts.load_dataset --output-dir /path/to/data

    # Specify custom cache directory
    python -m backend.scripts.load_dataset --cache-dir /path/to/cache

Dataset Information:
    - Name: quannguyen204/vietnamese_medical_corpus_dataset
    - URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset
    - Content: Comprehensive Vietnamese medical documents for RAG indexing
        """,
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data",
        help="Directory to save dataset (default: ./data)",
    )

    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Cache directory for HuggingFace datasets (default: ~/.cache/huggingface)",
    )

    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Use streaming mode (no local download, process on-the-fly). "
             "Recommended for large datasets or one-time indexing.",
    )

    args = parser.parse_args()

    # Setup paths
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None

    logger.info("=" * 80)
    logger.info("Vietnamese Medical Corpus Dataset Loader")
    logger.info("=" * 80)
    logger.info(f"Dataset: quannguyen204/vietnamese_medical_corpus_dataset")
    logger.info(
        f"URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset"
    )
    logger.info(f"Mode: {'STREAMING' if args.streaming else 'DOWNLOAD'}")
    if not args.streaming:
        logger.info(f"Output directory: {output_dir}")
    if cache_dir:
        logger.info(f"Cache directory: {cache_dir}")
    logger.info("")

    # Load dataset
    try:
        dataset = load_vietnamese_medical_corpus(
            output_dir, cache_dir, streaming=args.streaming
        )

        logger.info("")
        logger.info("=" * 80)
        logger.info("✓ Dataset loaded successfully!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Index dataset via API: POST /indexing/ingest-dataset")
        logger.info(
            "  2. Or run indexing script: python -m backend.scripts.index_dataset"
        )

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"✗ Dataset loading failed: {e}")
        logger.error("=" * 80)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
