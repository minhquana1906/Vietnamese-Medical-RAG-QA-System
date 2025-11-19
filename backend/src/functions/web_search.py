import os

import openai
from loguru import logger
from tavily import TavilyClient

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


def get_tavily_client():
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        return client
    except Exception as e:
        logger.error(f"Error initializing Tavily client: {e}")
        raise


def tavily_search(query):
    """
    Search web using Tavily API with content truncation to prevent context overflow.
    
    Args:
        query: Search query string
        
    Returns:
        Formatted search results with truncated content (max 300 chars per source)
        
    Note: Truncation prevents vLLM timeout due to exceeding 8192 token context limit
    """
    try:
        client = get_tavily_client()
        # Limit to 2 sources to reduce context size
        output_search = client.search(query).get("results")[:2]
        search_document = "Here are the retrieved documents from the internet:\n\n"

        for i, doc in enumerate(output_search):
            content = doc.get("content", "No content available")
            url = doc.get("url", "No URL available")
            title = doc.get("title", "Untitled")

            # Truncate content to prevent context overflow (vLLM has 8192 token limit)
            # Each source limited to 300 chars (~75 tokens) to leave room for prompt
            max_content_length = 300
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
                logger.debug(f"Truncated source {i+1} content from {len(doc.get('content', ''))} to {max_content_length} chars")

            search_document += f"**Source {i+1}:**\n"
            search_document += f"- Title: {title}\n"
            search_document += f"- Content: {content}\n"
            search_document += f"- URL: {url}\n\n"

        search_document += "---\n"
        search_document += "IMPORTANT: When using these search results in your response, you MUST cite the sources by including the URLs and mentioning which source number you're referencing.\n"

        logger.debug(f"Formatted search results: {len(search_document)} chars total")
        return search_document
    except Exception as e:
        logger.error(f"Error searching for external information using Tavily: {e}")
        raise


functions_info = [
    {
        "name": "tavily_search",
        "description": "Get information in internet based on user query ",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "This is user query",
                },
            },
            "required": ["query"],
        },
    }
]
