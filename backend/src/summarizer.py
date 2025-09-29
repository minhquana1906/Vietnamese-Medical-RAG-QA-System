from loguru import logger

from .brain import openai_chat_complete


def get_summarized_content(text):
    try:
        messages = [
            {
                "role": "system",
                "content": "Bạn là một trợ lý AI giúp tóm tắt nội dung các cuộc trò chuyện. Hãy tóm tắt ngắn gọn nhưng phải luôn giữ đầy đủ ý chính của cuộc trò chuyện.",
            },
            {
                "role": "user",
                "content": f"## Nội dung hội thoại\n: {text}\n\nOutput:",
            },
        ]

        llm_response = openai_chat_complete(messages, temperature=0.5, max_tokens=512)
        logger.info(f"Summarized text: {llm_response}")
        return llm_response
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        raise
