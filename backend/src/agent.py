import logging

from celery import shared_task
from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.llms.openai import OpenAI

from .functions.calculator import add, divide, multiply, subtract
from .functions.helper import get_tool_schema
from .functions.web_search import tavily_search

multiply_tool = FunctionTool.from_defaults(
    fn=multiply, name="multiply", description="Multiply two integers"
)
add_tool = FunctionTool.from_defaults(
    fn=add, name="add", description="Add two integers"
)
subtract_tool = FunctionTool.from_defaults(
    fn=subtract, name="subtract", description="Subtract two integers"
)
divide_tool = FunctionTool.from_defaults(
    fn=divide, name="divide", description="Divide two integers"
)
search_tool = FunctionTool.from_defaults(
    fn=tavily_search, name="search_internet", description="Search the internet"
)

llm = OpenAI(model="gpt-4o-mini")
ai_agent = ReActAgent.from_tools(
    [
        multiply_tool,
        add_tool,
        subtract_tool,
        divide_tool,
        search_tool,
    ],
    llm=llm,
    verbose=True,
)

available_tools = {
    "multiply": multiply_tool,
    "add": add_tool,
    "subtract": subtract_tool,
    "divide": divide_tool,
    "search_internet": search_tool,
}


def get_tool_list():
    tools = [
        get_tool_schema(add_tool),
        get_tool_schema(subtract_tool),
        get_tool_schema(multiply_tool),
        get_tool_schema(divide_tool),
        get_tool_schema(search_tool),
    ]
    return tools


# TODO: Refactor agent logic and add history handling
@shared_task()
def ai_agent_handle(question):
    response = ai_agent.chat(question)
    logging.info(f"Agent response: {response}")
    return response.response
