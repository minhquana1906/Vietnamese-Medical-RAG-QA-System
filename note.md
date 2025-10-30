# SPEC:
```
/speckit.specify title: improve_rag_system
Tôi muốn thực hiện các cải tiến như sau:
- Thay vì sử dụng Streamlit như hiện tại, tôi muốn đổi sang sử dụng Chainlit để xây dựng UI (RAG native hơn, hỗ trợ đầy đủ chat session life cycle, signin/signup với password và Oauth,...). Tài liệu chính thức tham khảo tại: https://docs.chainlit.io
- Cập nhật lại database mới toàn diện hơn (chỉ cần lưu trữ lại các thành phần cần thiết cho việc quản lý người dùng cũng như các thành phần quan trọng trong workflow. Không cần lưu lại các thành phần phục vụ analysis như tracking, progress...). Về phần chat session và users có thể tham khảo qua database khuyến nghị của chainlit tại: https://docs.chainlit.io/data-layers/sqlalchemy
- Thực hiện đánh giá baseline các model Qwen/Qwen3-4B-Instruct-2507 (generation) trên dataset: https://huggingface.co/datasets/quannguyen204/combined_medical_qa_dataset , Qwen3-Embedding-0.6B (embedding) trên dataset: https://huggingface.co/datasets/mtue29/vietnamese-medical-dataset sau đó tiến hành finetune, tracking và thực hiện evaluation sau khi đã finetuned so sánh với kết quả baseline của model khi chưa finetune. Sau khi kết quả evaluation đã ổn thì tiến hành serve các model Qwen/Qwen3-4B-Instruct-2507 (generation, đã finetuned), Qwen3-Embedding-0.6B (embedding, đã finetuned), Qwen3-Reranking-0.6B (rerank), Qwen3-Guard-Gen-0.6B (guardrails). Lưu ý rằng qwen3 sử dụng các kiến trúc đặc biệt nên khi finetuning, serving cần cài đặt cẩn thận theo hướng dẫn, best pratices của qwen team tại các urls: (https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507, https://huggingface.co/Qwen/Qwen3-Embedding-0.6B, https://huggingface.co/Qwen/Qwen3-Reranker-0.6B, https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B )
- Load các data từ dataset (url: https://huggingface.co/datasets/quannguyen204/combined_medical_dataset ) vào vector database của tôi. Cải thiện lại các metadata và cách lưu trữ id của các chunk được upload vào vector database
- Cái thiện phương pháp chunking
- Sử dụng model qwen3 embedding đã finetuned để embed và index dữ liệu từ dataset: https://huggingface.co/datasets/quannguyen204/combined_medical_dataset vào vector database
- Cái thiện phương pháp retrieve sử dụng Hybrid search Reciprocal Rank Fusion (RRF)
- Thêm cache layer để tối ưu hiệu suất inference
- Xây dựng hệ thống giám sát (đặc biệt phải log, trace và scrape được các metrics quan trọng của luồng RAG)
- Thực hiện đánh giá stress test, load test cho hệ thống RAG
```
