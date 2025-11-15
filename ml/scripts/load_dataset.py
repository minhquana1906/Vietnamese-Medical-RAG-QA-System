#!/usr/bin/env python3
"""
Load Vietnamese Medical Datasets from HuggingFace Hub

Downloads and prepares:
1. quannguyen204/combined_medical_dataset - Medical QA dataset for generation fine-tuning
2. mtue29/vietnamese-medical-dataset - Medical documents for embedding fine-tuning

Usage:
    python -m ml.scripts.load_dataset --dataset quannguyen204/combined_medical_dataset --output-dir ./data
    python -m ml.scripts.load_dataset --dataset mtue29/vietnamese-medical-dataset --output-dir ./data
    python -m ml.scripts.load_dataset --all --output-dir ./data
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

from datasets import load_dataset
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)


def load_medical_qa_dataset(output_dir: Path, cache_dir: Optional[Path] = None) -> None:
    """
    Load quannguyen204/combined_medical_dataset from HuggingFace Hub.

    This dataset contains Vietnamese medical question-answer pairs
    for fine-tuning the generation model (Qwen3-4B-Instruct-2507).

    Args:
        output_dir: Directory to save the dataset
        cache_dir: Optional cache directory for HuggingFace datasets
    """
    logger.info(
        "Loading quannguyen204/combined_medical_dataset from HuggingFace Hub..."
    )

    try:
        # Load dataset from HuggingFace
        # Note: Update with actual HuggingFace dataset path when available
        dataset = load_dataset(
            "quannguyen204/combined_medical_dataset",  # Placeholder - update with actual path
            cache_dir=str(cache_dir) if cache_dir else None,
        )

        # Save to disk
        dataset_path = output_dir / "combined_medical_qa"
        dataset_path.mkdir(parents=True, exist_ok=True)

        dataset.save_to_disk(str(dataset_path))

        logger.info(f"✓ Successfully loaded quannguyen204/combined_medical_dataset")
        logger.info(f"  Saved to: {dataset_path}")
        logger.info(f"  Train samples: {len(dataset.get('train', []))}")
        logger.info(f"  Test samples: {len(dataset.get('test', []))}")

    except Exception as e:
        logger.error(f"✗ Failed to load quannguyen204/combined_medical_dataset: {e}")
        logger.info(
            "Note: If dataset is not available on HuggingFace Hub, you may need to:"
        )
        logger.info("  1. Upload your dataset to HuggingFace Hub")
        logger.info("  2. Update the dataset path in this script")
        logger.info("  3. Set HF_TOKEN environment variable if dataset is private")
        raise


def load_vietnamese_medical_dataset(
    output_dir: Path, cache_dir: Optional[Path] = None
) -> None:
    """
    Load mtue29/vietnamese-medical-dataset from HuggingFace Hub.

    This dataset contains Vietnamese medical documents/articles
    for fine-tuning the embedding model (Qwen3-Embedding-0.6B).

    Args:
        output_dir: Directory to save the dataset
        cache_dir: Optional cache directory for HuggingFace datasets
    """
    logger.info("Loading mtue29/vietnamese-medical-dataset from HuggingFace Hub...")

    try:
        # Load dataset from HuggingFace
        # Note: Update with actual HuggingFace dataset path when available
        dataset = load_dataset(
            "mtue29/vietnamese-medical-dataset",  # Placeholder - update with actual path
            cache_dir=str(cache_dir) if cache_dir else None,
        )

        # Save to disk
        dataset_path = output_dir / "vietnamese_medical"
        dataset_path.mkdir(parents=True, exist_ok=True)

        dataset.save_to_disk(str(dataset_path))

        logger.info(f"✓ Successfully loaded mtue29/vietnamese-medical-dataset")
        logger.info(f"  Saved to: {dataset_path}")
        logger.info(f"  Total documents: {len(dataset.get('train', []))}")

    except Exception as e:
        logger.error(f"✗ Failed to load mtue29/vietnamese-medical-dataset: {e}")
        logger.info(
            "Note: If dataset is not available on HuggingFace Hub, you may need to:"
        )
        logger.info("  1. Upload your dataset to HuggingFace Hub")
        logger.info("  2. Update the dataset path in this script")
        logger.info("  3. Set HF_TOKEN environment variable if dataset is private")
        raise


def main():
    """Main entry point for dataset loading."""
    parser = argparse.ArgumentParser(
        description="Load Vietnamese medical datasets from HuggingFace Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Load medical QA dataset
    python -m ml.scripts.load_dataset --dataset quannguyen204/combined_medical_dataset

    # Load medical documents dataset
    python -m ml.scripts.load_dataset --dataset mtue29/vietnamese-medical-dataset

    # Load all datasets
    python -m ml.scripts.load_dataset --all

    # Specify custom output directory
    python -m ml.scripts.load_dataset --all --output-dir /path/to/data
        """,
    )

    parser.add_argument(
        "--dataset", type=str, choices=["qa", "embedding"], help="Which dataset to load"
    )

    parser.add_argument("--all", action="store_true", help="Load all datasets")

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data",
        help="Directory to save datasets (default: ./data)",
    )

    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Cache directory for HuggingFace datasets (default: ~/.cache/huggingface)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.dataset:
        parser.error("Either --dataset or --all must be specified")

    # Setup paths
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None

    logger.info("=" * 70)
    logger.info("Vietnamese Medical Dataset Loader")
    logger.info("=" * 70)
    logger.info(f"Output directory: {output_dir}")
    if cache_dir:
        logger.info(f"Cache directory: {cache_dir}")
    logger.info("")

    # Load datasets
    try:
        if args.all or args.dataset == "qa":
            load_medical_qa_dataset(output_dir, cache_dir)
            logger.info("")

        if args.all or args.dataset == "embedding":
            load_vietnamese_medical_dataset(output_dir, cache_dir)
            logger.info("")

        logger.info("=" * 70)
        logger.info("✓ All datasets loaded successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"✗ Dataset loading failed: {e}")
        logger.error("=" * 70)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
