import json
import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    """Triton Python Backend for Qwen3Guard-Gen-0.6B"""

    def initialize(self, args):
        """
        Initialize the guardrails model.

        Args:
            args: Dictionary containing model configuration
        """
        self.model_config = json.loads(args["model_config"])

        # Model name (from HuggingFace Hub)
        self.model_name = "Qwen/Qwen3Guard-Gen-0.6B"

        # Safety threshold (adjust based on evaluation)
        self.safety_threshold = 0.5

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

        print(f"[Triton] Qwen3Guard model loaded on {self.device}")
        print(f"[Triton] Safety threshold: {self.safety_threshold}")

    def execute(self, requests):
        """
        Execute safety check on a batch of requests.

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

                # Compute safety scores
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    # Get logits for safety classification
                    logits = outputs.logits

                    # Apply softmax to get probabilities
                    probs = torch.softmax(logits, dim=-1)

                    # Assuming binary classification: [unsafe, safe]
                    # Extract "safe" probability (class 1)
                    safety_scores = probs[:, 1].cpu().numpy()

                    # Determine if content is safe based on threshold
                    is_safe = safety_scores >= self.safety_threshold

                # Create output tensors
                is_safe_tensor = pb_utils.Tensor("IS_SAFE", is_safe.astype(bool))

                safety_score_tensor = pb_utils.Tensor(
                    "SAFETY_SCORE", safety_scores.astype(np.float32)
                )

                # Create response
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[is_safe_tensor, safety_score_tensor]
                )
                responses.append(inference_response)

            except Exception as e:
                # Create error response
                error_message = f"Error processing safety check: {str(e)}"
                inference_response = pb_utils.InferenceResponse(
                    output_tensors=[], error=pb_utils.TritonError(error_message)
                )
                responses.append(inference_response)

        return responses

    def finalize(self):
        """Cleanup when model is unloaded"""
        print("[Triton] Qwen3Guard model unloaded")
