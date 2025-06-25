# This file makes the 'plugins' directory a Python package.
# It can be empty or can be used to selectively import plugin modules
# if a more controlled loading mechanism than full directory scanning is desired later.

# For auto-discovery, ToolManager will scan this directory for .py files.
# logger = logging.getLogger("odyssey.plugins")
# logger.info("Odyssey plugins package initialized.")

# Example of how you might pre-load or expose specific tools if not using pure auto-discovery:
# from .calculator_tool import CalculatorTool
# from .some_other_tool import SomeOtherTool
#
# __all__ = ["CalculatorTool", "SomeOtherTool"] # If you want to control `from odyssey.plugins import *`
```
