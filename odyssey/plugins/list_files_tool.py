"""
ListFilesTool for the Odyssey agent.
Lists files within the sandboxed, pre-configured safe directory.
"""
import os
import logging
from typing import Dict, Any, List
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.list_files_tool")

# Use the same safe directory base as ReadFileTool and WriteFileTool for consistency.
SAFE_DIR_NAME = "agent_files"
BASE_FILE_PATH = os.path.abspath(os.path.join(os.getcwd(), "var", SAFE_DIR_NAME))


class ListFilesTool(ToolInterface):
    """
    A tool to list all files within the agent's safe, sandboxed directory.
    Does not list directories, only files.
    """
    name: str = "list_files"
    description: str = f"Lists all files (not directories) within the agent's sandboxed directory ({SAFE_DIR_NAME})."

    def __init__(self):
        super().__init__()
        # Ensure the safe directory exists, though this tool primarily reads its listing.
        if not os.path.exists(BASE_FILE_PATH):
            try:
                os.makedirs(BASE_FILE_PATH, exist_ok=True)
                logger.info(f"[{self.name}] Ensured safe directory exists: {BASE_FILE_PATH}")
            except OSError as e:
                logger.error(f"[{self.name}] Failed to ensure/create safe directory {BASE_FILE_PATH}: {e}", exc_info=True)
                # This might not be fatal for list_files if the dir doesn't exist (it will return empty list),
                # but good to log.

    def execute(self) -> Dict[str, Any]: # No arguments needed for this tool as per spec
        """
        Lists all files (not directories) in the pre-configured safe directory.

        Args:
            None

        Returns:
            Dict[str, Any]: A dictionary with "result" (a list of filenames) and "status": "success",
                            or "error" message and "status": "error" if the directory cannot be accessed.
        """
        logger.info(f"[{self.name}] Attempting to list files in directory: '{BASE_FILE_PATH}'")

        if not os.path.exists(BASE_FILE_PATH):
            # This case might be redundant if __init__ successfully creates it,
            # but good for robustness if directory creation failed or was deleted post-init.
            logger.warning(f"[{self.name}] Safe directory not found: {BASE_FILE_PATH}")
            return {"error": f"Agent's file directory '{SAFE_DIR_NAME}' not found.", "status": "error"}

        if not os.path.isdir(BASE_FILE_PATH):
            logger.error(f"[{self.name}] Configured safe path is not a directory: {BASE_FILE_PATH}")
            return {"error": f"Agent's file storage path is misconfigured (not a directory).", "status": "error"}

        try:
            filenames = [f for f in os.listdir(BASE_FILE_PATH) if os.path.isfile(os.path.join(BASE_FILE_PATH, f))]
            logger.info(f"[{self.name}] Found {len(filenames)} files in '{BASE_FILE_PATH}': {filenames}")
            return {"result": filenames, "status": "success"}
        except OSError as e:
            logger.error(f"[{self.name}] OSError listing files in '{BASE_FILE_PATH}': {e}", exc_info=True)
            return {"error": f"Could not list files in agent directory: {e}", "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error listing files in '{BASE_FILE_PATH}': {e}", exc_info=True)
            return {"error": "An unexpected error occurred while listing files.", "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": { # No parameters for this tool
                "type": "object",
                "properties": {},
                "required": []
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')
    tool = ListFilesTool()

    print(f"Base file path for tool: {BASE_FILE_PATH}")
    # Ensure directory exists for test
    if not os.path.exists(BASE_FILE_PATH):
        os.makedirs(BASE_FILE_PATH, exist_ok=True)

    # Create some dummy files and a directory for testing
    dummy_files = ["file1.txt", "file2.log", "another.md"]
    dummy_dir = "test_subdir"

    for fname in dummy_files:
        with open(os.path.join(BASE_FILE_PATH, fname), "w") as f:
            f.write(f"dummy content for {fname}")

    os.makedirs(os.path.join(BASE_FILE_PATH, dummy_dir), exist_ok=True)
    with open(os.path.join(BASE_FILE_PATH, dummy_dir, "sub_file.txt"), "w") as f:
        f.write("content in subdir")

    print("\nSchema:", tool.get_schema())

    print("\n--- Test Case: List files ---")
    result = tool.execute()
    print(result)
    if result.get("status") == "success":
        assert all(fname in result.get("result", []) for fname in dummy_files), "Not all dummy files listed"
        assert dummy_dir not in result.get("result", []), "Subdirectory should not be listed"
        print("Test assertion passed: lists files, excludes directories.")


    # Clean up dummy files and directory
    print("\nCleaning up test files and directory...")
    for fname in dummy_files:
        try:
            os.remove(os.path.join(BASE_FILE_PATH, fname))
        except OSError: pass

    try: # Clean up subdir
        os.remove(os.path.join(BASE_FILE_PATH, dummy_dir, "sub_file.txt"))
        os.rmdir(os.path.join(BASE_FILE_PATH, dummy_dir))
    except OSError: pass

    if os.path.exists(BASE_FILE_PATH) and not os.listdir(BASE_FILE_PATH):
        try:
            os.rmdir(BASE_FILE_PATH)
            print(f"Cleaned up directory: {BASE_FILE_PATH}")
        except OSError:
            print(f"Could not remove directory: {BASE_FILE_PATH}")
```
