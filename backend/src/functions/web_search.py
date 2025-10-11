import os

import openai
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def tavily_search(query):
    output_search = tavily_client.search(query).get("results")[:3]
    search_document = "Here are the retrieved documents from the internet:\n\n"

    for i, doc in enumerate(output_search):
        content = doc.get("content", "No content available")
        url = doc.get("url", "No URL available")
        title = doc.get("title", "Untitled")

        search_document += f"**Source {i+1}:**\n"
        search_document += f"- Title: {title}\n"
        search_document += f"- Content: {content}\n"
        search_document += f"- URL: {url}\n\n"

    search_document += "---\n"
    search_document += "IMPORTANT: When using these search results in your response, you MUST cite the sources by including the URLs and mentioning which source number you're referencing.\n"

    return search_document


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
