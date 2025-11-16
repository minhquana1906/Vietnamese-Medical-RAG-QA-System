import json
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    """Triton Python Backend for Qwen3-Embedding-0.6B"""

    def initialize(self, args):
        """
        Initialize the model. This function is called once when the model is loaded.

        Args:
            args: Dictionary containing model configuration
        """
        self.model_config = json.loads(args["model_config"])

        # Get output configuration
        output_config = pb_utils.get_output_config_by_name(
            self.model_config, "OUTPUT_EMBEDDING"
        )
        self.output_dtype = pb_utils.triton_string_to_numpy(output_config["data_type"])

        # Model name (from HuggingFace Hub)
        self.model_name = "Qwen/Qwen3-Embedding-0.6B"

        # Device configuration
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=True
        )

        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True,
        ).to(self.device)

        self.model.eval()

        print(f"[Triton] Qwen3-Embedding model loaded on {self.device}")

    def execute(self, requests):
        """
        Execute inference on a batch of requests.

        Args:
            requests: List of pb_utils.InferenceRequest

        Returns:
            List of pb_utils.InferenceResponse
        """
        responses = []

        for request in requests:
            # Get input text
            input_tensor = pb_utils.get_input_tensor_by_name(request, "INPUT_TEXT")
            texts = input_tensor.as_numpy().tolist()

            # Decode bytes to strings if necessary
            if isinstance(texts[0], bytes):
                texts = [t.decode("utf-8") for t in texts]

            try:
                # Tokenize
                inputs = self.tokenizer(
                    texts,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)

                # Generate embeddings
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    # Use [CLS] token embedding (first token)
                    embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

                # Normalize embeddings (for cosine similarity)
                embeddings = embeddings / np.linalg.norm(
                    embeddings, axis=1, keepdims=True
                )

                # Create output tensor
                output_tensor = pb_utils.Tensor(
                    "OUTPUT_EMBEDDING", embeddings.astype(self.output_dtype)
                )

                # Create response
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[output_tensor]
                )
                responses.append(inference_response)

            except Exception as e:
                # Create error response
                error_message = f"Error processing request: {str(e)}"
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[], error=pb_utils.TritonError(error_message)
                )
                responses.append(inference_response)

        return responses

    def finalize(self):
        """Cleanup when model is unloaded"""
        print("[Triton] Qwen3-Embedding model unloaded")
