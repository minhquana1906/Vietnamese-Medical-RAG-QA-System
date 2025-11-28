# Plan: Comprehensive RAG Evaluation với Ragas + LlamaIndex

Refactor hoàn toàn evaluation system để sử dụng Ragas v0.3.x đúng cách, kết hợp LlamaIndex cho testset generation, và fix các vấn đề dataset quality khiến retrieval metrics rất thấp (context_recall chỉ 23.9%).

## Steps

1. **Upgrade Ragas & fix dependencies**: Cập nhật `ragas>=0.3.9` trong `pyproject.toml`, thêm `langchain-openai` hoặc `langchain-community` cho embeddings wrapper. Đảm bảo compatible với LlamaIndex 0.14.8.

2. **Refactor testset generation với Ragas native**: Thay thế logic trong `generate_synthetic_eval_dataset.py` bằng `ragas.testset.TestsetGenerator` + `KnowledgeGraph` approach. Điều này đảm bảo ground_truth_contexts khớp với Ragas metrics schema.

3. **Add embedding configuration for semantic metrics**: Trong `evaluate_rag.py`, thêm `LangchainEmbeddingsWrapper` (hoặc dùng embedding model hiện có từ `backend.src.services.embedding`) để `AnswerRelevancy`, `AnswerSemanticSimilarity` hoạt động đúng.

4. **Fix ground_truth_contexts validation**: Thêm validation step kiểm tra ground_truth_contexts có tồn tại trong vector store (Qdrant) không. Nếu không match → regenerate hoặc log warning. Đây là root cause của context_recall thấp.

5. **Implement proper Ragas evaluation flow**: Refactor `run_evaluation()` function theo Ragas v0.3.9 docs: sử dụng `SingleTurnSample`, `EvaluationDataset.from_list()`, configure đúng `llm` và `embeddings` cho từng metric.

6. **Update eval_utils.py với retrieval metrics**: Thêm traditional retrieval metrics (Recall@K, nDCG@K, MRR, Precision@K) để có view đầy đủ hơn ngoài Ragas context metrics. Dùng `ground_truth_contexts` overlap với `retrieved_contexts` để tính.

## Notes

1. **Dataset source**: Ragas testset generation cần LlamaIndex Documents từ database hoặc local files => Load từ database (`load_documents_from_db()`) với limit 200-300 docs để generate 200 QA pairs. Lấy sample ngẫu nhiên từ database.

2. **Embedding model cho evaluation**: Dùng Qwen3-Embedding-0.6B (local GPU service) cho embeddings trong Ragas evaluation. Tương tự với Reranker và Guardrails nếu cần.

3. **Testset size vs quality**: Tăng `--num-samples` default lên 200 để có đánh giá tốt hơn. Chú ý chất lượng dataset (context relevance) ảnh hưởng lớn đến retrieval metrics.
