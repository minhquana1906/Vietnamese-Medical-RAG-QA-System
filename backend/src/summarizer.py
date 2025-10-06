from loguru import logger

from .brain import openai_chat_complete


def get_summarized_content(text):
    try:
        messages = [
            {
                "role": "system",
                "content": "You are an AI assistant in summarizing conversations. Your task is to provide concise summaries that capture the main points of the conversation while retaining all essential information.",
            },
            {
                "role": "user",
                "content": f"Conversation Content:\n:{text}\n\nOutput:\n",
            },
        ]

        return openai_chat_complete(messages, temperature=0.5, max_tokens=512)
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        raise
