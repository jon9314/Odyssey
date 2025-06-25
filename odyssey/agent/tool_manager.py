"""
Manages the registration, discovery, and execution of tools (plugins) for the Odyssey agent.
Tools are expected to conform to the ToolInterface.
"""
import os
import importlib
import inspect
import logging
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger("odyssey.agent.tool_manager")

class ToolInterface:
    """
    A base class (or protocol) that all tools/plugins should implement.
    This ensures tools have a consistent way to be called, describe themselves,
    and be managed by the ToolManager.

    Attributes:
        name (str): A unique name for the tool. This is used for registration and execution.
                    It should be a simple, descriptive string (e.g., "calculator", "file_reader").
        description (str): A brief description of what the tool does. This is primarily for
                           human understanding and can also be used by LLMs if the schema
                           description is not detailed enough or for a quick overview.
                           This will be part of the schema's description field.
    """
    name: str
    description: str

    def __init__(self):
        """
        Tool constructor. Subclasses should ensure `name` and `description` are set,
        either directly as class attributes or in their own `__init__`.
        """
        if not hasattr(self, 'name') or not self.name:
            raise NotImplementedError(f"Tool class {self.__class__.__name__} must define a 'name' attribute.")
        if not hasattr(self, 'description') or not self.description:
            raise NotImplementedError(f"Tool class {self.__class__.__name__} must define a 'description' attribute.")

    def execute(self, **kwargs: Any) -> Any:
        """
        Executes the primary function of the tool.

        Args:
            **kwargs: Keyword arguments specific to the tool's operation,
                      as defined in its parameter schema.

        Returns:
            Any: The result of the tool's execution. This should be a JSON-serializable
                 value (e.g., string, number, boolean, dict, list).

        Raises:
            NotImplementedError: If the subclass does not implement this method.
            Exception: Any exception raised by the tool during its execution should be handled
                       by the caller or allowed to propagate if appropriate.
        """
        raise NotImplementedError(f"Tool class {self.__class__.__name__} must implement the 'execute' method.")

    def get_schema(self) -> Dict[str, Any]:
        """
        Returns a JSON schema describing the tool and its parameters.
        This schema is crucial for LLMs to understand how to use the tool correctly
        (e.g., for function calling or generating appropriate arguments).
        The schema should follow a structure similar to OpenAI's function calling schema.

        Returns:
            Dict[str, Any]: A dictionary representing the JSON schema of the tool.
                            It must include 'name', 'description', and 'parameters'.

        Example schema:
        {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "Description of param1."},
                    "param2": {"type": "integer", "description": "Description of param2."}
                },
                "required": ["param1"]
            }
        }
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }


class ToolManager:
    """
    Manages the lifecycle of tools/plugins within the Odyssey agent.
    It handles registration (manual and auto-discovery), listing, and execution of tools.
    It can also inject known core services into tools that declare them in their __init__.
    """
    def __init__(self,
                 memory_manager: Optional[Any] = None,
                 ollama_client: Optional[Any] = None,
                 celery_app_instance: Optional[Any] = None,
                 app_settings: Optional[Any] = None  # Added app_settings
                 # Add other core services here if they need to be injectable
                ):
        """
        Initializes the ToolManager.

        Args:
            memory_manager: An instance of MemoryManager (or compatible).
            ollama_client: An instance of OllamaClient (or compatible).
            celery_app_instance: An instance of the Celery app.
            app_settings: An instance of AppSettings (or compatible).
        """
        self.tools: Dict[str, ToolInterface] = {}
        self._available_dependencies: Dict[str, Any] = {}

        if memory_manager:
            self._available_dependencies['memory_manager'] = memory_manager
        if ollama_client:
            self._available_dependencies['ollama_client'] = ollama_client
        if celery_app_instance:
            self._available_dependencies['celery_app'] = celery_app_instance
        if app_settings: # Store app_settings for injection
            self._available_dependencies['settings'] = app_settings # Key 'settings'

        # To allow tools to get a reference to this ToolManager instance itself.
        self._available_dependencies['tool_manager'] = self

        logger.info(f"[ToolManager] Initialized. Available dependencies for injection: {list(self._available_dependencies.keys())}")


    def register(self, tool_instance: ToolInterface) -> bool:
        if not isinstance(tool_instance, ToolInterface):
            logger.error(f"[ToolManager] Registration failed: Object {tool_instance} is not an instance of ToolInterface.")
            return False

        try:
            schema = tool_instance.get_schema()
            if not schema.get("name") or not schema.get("description") or "parameters" not in schema:
                logger.error(f"[ToolManager] Registration failed: Tool '{tool_instance.name}' has an invalid schema structure. "
                             "Schema must contain 'name', 'description', and 'parameters'.")
                return False
            if schema["name"] != tool_instance.name:
                 logger.warning(f"[ToolManager] Tool name '{tool_instance.name}' in instance differs from schema name '{schema['name']}'. Using instance name.")

        except Exception as e:
            logger.error(f"[ToolManager] Registration failed for tool '{getattr(tool_instance, 'name', 'UnknownTool')}': Error getting schema: {e}", exc_info=True)
            return False

        if tool_instance.name in self.tools:
            logger.warning(f"[ToolManager] Tool '{tool_instance.name}' is already registered. Overwriting with new instance: {tool_instance.__class__.__name__}.")

        self.tools[tool_instance.name] = tool_instance
        logger.info(f"[ToolManager] Tool '{tool_instance.name}' (class: {tool_instance.__class__.__name__}) registered successfully.")
        return True

    def discover_and_register_plugins(self, plugin_dir_name: str = "plugins") -> int:
        """
        Discovers and registers tools from .py files in the specified plugin directory.
        The plugin_dir_name is expected to be a directory directly under the 'odyssey' package root.
        e.g., if odyssey is the top level, then plugin_dir_name="plugins" refers to "odyssey/plugins".
        """
        registered_count = 0

        # Construct path relative to this file's package 'odyssey'
        # This assumes tool_manager.py is in odyssey/agent/
        # and plugins are in odyssey/plugins/
        current_package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) # .../odyssey/
        abs_plugin_dir_path = os.path.join(current_package_root, plugin_dir_name)

        if not os.path.isdir(abs_plugin_dir_path):
            logger.warning(f"[ToolManager] Plugin directory '{abs_plugin_dir_path}' (resolved from '{plugin_dir_name}') not found. Skipping auto-discovery.")
            return 0

        logger.info(f"[ToolManager] Starting auto-discovery of plugins in '{abs_plugin_dir_path}'...")

        # Base import path for plugins is 'odyssey.plugins'
        base_plugin_import_path = f"odyssey.{plugin_dir_name.replace(os.sep, '.')}"

        for filename in os.listdir(abs_plugin_dir_path):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name_only = filename[:-3]
                module_full_path = f"{base_plugin_import_path}.{module_name_only}"
                try:
                    module = importlib.import_module(module_full_path)
                    for attribute_name in dir(module):
                        attribute = getattr(module, attribute_name)
                        if inspect.isclass(attribute) and issubclass(attribute, ToolInterface) and attribute is not ToolInterface:
                            tool_class = attribute
                            logger.debug(f"[ToolManager] Found potential tool class '{tool_class.__name__}' in '{module_full_path}'.")

                            # Dependency Injection Logic
                            dependencies_to_inject: Dict[str, Any] = {}
                            missing_deps = False
                            try:
                                sig = inspect.signature(tool_class.__init__)
                                for param_name, param in sig.parameters.items():
                                    if param_name == 'self':
                                        continue
                                    if param_name in self._available_dependencies:
                                        dependencies_to_inject[param_name] = self._available_dependencies[param_name]
                                        logger.debug(f"[ToolManager] Preparing to inject '{param_name}' into '{tool_class.__name__}'.")
                                    elif param.default is inspect.Parameter.empty: # Required param with no default
                                        logger.warning(f"[ToolManager] Tool '{tool_class.__name__}' requires dependency '{param_name}' which is not available in ToolManager. Skipping registration.")
                                        missing_deps = True
                                        break
                                if missing_deps:
                                    continue

                                tool_instance = tool_class(**dependencies_to_inject)
                                if self.register(tool_instance): # self.register already logs success/failure
                                    registered_count += 1
                            except TypeError as te: # Handles errors if __init__ signature doesn't match what we try to pass
                                logger.error(f"[ToolManager] TypeError instantiating tool '{tool_class.__name__}' from '{module_full_path}'. Check __init__ signature and dependencies. Error: {te}", exc_info=False) # exc_info=False to avoid long trace for common type errors
                            except Exception as e:
                                logger.error(f"[ToolManager] Failed to instantiate or register tool '{tool_class.__name__}' from '{module_full_path}': {e}", exc_info=True)
                except ImportError as e:
                    logger.error(f"[ToolManager] Failed to import plugin module '{module_full_path}': {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"[ToolManager] Unexpected error processing module '{module_full_path}': {e}", exc_info=True)

        logger.info(f"[ToolManager] Plugin auto-discovery finished. Attempted to load from {len(os.listdir(abs_plugin_dir_path))} files. Successfully registered {registered_count} tool(s).")
        return registered_count

    def unregister(self, tool_name: str) -> bool:
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info(f"[ToolManager] Tool '{tool_name}' unregistered.")
            return True
        else:
            logger.warning(f"[ToolManager] Tool '{tool_name}' not found for unregistration.")
            return False

    def execute(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name not in self.tools:
            err_msg = f"Tool '{tool_name}' not found."
            logger.error(f"[ToolManager] {err_msg}")
            available_tools_names = self.list_tools()
            return {"error": True, "message": err_msg, "available_tools": available_tools_names or "None"}

        tool_instance = self.tools[tool_name]
        args_snippet = str(kwargs)[:100] + ('...' if len(str(kwargs)) > 100 else '')
        logger.info(f"[ToolManager] Executing tool '{tool_name}' with arguments (snippet): {args_snippet}")

        try:
            result = tool_instance.execute(**kwargs)
            result_snippet = str(result)[:100] + ('...' if len(str(result)) > 100 else '')
            logger.info(f"[ToolManager] Tool '{tool_name}' execution successful. Result (snippet): {result_snippet}")
            return result
        except Exception as e:
            logger.error(f"[ToolManager] Error executing tool '{tool_name}': {e}", exc_info=True)
            return {"error": True, "message": f"Error during execution of tool '{tool_name}'", "details": f"{type(e).__name__}: {e}"}

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        if tool_name in self.tools:
            try:
                return self.tools[tool_name].get_schema()
            except Exception as e:
                logger.error(f"[ToolManager] Error retrieving schema for tool '{tool_name}': {e}", exc_info=True)
                return None
        else:
            logger.warning(f"[ToolManager] Schema requested for unknown tool: '{tool_name}'")
            return None

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        for tool_name, tool_instance in self.tools.items():
            try:
                schemas.append(tool_instance.get_schema())
            except Exception as e:
                logger.error(f"[ToolManager] Error retrieving schema for tool '{tool_name}' during get_all_tool_schemas: {e}", exc_info=True)
        return schemas

# The if __name__ == '__main__': block has been removed to prevent syntax errors
# during automated testing. Individual tools have their own test blocks,
# and ToolManager functionality will be tested via integration tests
# or by running the main application and using its API endpoints.
```
