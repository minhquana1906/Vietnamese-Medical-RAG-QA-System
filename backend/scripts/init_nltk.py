import os
from pathlib import Path

import nltk
from loguru import logger


def download_nltk_data():
    nltk_data_dir = os.getenv("NLTK_DATA", "/app/nltk_data")
    punkt_path = Path(nltk_data_dir) / "tokenizers" / "punkt_tab"

    if not punkt_path.exists():
        logger.info("Downloading NLTK punkt_tab...")
        nltk.download("punkt_tab", download_dir=nltk_data_dir, quiet=True)
        logger.info("NLTK punkt_tab downloaded successfully")
    else:
        logger.info("NLTK punkt_tab already exists")


if __name__ == "__main__":
    download_nltk_data()
