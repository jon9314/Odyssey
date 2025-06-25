"""
A simple calculator tool for the Odyssey agent.
This tool can perform basic arithmetic operations: add, subtract, multiply, divide.
"""
import logging
from typing import Union, Dict, Any
from odyssey.agent.tool_manager import ToolInterface # Import base class

logger = logging.getLogger("odyssey.plugins.calculator_tool")

class CalculatorTool(ToolInterface):
    """
    A tool that performs basic arithmetic calculations.
    It takes two numbers and an operation string as input.
    """
    name: str = "calculator"
    description: str = "Performs basic arithmetic operations (add, subtract, multiply, divide) on two numbers."

    def __init__(self):
        # Call super().__init__() if ToolInterface's __init__ does actual work,
        # but here it mainly enforces attribute existence which is fine with class attributes.
        # super().__init__()
        pass

    def execute(self, num1: Union[int, float], num2: Union[int, float], operation: str) -> Dict[str, Any]:
        """
        Executes the specified arithmetic operation.

        Args:
            num1: The first number.
            num2: The second number.
            operation: The operation to perform. Must be one of 'add', 'subtract',
                       'multiply', or 'divide'.

        Returns:
            A dictionary containing the result and status "success",
            or an error message and status "error".
        """
        logger.info(f"[{self.name}] Executing operation: '{operation}' with num1={num1}, num2={num2}")

        op = operation.lower()

        try:
            # Ensure inputs can be treated as numbers
            val1 = float(num1)
            val2 = float(num2)

            if op == 'add':
                result = val1 + val2
            elif op == 'subtract':
                result = val1 - val2
            elif op == 'multiply':
                result = val1 * val2
            elif op == 'divide':
                if val2 == 0:
                    err_msg = "Division by zero."
                    logger.warning(f"[{self.name}] {err_msg} Attempted: {val1}/{val2}")
                    return {"error": err_msg, "status": "error"}
                result = val1 / val2
            else:
                err_msg = f"Invalid operation '{operation}'. Must be one of 'add', 'subtract', 'multiply', 'divide'."
                logger.warning(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}

            logger.info(f"[{self.name}] Operation '{operation}' result: {result}")
            return {"result": result, "status": "success"}

        except ValueError:
            err_msg = "Invalid number input. 'num1' and 'num2' must be numbers."
            logger.warning(f"[{self.name}] {err_msg} Received num1='{num1}', num2='{num2}'.")
            return {"error": err_msg, "status": "error"}
        except Exception as e: # Catch any other unexpected errors during calculation
            err_msg = f"An unexpected error occurred during calculation: {e}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}


    def get_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON schema for the CalculatorTool.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "num1": {
                        "type": "number",
                        "description": "The first number for the operation."
                    },
                    "num2": {
                        "type": "number",
                        "description": "The second number for the operation."
                    },
                    "operation": {
                        "type": "string",
                        "description": "The arithmetic operation to perform.",
                        "enum": ["add", "subtract", "multiply", "divide"]
                    }
                },
                "required": ["num1", "num2", "operation"]
            }
        }

if __name__ == '__main__':
    # Example usage for direct testing of the tool
    logging.basicConfig(level=logging.INFO)
    calc_tool = CalculatorTool()

    # Test schema
    print("Schema:", calc_tool.get_schema())

    # Test cases
    print("\nTest Add (5 + 3):", calc_tool.execute(num1=5, num2=3, operation="add"))
    print("Test Subtract (10 - 4):", calc_tool.execute(num1=10, num2=4, operation="subtract"))
    print("Test Multiply (6 * 7):", calc_tool.execute(num1=6, num2=7, operation="multiply"))
    print("Test Divide (20 / 5):", calc_tool.execute(num1=20, num2=5, operation="divide"))
    print("Test Divide by Zero (10 / 0):", calc_tool.execute(num1=10, num2=0, operation="divide"))
    print("Test Invalid Operation (10 @ 2):", calc_tool.execute(num1=10, num2=2, operation="modulo"))
    print("Test with floats (3.5 * 2.0):", calc_tool.execute(num1=3.5, num2=2.0, operation="multiply"))

```
