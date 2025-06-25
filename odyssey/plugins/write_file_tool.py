"""
WriteFileTool for the Odyssey agent.
Allows writing string content to files within a sandboxed, pre-configured safe directory.
"""
import os
import logging
from typing import Dict, Any, Optional
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.write_file_tool")

# Use the same safe directory base as ReadFileTool for consistency.
# This path will be created by the tool if it doesn't exist.
SAFE_DIR_NAME = "agent_files"
BASE_FILE_PATH = os.path.abspath(os.path.join(os.getcwd(), "var", SAFE_DIR_NAME))


class WriteFileTool(ToolInterface):
    """
    A tool to write string content to a specified file in a safe, sandboxed directory.
    Supports 'overwrite' and 'append' modes. Prevents directory traversal.
    """
    name: str = "write_file"
    description: str = f"Writes string content to a specified file in the agent's sandboxed directory ({SAFE_DIR_NAME}). Supports 'overwrite' and 'append' modes."

    def __init__(self):
        super().__init__()
        # Ensure the safe directory exists
        if not os.path.exists(BASE_FILE_PATH):
            try:
                os.makedirs(BASE_FILE_PATH, exist_ok=True)
                logger.info(f"[{self.name}] Created safe directory: {BASE_FILE_PATH}")
            except OSError as e:
                logger.error(f"[{self.name}] Failed to create safe directory {BASE_FILE_PATH}: {e}", exc_info=True)
                # This is a critical failure for the tool's operation.

    def _get_safe_filepath(self, filename: str) -> Optional[str]:
        """
        Validates the filename and constructs an absolute path within the safe directory.
        Prevents directory traversal. Allows creating new files directly in the safe dir.
        """
        if not filename or ".." in filename or filename.startswith("/"):
            logger.warning(f"[{self.name}] Invalid or potentially unsafe filename attempted for writing: '{filename}'")
            return None

        base_filename = os.path.basename(filename)
        if base_filename != filename:
            logger.warning(f"[{self.name}] Filename '{filename}' contained path components. Using only basename: '{base_filename}'. Files can only be written directly in the safe directory.")
            # To strictly disallow any path-like input, one might return None here.
            # For now, we proceed with the basename, effectively flattening any path.

        full_path = os.path.normpath(os.path.join(BASE_FILE_PATH, base_filename))

        if os.path.commonprefix([full_path, BASE_FILE_PATH]) != BASE_FILE_PATH:
            logger.error(f"[{self.name}] Path traversal attempt detected or resolved path is outside safe directory for writing. Filename: '{filename}', Resolved: '{full_path}'")
            return None

        return full_path

    def execute(self, filename: str, content: str, mode: Optional[str] = "overwrite") -> Dict[str, Any]:
        """
        Writes content to the specified file in the safe directory.

        Args:
            filename (str): The name of the file to write to (must be within the safe directory).
            content (str): The string content to write to the file.
            mode (Optional[str]): Write mode. 'overwrite' (default) or 'append'.

        Returns:
            Dict[str, Any]: A dictionary with "result" (success message) and "status": "success",
                            or "error" message and "status": "error".
        """
        logger.info(f"[{self.name}] Attempting to write to file: '{filename}', mode: '{mode}', content length: {len(content)}")

        safe_filepath = self._get_safe_filepath(filename)
        if not safe_filepath:
            return {"error": f"Invalid or unsafe filename: '{filename}'. Writing is restricted to the designated agent directory.", "status": "error"}

        # Validate mode
        normalized_mode = mode.lower() if mode else "overwrite"
        if normalized_mode not in ["overwrite", "append"]:
            err_msg = f"Invalid mode: '{mode}'. Must be 'overwrite' or 'append'."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        file_mode = 'w' if normalized_mode == "overwrite" else 'a'

        try:
            # Ensure containing directory exists (BASE_FILE_PATH should already from __init__)
            # os.makedirs(os.path.dirname(safe_filepath), exist_ok=True) # Not strictly needed if only allowing files in BASE_FILE_PATH

            with open(safe_filepath, file_mode, encoding='utf-8') as f:
                f.write(content)

            success_msg = f"Successfully wrote {len(content)} bytes to '{filename}' (mode: {normalized_mode})."
            logger.info(f"[{self.name}] {success_msg}")
            return {"result": success_msg, "status": "success"}
        except IOError as e:
            logger.error(f"[{self.name}] IOError writing to file '{filename}': {e}", exc_info=True)
            return {"error": f"Could not write to file '{filename}': {e}", "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error writing to file '{filename}': {e}", exc_info=True)
            return {"error": f"An unexpected error occurred while writing to '{filename}'.", "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The name of the file to write to in the agent's sandboxed directory."
                    },
                    "content": {
                        "type": "string",
                        "description": "The string content to write to the file."
                    },
                    "mode": {
                        "type": "string",
                        "description": "Write mode: 'overwrite' to replace the file content, or 'append' to add to the end.",
                        "enum": ["overwrite", "append"],
                        "default": "overwrite"
                    }
                },
                "required": ["filename", "content"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')
    tool = WriteFileTool()

    test_filename = "test_write.txt"
    test_filepath = os.path.join(BASE_FILE_PATH, test_filename) # Used for verification

    print(f"Base file path for tool: {BASE_FILE_PATH}")
    # Directory creation is handled in __init__

    print("\nSchema:", tool.get_schema())

    print("\n--- Test Cases ---")
    print("1. Write (overwrite) to new file:")
    res1 = tool.execute(filename=test_filename, content="Hello from WriteFileTool!\nFirst line.")
    print(res1)
    if os.path.exists(test_filepath):
        with open(test_filepath, "r") as f: print(f"  Content: '{f.read().strip()}'")

    print("\n2. Append to existing file:")
    res2 = tool.execute(filename=test_filename, content="Second line, appended.", mode="append")
    print(res2)
    if os.path.exists(test_filepath):
        with open(test_filepath, "r") as f: print(f"  Content: '{f.read().strip()}'")

    print("\n3. Overwrite existing file:")
    res3 = tool.execute(filename=test_filename, content="This is a complete overwrite.", mode="overwrite") # or default mode
    print(res3)
    if os.path.exists(test_filepath):
        with open(test_filepath, "r") as f: print(f"  Content: '{f.read().strip()}'")

    print("\n4. Attempt directory traversal (should fail):")
    print(tool.execute(filename="../evil.txt", content="sneaky"))
    print(tool.execute(filename="/tmp/another.txt", content="system write"))

    print("\n5. Invalid mode:")
    print(tool.execute(filename="test_invalid_mode.txt", content="test", mode="delete"))


    # Clean up the test file
    if os.path.exists(test_filepath):
        os.remove(test_filepath)
        print(f"\nCleaned up test file: {test_filepath}")

    if os.path.exists(BASE_FILE_PATH) and not os.listdir(BASE_FILE_PATH):
        try:
            os.rmdir(BASE_FILE_PATH)
            print(f"Cleaned up directory: {BASE_FILE_PATH}")
        except OSError:
            print(f"Could not remove directory: {BASE_FILE_PATH}")
```
