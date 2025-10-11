from function_schema import get_function_schema


def get_tool_schema(function):
    return {"type": "function", "function": get_function_schema(function)}
