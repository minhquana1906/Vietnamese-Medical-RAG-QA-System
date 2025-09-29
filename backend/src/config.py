# For Google Gemini models
# LLM = "gemini-2.5-flash"
# EMBEDDING_MODEL = "gemini-embedding-001"
# BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# For OpenAI models
LLM = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# LLM's settings
TEMPERATURE = 0.7
MAX_TOKENS = 2048


# Qdrant vector database configuration
DEFAULT_COLLECTION_NAME = "documents"
VECTOR_DIMENSION = 1536
TOP_K = 5

# CHUNKING settings
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

SYSTEM_PROMPT = "Bạn là một trợ lý AI giúp trả lời các câu hỏi về tài liệu y khoa. Hãy trả lời thật chính xác và luôn trả lời bằng ngôn ngữ giống với câu hỏi người dùng."
