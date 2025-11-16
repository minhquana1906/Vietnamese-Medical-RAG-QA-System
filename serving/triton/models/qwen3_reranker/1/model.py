import json
import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    """Triton Python Backend for Qwen3-Reranker-0.6B"""

    def initialize(self, args):
        """
        Initialize the reranker model.

        Args:
            args: Dictionary containing model configuration
        """
        self.model_config = json.loads(args["model_config"])

        # Get output configuration
        output_config = pb_utils.get_output_config_by_name(self.model_config, "SCORES")
        self.output_dtype = pb_utils.triton_string_to_numpy(output_config["data_type"])

        # Model name (from HuggingFace Hub)
        self.model_name = "Qwen/Qwen3-Reranker-0.6B"

        # Device configuration
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )

        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True,
        ).to(self.device)

        self.model.eval()

        print(f"[Triton] Qwen3-Reranker model loaded on {self.device}")

    def execute(self, requests):
        """
        Execute reranking on a batch of requests.

        Args:
            requests: List of pb_utils.InferenceRequest

        Returns:
            List of pb_utils.InferenceResponse
        """
        responses = []

        for request in requests:
            # Get inputs
            query_tensor = pb_utils.get_input_tensor_by_name(request, "QUERY")
            docs_tensor = pb_utils.get_input_tensor_by_name(request, "DOCUMENTS")

            query = query_tensor.as_numpy()[0]
            documents = docs_tensor.as_numpy().tolist()

            # Decode bytes to strings if necessary
            if isinstance(query, bytes):
                query = query.decode("utf-8")
            if isinstance(documents[0], bytes):
                documents = [d.decode("utf-8") for d in documents]

            try:
                # Create query-document pairs
                pairs = [[query, doc] for doc in documents]

                # Tokenize
                inputs = self.tokenizer(
                    pairs,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)

                # Compute relevance scores
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    # Get logits (relevance scores)
                    scores = outputs.logits[:, 0].cpu().numpy()

                # Apply softmax for normalized scores (optional)
                # scores = torch.softmax(torch.tensor(scores), dim=0).numpy()

                # Create output tensor
                output_tensor = pb_utils.Tensor(
                    "SCORES", scores.astype(self.output_dtype).reshape(-1)
                )

                # Create response
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[output_tensor]
                )
                responses.append(inference_response)

            except Exception as e:
                # Create error response
                error_message = f"Error processing reranking request: {str(e)}"
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[], error=pb_utils.TritonError(error_message)
                )
                responses.append(inference_response)

        return responses

    def finalize(self):
        """Cleanup when model is unloaded"""
        print("[Triton] Qwen3-Reranker model unloaded")
