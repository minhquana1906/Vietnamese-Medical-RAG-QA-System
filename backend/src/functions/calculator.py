def multiply(a: int | float, b: int | float) -> int | float:
    """Multiply two numbers and returns the result"""
    return a * b


def add(a: int | float, b: int | float) -> int | float:
    """Add two numbers and returns the result"""
    return a + b


def subtract(a: int | float, b: int | float) -> int | float:
    """Subtract two numbers and returns the result"""
    return a - b


def divide(a: int | float, b: int | float) -> int | float:
    """Divide two number and returns the result number"""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
