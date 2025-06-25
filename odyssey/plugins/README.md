# Odyssey Agent Plugins

This directory contains plugins (tools) that extend the capabilities of the Odyssey agent.
The `ToolManager` component is designed to auto-discover and register valid tools from `.py` files within this directory.

## How to Add a New Tool

1.  **Create a Python File:**
    Create a new `.py` file in this `plugins/` directory (e.g., `my_awesome_tool.py`).

2.  **Implement the Tool Class:**
    Inside your new file, define a class that implements the `ToolInterface` (found in `odyssey.agent.tool_manager`).
    Your class must:
    *   Be a subclass of `ToolInterface` or duck-type implement its methods.
    *   Have a class or instance attribute `name: str` that is unique among tools.
    *   Have a class or instance attribute `description: str` that briefly explains what the tool does.
    *   Implement an `execute(self, **kwargs) -> Any` method. This method will contain the core logic of your tool and will receive arguments as keyword arguments. The return value should be JSON-serializable.
    *   Implement a `get_schema(self) -> Dict[str, Any]` method. This method must return a JSON schema dictionary that describes the tool, its overall purpose (in the schema's `description` field), and the parameters its `execute` method accepts. The schema should follow a structure similar to OpenAI's function calling schema (including `name`, `description`, and `parameters` with `type: "object"`, `properties`, and `required` fields).

3.  **Example Tool Structure (`my_tool.py`):**

    ```python
    # odyssey/plugins/my_tool.py
    import logging
    from typing import Dict, Any, Optional
    from odyssey.agent.tool_manager import ToolInterface
    # If your tool needs core services like MemoryManager:
    # from odyssey.agent.memory import MemoryManager

    logger = logging.getLogger(__name__)

    class MyAwesomeTool(ToolInterface):
        name: str = "my_awesome_tool"
        description: str = "This is a brief description of what My Awesome Tool does."

        # Example of dependency injection:
        # def __init__(self, memory_manager: Optional[MemoryManager] = None, another_service: Optional[Any] = None):
        #     super().__init__() # Important for ToolInterface checks
        #     self.memory_manager = memory_manager
        #     self.another_service = another_service
        #     if self.memory_manager:
        #         logger.info(f"[{self.name}] Initialized with MemoryManager.")
        #     # Any other initialization your tool needs

        def __init__(self): # Simple init if no dependencies needed
            super().__init__()
            logger.info(f"[{self.name}] Initialized.")


        def execute(self, required_param: str, optional_param: int = 0) -> Dict[str, Any]:
            """
            Executes the awesome functionality of this tool.
            """
            logger.info(f"[{self.name}] Executing with required_param='{required_param}', optional_param={optional_param}")

            # Example of using an injected dependency:
            # if self.memory_manager:
            #     self.memory_manager.log_event(message=f"{self.name} executed", level="TOOL_EXEC")

            # --- Your tool's logic here ---
            # IMPORTANT: Return a dictionary with "status" and either "result" or "error".
            try:
                # ... perform action ...
                calculated_result = f"Tool executed with {required_param} and {optional_param}. Output: Processed."
                logger.info(f"[{self.name}] Execution finished. Result: {calculated_result}")
                return {"result": calculated_result, "status": "success"}
            except Exception as e:
                logger.error(f"[{self.name}] Error during execution: {e}", exc_info=True)
                return {"error": str(e), "status": "error"}

        def get_schema(self) -> Dict[str, Any]:
            return {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "required_param": {
                            "type": "string",
                            "description": "A mandatory parameter for this tool."
                        },
                        "optional_param": {
                            "type": "integer",
                            "description": "An optional parameter, defaults to 0 if not provided."
                        }
                    },
                    "required": ["required_param"]
                }
            }

    # If you have multiple tool classes in one file, ToolManager will attempt to load all of them
    # that are subclasses of ToolInterface.
    ```

4.  **Dependency Injection (Optional):**
    If your tool needs access to core Odyssey services (like `MemoryManager`, `OllamaClient`, `ToolManager` itself, or the `celery_app`), you can declare them as type-hinted arguments in your tool's `__init__` method. The `ToolManager` will attempt to inject these dependencies automatically during discovery if they are available.

    Example `__init__` with dependency:
    ```python
    from odyssey.agent.memory import MemoryManager

    class MyDataTool(ToolInterface):
        name = "my_data_tool"
        description = "A tool that interacts with memory."

        def __init__(self, memory_manager: MemoryManager):
            super().__init__()
            self.memory_manager = memory_manager # Store the injected instance
            logger.info(f"[{self.name}] Initialized with MemoryManager.")

        # ... execute and get_schema methods ...
    ```
    The `ToolManager` currently knows how to inject `memory_manager`, `ollama_client`, `celery_app`, and `tool_manager`.

5.  **Auto-Discovery:**
    The `ToolManager` (when its `discover_and_register_plugins()` method is called, typically at agent startup) will automatically scan this directory, import your new `.py` file, find your `ToolInterface`-compliant class, instantiate it (injecting known dependencies if requested in `__init__`), and register it. The tool will then be available for use by the agent and via API endpoints.

## Naming Conventions
-   Tool filenames should be descriptive (e.g., `web_search_tool.py`, `file_system_tool.py`).
-   The `name` attribute within the tool class should be unique and use `snake_case` (e.g., `"web_search"`, `"file_read"`). This name is used to call the tool via the API.

## Dependencies
If your tool has external Python dependencies, ensure they are added to the main project's `requirements.txt` file.

Happy plugin development!
```
