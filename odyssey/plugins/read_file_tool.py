"""
ReadFileTool for the Odyssey agent.
Allows reading content from files within a sandboxed, pre-configured safe directory.
"""
import os
import logging
from typing import Dict, Any, Optional
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.read_file_tool")

# Define a base directory for file operations.
# This should be an absolute path or resolved relative to a known project root.
# For security, tools should not be able to write outside this directory.
# Example: os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), "agent_workspace", "shared_files")
# For now, using a simpler relative path that assumes execution from project root or that `var` is accessible.
# This path will be created by the tool if it doesn't exist.
SAFE_DIR_NAME = "agent_files" # This will be inside 'var/'
BASE_FILE_PATH = os.path.abspath(os.path.join(os.getcwd(), "var", SAFE_DIR_NAME))


class ReadFileTool(ToolInterface):
    """
    A tool to read the content of a specified file from a safe, sandboxed directory.
    Prevents directory traversal and limits the number of bytes read.
    """
    name: str = "read_file"
    description: str = f"Reads the content of a specified text file from the agent's sandboxed directory ({SAFE_DIR_NAME}). Allows specifying max bytes to read."

    def __init__(self):
        super().__init__()
        # Ensure the safe directory exists
        if not os.path.exists(BASE_FILE_PATH):
            try:
                os.makedirs(BASE_FILE_PATH, exist_ok=True)
                logger.info(f"[{self.name}] Created safe directory: {BASE_FILE_PATH}")
            except OSError as e:
                logger.error(f"[{self.name}] Failed to create safe directory {BASE_FILE_PATH}: {e}", exc_info=True)
                # If directory can't be created, tool might be unusable. Consider raising an error.
                # For now, it will lead to errors when trying to access files.

    def _get_safe_filepath(self, filename: str) -> Optional[str]:
        """
        Validates the filename and constructs an absolute path within the safe directory.
        Prevents directory traversal.
        """
        if not filename or ".." in filename or filename.startswith("/"):
            logger.warning(f"[{self.name}] Invalid or potentially unsafe filename attempted: '{filename}'")
            return None

        # Normalize the filename to prevent issues (e.g., redundant slashes)
        # os.path.basename might be too restrictive if we intend to allow subdirs within safe_dir later.
        # For now, only allow files directly in BASE_FILE_PATH.
        base_filename = os.path.basename(filename)
        if base_filename != filename: # Indicates path components were present
            logger.warning(f"[{self.name}] Filename '{filename}' contained path components. Using only basename: '{base_filename}'. Only files directly in the safe directory are allowed.")
            # To strictly disallow subdirectories, return None here if base_filename != filename
            # For now, we proceed with the basename, effectively flattening any path.

        # Construct the full path and normalize it
        full_path = os.path.normpath(os.path.join(BASE_FILE_PATH, base_filename))

        # Final check to ensure the path is still within the intended BASE_FILE_PATH
        if os.path.commonprefix([full_path, BASE_FILE_PATH]) != BASE_FILE_PATH:
            logger.error(f"[{self.name}] Path traversal attempt detected or resolved path is outside safe directory. Filename: '{filename}', Resolved: '{full_path}'")
            return None

        return full_path

    def execute(self, filename: str, max_bytes: Optional[int] = 4096) -> Dict[str, Any]:
        """
        Reads content from the specified file.

        Args:
            filename (str): The name of the file to read (must be within the safe directory).
            max_bytes (Optional[int]): Maximum number of bytes to read. Defaults to 4096.
                                       If None or <= 0, reads the whole file (use with caution).

        Returns:
            Dict[str, Any]: A dictionary with "result" (file content as string) and "status": "success",
                            or "error" message and "status": "error".
        """
        logger.info(f"[{self.name}] Attempting to read file: '{filename}', max_bytes: {max_bytes}")

        safe_filepath = self._get_safe_filepath(filename)
        if not safe_filepath:
            return {"error": f"Invalid or unsafe filename: '{filename}'. Reading is restricted to files within the designated agent directory.", "status": "error"}

        if not os.path.exists(safe_filepath):
            logger.warning(f"[{self.name}] File not found: {safe_filepath}")
            return {"error": f"File '{filename}' not found in the agent directory.", "status": "error"}

        if not os.path.isfile(safe_filepath):
            logger.warning(f"[{self.name}] Path is not a file: {safe_filepath}")
            return {"error": f"'{filename}' is not a file.", "status": "error"}

        try:
            with open(safe_filepath, 'r', encoding='utf-8') as f:
                if max_bytes is not None and max_bytes > 0:
                    content = f.read(max_bytes)
                    # Check if file was truncated
                    # Note: f.read(max_bytes + 1) would be more accurate but means reading more.
                    # A simple check if len(content) == max_bytes might indicate truncation if file is larger.
                    if len(content) == max_bytes:
                        # Attempt to read one more byte to see if there's more content
                        if f.read(1):
                            logger.info(f"[{self.name}] File '{filename}' content truncated to {max_bytes} bytes.")
                            # Optionally append a truncation indicator to content if desired by spec
                            # content += "\n[...truncated]"
                else: # Read whole file
                    content = f.read()

            logger.info(f"[{self.name}] Successfully read {len(content)} bytes from '{filename}'.")
            return {"result": content, "status": "success"}
        except UnicodeDecodeError as e:
            logger.error(f"[{self.name}] Failed to decode file '{filename}' as UTF-8: {e}", exc_info=True)
            return {"error": f"File '{filename}' is likely not a UTF-8 encoded text file or is corrupted.", "status": "error"}
        except IOError as e:
            logger.error(f"[{self.name}] IOError reading file '{filename}': {e}", exc_info=True)
            return {"error": f"Could not read file '{filename}': {e}", "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error reading file '{filename}': {e}", exc_info=True)
            return {"error": f"An unexpected error occurred while reading '{filename}'.", "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The name of the file to read from the agent's sandboxed directory."
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Optional. Maximum number of bytes to read. Defaults to 4096. Set to 0 or negative for no limit (reads entire file).",
                        "default": 4096
                    }
                },
                "required": ["filename"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')
    tool = ReadFileTool()

    # Create a dummy file for testing in the safe directory
    test_filename = "test_read.txt"
    test_filepath = os.path.join(BASE_FILE_PATH, test_filename)

    print(f"Base file path for tool: {BASE_FILE_PATH}")
    if not os.path.exists(BASE_FILE_PATH):
        os.makedirs(BASE_FILE_PATH, exist_ok=True)
        print(f"Created directory: {BASE_FILE_PATH}")

    with open(test_filepath, "w", encoding="utf-8") as f:
        f.write("This is line 1.\nThis is line 2.\nThis is a much longer third line to test truncation if necessary.")
    print(f"Created test file: {test_filepath}")

    print("\nSchema:", tool.get_schema())

    print("\n--- Test Cases ---")
    print("1. Read existing file (default max_bytes):")
    print(tool.execute(filename=test_filename))

    print("\n2. Read existing file (small max_bytes=10):")
    print(tool.execute(filename=test_filename, max_bytes=10))

    print("\n3. Read existing file (max_bytes covers partial line):")
    print(tool.execute(filename=test_filename, max_bytes=20))

    print("\n4. Read existing file (no limit, max_bytes=0):")
    print(tool.execute(filename=test_filename, max_bytes=0))

    print("\n5. Read non-existent file:")
    print(tool.execute(filename="non_existent.txt"))

    print("\n6. Attempt directory traversal (should fail):")
    print(tool.execute(filename="../secrets.txt"))
    print(tool.execute(filename="/etc/passwd"))
    print(tool.execute(filename="some_subdir/another_file.txt")) # This will also be treated as 'another_file.txt' in base due to basename usage

    # Clean up the dummy file
    if os.path.exists(test_filepath):
        os.remove(test_filepath)
        print(f"\nCleaned up test file: {test_filepath}")

    # Attempt to remove BASE_FILE_PATH if it's empty and was created by this script
    # This is a bit simplistic; a real cleanup might check if it was created by *this run*
    if os.path.exists(BASE_FILE_PATH) and not os.listdir(BASE_FILE_PATH):
        try:
            os.rmdir(BASE_FILE_PATH)
            print(f"Cleaned up directory: {BASE_FILE_PATH}")
        except OSError:
            print(f"Could not remove directory (possibly not empty or permissions issue): {BASE_FILE_PATH}")

