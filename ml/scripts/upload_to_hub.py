#!/usr/bin/env python3
"""
Upload Fine-tuned Models to HuggingFace Hub

Uploads models with comprehensive model cards including:
- Model description and architecture
- Training details and hyperparameters
- Evaluation metrics and performance
- Usage examples
- Limitations and biases

Usage:
    python -m ml.scripts.upload_to_hub --model-path ./ml/models/qwen3-4b-medical-lora/final --model-id minhquana1906/qwen3-4b-medical-vietnamese
    python -m ml.scripts.upload_to_hub --model-path ./ml/models/qwen3-embedding-medical/final --model-id minhquana1906/qwen3-embedding-medical-vietnamese --model-type embedding
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from huggingface_hub import HfApi, create_repo
from loguru import logger


def create_model_card(
    model_id: str,
    model_type: str,
    base_model: str,
    dataset: str,
    metrics: dict,
    training_config: dict,
) -> str:
    """
    Create a comprehensive model card in Markdown format.

    Args:
        model_id: HuggingFace model ID
        model_type: Type of model (generation or embedding)
        base_model: Base model name
        dataset: Training dataset name
        metrics: Evaluation metrics
        training_config: Training configuration

    Returns:
        Model card content as Markdown string
    """

    if model_type == "generation":
        card = f"""---
language:
- vi
license: apache-2.0
tags:
- medical
- vietnamese
- question-answering
- rag
- lora
- peft
base_model: {base_model}
datasets:
- combined_medical_qa_dataset
metrics:
- bleu
- rouge
- bertscore
---

# {model_id}

## Model Description

This model is a fine-tuned version of [{base_model}](https://huggingface.co/{base_model}) specifically optimized for Vietnamese medical question answering. It has been fine-tuned using LoRA (Low-Rank Adaptation) on the {dataset} dataset containing Vietnamese medical QA pairs.

## Intended Use

**Primary Use**: Medical question answering in Vietnamese language for RAG (Retrieval-Augmented Generation) systems.

**Out-of-scope Use**: 
- Should NOT be used as a sole source for medical diagnosis or treatment decisions
- Not suitable for non-Vietnamese languages
- Not intended for general-purpose question answering

## Training Data

- **Dataset**: {dataset}
- **Language**: Vietnamese
- **Domain**: Medical (diseases, symptoms, treatments, medications)
- **Size**: See dataset card for details

## Training Procedure

### LoRA Configuration

```yaml
r: {training_config.get('lora_r', 16)}
lora_alpha: {training_config.get('lora_alpha', 32)}
target_modules: {training_config.get('target_modules', ['q_proj', 'k_proj', 'v_proj', 'o_proj'])}
lora_dropout: {training_config.get('lora_dropout', 0.05)}
```

### Training Hyperparameters

```yaml
learning_rate: {training_config.get('learning_rate', 2e-4)}
num_epochs: {training_config.get('num_epochs', 3)}
batch_size: {training_config.get('batch_size', 4)}
gradient_accumulation_steps: {training_config.get('gradient_accumulation_steps', 4)}
warmup_steps: {training_config.get('warmup_steps', 100)}
optimizer: {training_config.get('optimizer', 'paged_adamw_8bit')}
```

## Performance

### Evaluation Metrics

| Metric | Baseline | Fine-tuned | Improvement |
|--------|----------|------------|-------------|
| BLEU | {metrics.get('baseline_bleu', 0):.4f} | {metrics.get('finetuned_bleu', 0):.4f} | {metrics.get('bleu_improvement', 0):.2f}% |
| ROUGE-L F1 | {metrics.get('baseline_rouge_f1', 0):.4f} | {metrics.get('finetuned_rouge_f1', 0):.4f} | {metrics.get('rouge_improvement', 0):.2f}% |
| BERTScore F1 | {metrics.get('baseline_bert_f1', 0):.4f} | {metrics.get('finetuned_bert_f1', 0):.4f} | {metrics.get('bert_improvement', 0):.2f}% |

## Usage

### Loading the Model

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model
base_model = AutoModelForCausalLM.from_pretrained(
    "{base_model}",
    dtype="auto",
    device_map="auto",
    trust_remote_code=True
)

# Load LoRA adapter
model = PeftModel.from_pretrained(base_model, "{model_id}")

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained("{model_id}")
```

### Inference

```python
def generate_answer(question: str, context: str = None) -> str:
    if context:
        prompt = f\"\"\"Bạn là trợ lý y tế AI. Dựa vào ngữ cảnh sau, hãy trả lời câu hỏi.

Ngữ cảnh: {{context}}

Câu hỏi: {{question}}

Trả lời:\"\"\"
    else:
        prompt = f\"\"\"Bạn là trợ lý y tế AI. Hãy trả lời câu hỏi sau.

Câu hỏi: {{question}}

Trả lời:\"\"\"
    
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.7, top_p=0.9)
    answer = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return answer.strip()

# Example
question = "Triệu chứng của bệnh tiểu đường là gì?"
answer = generate_answer(question)
print(answer)
```

## Limitations

- **Medical Accuracy**: While fine-tuned on medical data, this model should NOT replace professional medical advice
- **Language**: Only supports Vietnamese language
- **Context Length**: Limited to {training_config.get('max_length', 512)} tokens
- **Hallucinations**: May generate plausible but incorrect information
- **Bias**: May reflect biases present in training data

## Ethical Considerations

- **Medical Disclaimer**: This model is for informational purposes only and should not be used for medical diagnosis or treatment decisions
- **Professional Consultation**: Users should always consult qualified healthcare professionals for medical advice
- **Data Privacy**: Do not input personal health information when using this model
- **Bias Awareness**: The model may have biases from training data; use with caution in diverse populations

## Citation

If you use this model in your research, please cite:

```bibtex
@misc{{vietnamese-medical-rag-2025,
  title={{Vietnamese Medical RAG QA System with Fine-tuned Qwen3 Models}},
  author={{Quan Nguyen}},
  year={{2025}},
  publisher={{HuggingFace}},
  url={{https://huggingface.co/{model_id}}}
}}
```

## Contact

For questions or issues, please open an issue on the [GitHub repository](https://github.com/minhquana1906/Vietnamese-Medical-RAG-QA-System).
"""

    else:  # embedding model
        card = f"""---
language:
- vi
license: apache-2.0
tags:
- medical
- vietnamese
- sentence-transformers
- embedding
- retrieval
- lora
- peft
base_model: {base_model}
datasets:
- vietnamese-medical-dataset
metrics:
- precision@k
- recall@k
- mrr
- ndcg
---

# {model_id}

## Model Description

This model is a fine-tuned version of [{base_model}](https://huggingface.co/{base_model}) specifically optimized for Vietnamese medical document retrieval. It has been fine-tuned using LoRA with contrastive learning on the {dataset} dataset.

## Intended Use

**Primary Use**: Semantic search and document retrieval for Vietnamese medical documents in RAG systems.

**Out-of-scope Use**: 
- Not suitable for non-Vietnamese languages
- Not intended for general-purpose embeddings
- Not optimized for short queries outside medical domain

## Training Data

- **Dataset**: {dataset}
- **Language**: Vietnamese
- **Domain**: Medical documents
- **Training Method**: Contrastive learning with hard negatives

## Training Procedure

### LoRA Configuration

```yaml
r: {training_config.get('lora_r', 32)}
lora_alpha: {training_config.get('lora_alpha', 64)}
target_modules: {training_config.get('target_modules', ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'])}
lora_dropout: {training_config.get('lora_dropout', 0.1)}
```

### Training Hyperparameters

```yaml
learning_rate: {training_config.get('learning_rate', 1e-4)}
num_epochs: {training_config.get('num_epochs', 5)}
batch_size: {training_config.get('batch_size', 16)}
loss_function: {training_config.get('loss_function', 'multiple_negatives_ranking')}
temperature: {training_config.get('temperature', 0.05)}
```

## Performance

### Retrieval Metrics

| Metric | Baseline | Fine-tuned | Improvement |
|--------|----------|------------|-------------|
| MRR@10 | {metrics.get('baseline_mrr', 0):.4f} | {metrics.get('finetuned_mrr', 0):.4f} | {metrics.get('mrr_improvement', 0):.2f}% |
| Precision@10 | {metrics.get('baseline_p10', 0):.4f} | {metrics.get('finetuned_p10', 0):.4f} | {metrics.get('p10_improvement', 0):.2f}% |
| Recall@10 | {metrics.get('baseline_r10', 0):.4f} | {metrics.get('finetuned_r10', 0):.4f} | {metrics.get('r10_improvement', 0):.2f}% |

## Usage

### Loading the Model

```python
from transformers import AutoModel, AutoTokenizer
from peft import PeftModel
import torch

# Load base model
base_model = AutoModel.from_pretrained(
    "{base_model}",
    trust_remote_code=True
)

# Load LoRA adapter
model = PeftModel.from_pretrained(base_model, "{model_id}")

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained("{model_id}")

# Set to evaluation mode
model.eval()
```

### Generate Embeddings

```python
def embed_text(text: str) -> torch.Tensor:
    # Tokenize
    inputs = tokenizer(text, padding=True, truncation=True, max_length=256, return_tensors="pt")
    
    # Generate embeddings
    with torch.no_grad():
        outputs = model(**inputs)
        embeddings = outputs.last_hidden_state.mean(dim=1)  # Mean pooling
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)  # L2 normalize
    
    return embeddings

# Example
query = "Triệu chứng của bệnh tiểu đường"
query_embedding = embed_text(query)
print(f"Embedding shape: {{query_embedding.shape}}")
```

### Semantic Search

```python
def semantic_search(query: str, documents: list[str], top_k: int = 5):
    # Embed query
    query_emb = embed_text(query)
    
    # Embed documents
    doc_embs = torch.cat([embed_text(doc) for doc in documents])
    
    # Calculate cosine similarity
    scores = torch.mm(query_emb, doc_embs.T).squeeze(0)
    
    # Get top-k results
    top_indices = scores.argsort(descending=True)[:top_k]
    
    return [(documents[i], scores[i].item()) for i in top_indices]

# Example
documents = [
    "Bệnh tiểu đường type 2 là...",
    "Triệu chứng của bệnh tim...",
    # ... more documents
]

results = semantic_search("triệu chứng tiểu đường", documents)
for doc, score in results:
    print(f"Score: {{score:.4f}} - {{doc[:100]}}...")
```

## Limitations

- **Domain-Specific**: Optimized for Vietnamese medical text only
- **Context Length**: Limited to {training_config.get('max_length', 256)} tokens
- **Normalization**: Embeddings should be L2-normalized for cosine similarity
- **Inference Speed**: LoRA adds slight overhead compared to base model

## Citation

```bibtex
@misc{{vietnamese-medical-embedding-2025,
  title={{Vietnamese Medical Embedding Model with Fine-tuned Qwen3}},
  author={{Quan Minh}},
  year={{2025}},
  publisher={{HuggingFace}},
  url={{https://huggingface.co/{model_id}}}
}}
```

## Contact

For questions or issues, please open an issue on the [GitHub repository](https://github.com/minhquana1906/Vietnamese-Medical-RAG-QA-System).
"""

    return card


def upload_model(
    model_path: Path,
    model_id: str,
    model_type: str = "generation",
    metrics_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    private: bool = False,
) -> None:
    """
    Upload model to HuggingFace Hub with model card.

    Args:
        model_path: Path to the fine-tuned model directory
        model_id: HuggingFace model ID (e.g., "username/model-name")
        model_type: Type of model ("generation" or "embedding")
        metrics_path: Optional path to metrics JSON file
        config_path: Optional path to training config YAML file
        private: Whether to make the model private
    """
    logger.info(f"Uploading model to HuggingFace Hub: {model_id}")

    # Validate model path
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    # Load metrics if provided
    metrics = {}
    if metrics_path and metrics_path.exists():
        with open(metrics_path, "r") as f:
            metrics = json.load(f)
        logger.info(f"Loaded metrics from {metrics_path}")

    # Load training config if provided
    training_config = {}
    if config_path and config_path.exists():
        import yaml

        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
            training_config = {
                "lora_r": config_data.get("lora", {}).get("r", 16),
                "lora_alpha": config_data.get("lora", {}).get("lora_alpha", 32),
                "target_modules": config_data.get("lora", {}).get("target_modules", []),
                "lora_dropout": config_data.get("lora", {}).get("lora_dropout", 0.05),
                "learning_rate": config_data.get("training", {}).get(
                    "learning_rate", 2e-4
                ),
                "num_epochs": config_data.get("training", {}).get("num_epochs", 3),
                "batch_size": config_data.get("training", {}).get(
                    "per_device_train_batch_size", 4
                ),
                "gradient_accumulation_steps": config_data.get("training", {}).get(
                    "gradient_accumulation_steps", 4
                ),
                "warmup_steps": config_data.get("training", {}).get(
                    "warmup_steps", 100
                ),
                "optimizer": config_data.get("training", {}).get(
                    "optimizer", "adamw_torch"
                ),
                "max_length": config_data.get("data", {}).get("max_length", 512),
                "loss_function": config_data.get("contrastive", {}).get(
                    "loss_function", "multiple_negatives_ranking"
                ),
                "temperature": config_data.get("contrastive", {}).get(
                    "temperature", 0.05
                ),
            }
        logger.info(f"Loaded training config from {config_path}")

    # Determine base model
    if model_type == "generation":
        base_model = "Qwen/Qwen3-4B-Instruct-2507"
        dataset = "combined_medical_qa_dataset"
    else:
        base_model = "Qwen/Qwen3-Embedding-0.6B"
        dataset = "vietnamese-medical-dataset"

    # Create model card
    logger.info("Creating model card...")
    model_card = create_model_card(
        model_id=model_id,
        model_type=model_type,
        base_model=base_model,
        dataset=dataset,
        metrics=metrics,
        training_config=training_config,
    )

    # Save model card
    readme_path = model_path / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(model_card)
    logger.info(f"Model card saved to {readme_path}")

    # Create repository
    api = HfApi()
    try:
        create_repo(model_id, private=private, exist_ok=True)
        logger.info(f"Created/verified repository: {model_id}")
    except Exception as e:
        logger.warning(f"Repository may already exist: {e}")

    # Upload model
    logger.info("Uploading model files...")
    api.upload_folder(folder_path=str(model_path), repo_id=model_id, repo_type="model")

    logger.info(f"✓ Model uploaded successfully to: https://huggingface.co/{model_id}")


def main():
    """Main entry point for model upload."""
    parser = argparse.ArgumentParser(
        description="Upload fine-tuned models to HuggingFace Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Upload generation model
    python -m ml.scripts.upload_to_hub \\
        --model-path ./ml/models/qwen3-4b-medical-lora/final \\
        --model-id minhquana1906/qwen3-4b-medical-vietnamese \\
        --model-type generation \\
        --metrics-path ./ml/results/generation_metrics.json \\
        --config-path ./ml/configs/generation_lora_config.yaml

    # Upload embedding model
    python -m ml.scripts.upload_to_hub \\
        --model-path ./ml/models/qwen3-embedding-medical/final \\
        --model-id minhquana1906/qwen3-embedding-medical-vietnamese \\
        --model-type embedding \\
        --private
        """,
    )

    parser.add_argument(
        "--model-path",
        type=str,
        required=True,
        help="Path to the fine-tuned model directory",
    )

    parser.add_argument(
        "--model-id",
        type=str,
        required=True,
        help="HuggingFace model ID (e.g., username/model-name)",
    )

    parser.add_argument(
        "--model-type",
        type=str,
        choices=["generation", "embedding"],
        default="generation",
        help="Type of model to upload",
    )

    parser.add_argument(
        "--metrics-path",
        type=str,
        default=None,
        help="Path to metrics JSON file (optional)",
    )

    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Path to training config YAML file (optional)",
    )

    parser.add_argument(
        "--private",
        action="store_true",
        help="Make the model private (default: public)",
    )

    args = parser.parse_args()

    # Convert paths
    model_path = Path(args.model_path).resolve()
    metrics_path = Path(args.metrics_path).resolve() if args.metrics_path else None
    config_path = Path(args.config_path).resolve() if args.config_path else None

    logger.info("=" * 70)
    logger.info("HuggingFace Model Upload")
    logger.info("=" * 70)
    logger.info(f"Model path: {model_path}")
    logger.info(f"Model ID: {args.model_id}")
    logger.info(f"Model type: {args.model_type}")
    logger.info(f"Private: {args.private}")
    logger.info("")

    try:
        upload_model(
            model_path=model_path,
            model_id=args.model_id,
            model_type=args.model_type,
            metrics_path=metrics_path,
            config_path=config_path,
            private=args.private,
        )

        logger.info("=" * 70)
        logger.info("✓ Upload complete!")
        logger.info("=" * 70)
        logger.info(f"View your model at: https://huggingface.co/{args.model_id}")

    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"✗ Upload failed: {e}")
        logger.error("=" * 70)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
