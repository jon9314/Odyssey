"""
Random String Generator tool for the Odyssey agent.
Generates random strings of specified length and character set.
"""
import random
import string
import logging
from typing import Dict, Any, Optional
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.random_string_tool")

class RandomStringTool(ToolInterface):
    """
    A tool to generate random strings with configurable length and character set.
    Useful for creating test data, unique identifiers, temporary passwords, etc.
    """
    name: str = "random_string_tool"
    description: str = "Generates a random string of a specified length using a chosen character set (alphanumeric, alpha, numeric, hex)."

    CHARSET_ALPHANUMERIC = string.ascii_letters + string.digits
    CHARSET_ALPHA = string.ascii_letters
    CHARSET_NUMERIC = string.digits
    CHARSET_HEX = string.hexdigits.lower() # Use lowercase hex for consistency

    def __init__(self):
        super().__init__()

    def execute(self, length: Optional[int] = 12, charset: Optional[str] = "alphanumeric") -> Dict[str, Any]:
        """
        Generates a random string.

        Args:
            length (Optional[int]): The desired length of the random string. Defaults to 12.
                                    Must be a positive integer.
            charset (Optional[str]): The character set to use. Defaults to "alphanumeric".
                                     Valid options: "alphanumeric", "alpha", "numeric", "hex".

        Returns:
            Dict[str, Any]: A dictionary containing the generated string under "result" and
                            status "success", or an "error" message and status "error".
        """
        log_message = f"[{self.name}] execute called. length={length}, charset='{charset}'"
        logger.info(log_message)

        if not isinstance(length, int) or length <= 0:
            err_msg = "Invalid 'length' parameter. Must be a positive integer."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        selected_charset_str = charset.lower() if charset else "alphanumeric"

        char_pool = ""
        if selected_charset_str == "alphanumeric":
            char_pool = self.CHARSET_ALPHANUMERIC
        elif selected_charset_str == "alpha":
            char_pool = self.CHARSET_ALPHA
        elif selected_charset_str == "numeric":
            char_pool = self.CHARSET_NUMERIC
        elif selected_charset_str == "hex":
            char_pool = self.CHARSET_HEX
        else:
            err_msg = f"Invalid 'charset' parameter: '{charset}'. Valid options are 'alphanumeric', 'alpha', 'numeric', 'hex'."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        if not char_pool: # Should not happen if logic above is correct
            err_msg = "Character pool is empty, internal error."
            logger.error(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        random_string = ''.join(random.choice(char_pool) for _ in range(length))

        logger.info(f"[{self.name}] Generated random string: '{random_string}' (length: {length}, charset: {selected_charset_str})")
        return {"result": random_string, "status": "success"}

    def get_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON schema for the RandomStringTool.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "length": {
                        "type": "integer",
                        "description": "The desired length of the random string. Must be a positive integer.",
                        "default": 12
                    },
                    "charset": {
                        "type": "string",
                        "description": "The character set to use for generating the string.",
                        "enum": ["alphanumeric", "alpha", "numeric", "hex"],
                        "default": "alphanumeric"
                    }
                },
                "required": [] # No parameters are strictly required as they have defaults
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    rst_tool = RandomStringTool()

    print("Schema:", rst_tool.get_schema())

    print("\nDefault random string (length 12, alphanumeric):")
    res1 = rst_tool.execute()
    print(res1)
    if res1.get("status") == "success":
        print(f"  Length: {len(res1.get('result', ''))}")


    print("\nRandom string (length 8, hex):")
    res2 = rst_tool.execute(length=8, charset="hex")
    print(res2)
    if res2.get("status") == "success":
        print(f"  Length: {len(res2.get('result', ''))}")

    print("\nRandom string (length 16, alpha):")
    res3 = rst_tool.execute(length=16, charset="alpha")
    print(res3)
    if res3.get("status") == "success":
        print(f"  Length: {len(res3.get('result', ''))}")


    print("\nRandom string (length 10, numeric):")
    res4 = rst_tool.execute(length=10, charset="numeric")
    print(res4)
    if res4.get("status") == "success":
        print(f"  Length: {len(res4.get('result', ''))}")


    print("\nInvalid length (0):")
    print(rst_tool.execute(length=0))

    print("\nInvalid length (-5):")
    print(rst_tool.execute(length=-5))

    print("\nInvalid charset ('symbols'):")
    print(rst_tool.execute(charset="symbols"))

    print("\nInvalid length type ('ten'):")
    print(rst_tool.execute(length="ten"))
