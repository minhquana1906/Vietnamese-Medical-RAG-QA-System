import uuid

from datasets import load_dataset
from loguru import logger
from src.brain import openai_generate_embedding
from src.chunking import dynamic_chunking
from src.config import get_backend_settings
from src.vectorize import batch_upsert
from tqdm import tqdm

settings = get_backend_settings()


def load_medical_datasets():
    try:
        disease = load_dataset("PB3002/ViMedical_Disease")
        med_article = load_dataset("quannguyen204/vietnamese-medical-article-corpus")
        logger.info("Medical datasets loaded successfully")

        N = 2
        disease_small = {
            "train": disease["train"].select(range(min(N, len(disease["train"]))))
        }
        med_article_small = {
            "train": med_article["train"].select(
                range(min(N, len(med_article["train"])))
            )
        }

        return disease_small, med_article_small
    except Exception as e:
        logger.error(f"Error loading medical datasets: {e}")
        raise


def prepare_disease_points(disease_dataset):
    points = []
    logger.info("Processing medical disease dataset with dynamic chunking...")

    for idx, item in enumerate(
        tqdm(disease_dataset["train"], desc="Disease Dataset Processing")
    ):
        disease = item.get("Disease", "").strip()
        question = item.get("Question", "").strip()

        if not disease or not question:
            logger.warning(f"Skipping disease item {idx}: missing disease or question")
            continue

        combined_text = f"Câu hỏi: {question}\nCâu trả lời: {disease}"

        try:
            chunks = dynamic_chunking(
                text=combined_text,
                metadata={
                    "doc_type": "disease_info",
                    "question": question,
                    "disease": disease,
                    "source": "PB3002/ViMedical_Disease",
                    "original_index": idx,
                },
            )

            for idx, chunk in enumerate(chunks):
                embedding = openai_generate_embedding(
                    chunk.text, model=settings.openai_embedding_model
                )

                point = {
                    "id": str(uuid.uuid4()),
                    "embedding": embedding,
                    "metadata": {
                        **chunk.metadata,
                        "chunk_id": idx,
                        "total_chunks": len(chunks),
                        "content": chunk.text,
                    },
                }
                points.append(point)
        except Exception as e:
            logger.error(f"Failed processing disease item {idx}: {e}")
            continue
    logger.info(f"Prepared {len(points)} disease points")
    return points


def prepare_article_points(article_dataset):
    points = []
    logger.info("Processing medical article with dynamic chunking...")

    for idx, item in enumerate(
        tqdm(article_dataset["train"], desc="Article Processing...")
    ):
        answer = item.get("answer", item.get("answer", "")).strip()
        question = item.get("question", item.get("question", "")).strip()

        if not answer or len(answer) < 50:
            logger.warning(f"Skipping article item {idx}: insufficient answer")
            continue

        combined_text = f"Câu hỏi: {question}\nTrả lời: {answer}"

        try:
            chunks = dynamic_chunking(
                text=combined_text,
                metadata={
                    "doc_type": "medical_article",
                    "question": question,
                    "answer": answer,
                    "source": "medical_vietnamese_datasets",
                    "original_index": idx,
                },
            )

            for chunk_idx, chunk in enumerate(chunks):
                embedding = openai_generate_embedding(
                    chunk.text, model=settings.openai_embedding_model
                )

                point = {
                    "id": str(uuid.uuid4()),
                    "embedding": embedding,
                    "metadata": {
                        **chunk.metadata,
                        "chunk_id": chunk_idx,
                        "total_chunks": len(chunks),
                        "content": chunk.text,
                    },
                }
                points.append(point)

        except Exception as e:
            logger.error(f"Failed processing article {idx}: {e}")
            continue

    logger.info(f"Prepared {len(points)} article points")
    return points


def main():
    try:
        logger.info("📦 Downloading dataset...")
        # Step 2: Load datasets
        disease_dataset, article_dataset = load_medical_datasets()

        disease_points = prepare_disease_points(disease_dataset, start_id=0)

        article_start_id = len(disease_dataset["train"])
        article_points = prepare_article_points(
            article_dataset, start_id=article_start_id
        )

        all_points = disease_points + article_points
        logger.info(f"Total points to upload: {len(all_points)}")

        batch_upsert(all_points, batch_size=100)

        logger.info("=" * 60)
        logger.info("Dataset upload completed successfully!")
        logger.info(
            f"Disease dataset processed: {len(disease_dataset['train'])} → {len(disease_points)} chunks"
        )
        logger.info(
            f"Medical articles processed: {len(article_dataset['train'])} → {len(article_points)} chunks"
        )
        logger.info(f"Total points in Qdrant: {len(all_points)}")
        logger.info(f"Collection: {settings.default_collection_name}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Dataset upload failed: {e}")
        raise


if __name__ == "__main__":
    main()
