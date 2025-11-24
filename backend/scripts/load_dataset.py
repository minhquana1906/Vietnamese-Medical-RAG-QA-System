import argparse
import logging
from pathlib import Path
from typing import Optional

from datasets import load_dataset
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)


def load_vietnamese_medical_corpus(
    output_dir: Path, cache_dir: Optional[Path] = None
) -> None:

    logger.info(
        "Loading quannguyen204/vietnamese_medical_corpus_dataset from HuggingFace Hub..."
    )

    try:
        # Load dataset from HuggingFace Hub
        dataset = load_dataset(
            "quannguyen204/vietnamese_medical_corpus_dataset",
            cache_dir=str(cache_dir) if cache_dir else None,
        )

        # Save to disk
        dataset_path = output_dir / "vietnamese_medical_corpus"
        dataset_path.mkdir(parents=True, exist_ok=True)

        dataset.save_to_disk(str(dataset_path))

        logger.info(
            f"✓ Successfully loaded quannguyen204/vietnamese_medical_corpus_dataset"
        )
        logger.info(f"  Saved to: {dataset_path}")
        logger.info(
            f"  Dataset URL: https://huggingface.co/datasets/quannguyen204/vietnamese_medical_corpus_dataset"
        )

        # Log split information
        for split_name, split_data in dataset.items():
            logger.info(f"  {split_name.capitalize()} samples: {len(split_data)}")

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
    # Load Vietnamese medical corpus dataset (default)
    python -m backend.scripts.load_dataset

    # Specify custom output directory
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
    logger.info(f"Output directory: {output_dir}")
    if cache_dir:
        logger.info(f"Cache directory: {cache_dir}")
    logger.info("")

    # Load dataset
    try:
        load_vietnamese_medical_corpus(output_dir, cache_dir)

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
