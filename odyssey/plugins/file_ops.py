# File handler plugin
import os
import shutil
import json

class FileOpsTool:
    def __init__(self, base_directory=None):
        """
        Initializes the File Operations tool.
        - base_directory: A base path to restrict operations. If None, uses current working directory,
                          but caution is advised. For agent use, a sandboxed/restricted dir is best.
        """
        if base_directory:
            self.base_directory = os.path.abspath(base_directory)
            if not os.path.exists(self.base_directory):
                os.makedirs(self.base_directory, exist_ok=True)
                print(f"FileOpsTool: Created base directory '{self.base_directory}'")
        else:
            # Using CWD as base if no directory is specified.
            # WARNING: This can be risky if the agent has broad permissions.
            # Consider restricting this to a specific agent workspace.
            self.base_directory = os.getcwd()
        print(f"FileOpsTool initialized. Base directory: '{self.base_directory}'")

    def _resolve_path(self, path: str) -> str:
        """Resolves a relative path against the base_directory and ensures it's within."""
        # Normalize to prevent path traversal tricks like '..' leading outside base_directory
        abs_path = os.path.abspath(os.path.join(self.base_directory, path))
        if os.path.commonpath([abs_path, self.base_directory]) != self.base_directory:
            raise ValueError(f"Path '{path}' is outside the allowed base directory '{self.base_directory}'.")
        return abs_path

    def read_file(self, path: str) -> str:
        """Reads the content of a file."""
        try:
            filepath = self._resolve_path(path)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            return f"Error: File not found at '{path}'."
        except ValueError as e: # From _resolve_path
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file '{path}': {e}"

    def write_file(self, path: str, content: str, overwrite: bool = False) -> str:
        """Writes content to a file. Creates directories if they don't exist."""
        try:
            filepath = self._resolve_path(path)
            if os.path.exists(filepath) and not overwrite:
                return f"Error: File '{path}' already exists. Set overwrite=True to replace."

            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"File '{path}' written successfully."
        except ValueError as e: # From _resolve_path
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file '{path}': {e}"

    def delete_file(self, path: str) -> str:
        """Deletes a file."""
        try:
            filepath = self._resolve_path(path)
            if not os.path.isfile(filepath):
                return f"Error: Not a file or file not found at '{path}'."
            os.remove(filepath)
            return f"File '{path}' deleted successfully."
        except ValueError as e: # From _resolve_path
            return f"Error: {e}"
        except Exception as e:
            return f"Error deleting file '{path}': {e}"

    def list_directory(self, path: str = ".") -> list:
        """Lists files and directories within a given path relative to base_directory."""
        try:
            dirpath = self._resolve_path(path)
            if not os.path.isdir(dirpath):
                return [f"Error: Directory not found or not a directory at '{path}'."]

            items = []
            for item in os.listdir(dirpath):
                item_path = os.path.join(dirpath, item)
                item_type = "dir" if os.path.isdir(item_path) else "file"
                items.append({"name": item, "type": item_type, "path": os.path.join(path, item)})
            return items
        except ValueError as e: # From _resolve_path
            return [f"Error: {e}"]
        except Exception as e:
            return [f"Error listing directory '{path}': {e}"]

    def move_file(self, source_path: str, destination_path: str) -> str:
        """Moves or renames a file or directory."""
        try:
            source_fp = self._resolve_path(source_path)
            destination_fp = self._resolve_path(destination_path)

            if not os.path.exists(source_fp):
                return f"Error: Source '{source_path}' not found."

            os.makedirs(os.path.dirname(destination_fp), exist_ok=True)
            shutil.move(source_fp, destination_fp)
            return f"Moved '{source_path}' to '{destination_path}' successfully."
        except ValueError as e: # From _resolve_path
            return f"Error: {e}"
        except Exception as e:
            return f"Error moving '{source_path}' to '{destination_path}': {e}"

    def execute(self, action: str, params: dict):
        """Generic execute method for ToolManager."""
        if action == "read_file":
            return self.read_file(params.get("path"))
        elif action == "write_file":
            return self.write_file(params.get("path"), params.get("content", ""), params.get("overwrite", False))
        elif action == "delete_file":
            return self.delete_file(params.get("path"))
        elif action == "list_directory":
            return self.list_directory(params.get("path", "."))
        elif action == "move_file":
            return self.move_file(params.get("source_path"), params.get("destination_path"))
        else:
            return f"Error: Unknown action '{action}' for FileOpsTool."

if __name__ == '__main__':
    # Example usage with a dedicated 'agent_workspace' directory for safety
    workspace_dir = "agent_workspace_test"
    if os.path.exists(workspace_dir): # Clean up from previous runs
        shutil.rmtree(workspace_dir)

    file_ops = FileOpsTool(base_directory=workspace_dir)

    print("--- File Operations Test ---")

    # Write a file
    write_result = file_ops.execute("write_file", {"path": "test_doc.txt", "content": "Hello from FileOps!"})
    print(f"Write file: {write_result}")

    # Write another file in a subdirectory
    write_result_sub = file_ops.execute("write_file", {"path": "subdir/another_doc.txt", "content": "Subdirectory content."})
    print(f"Write file in subdir: {write_result_sub}")

    # List base directory
    list_base = file_ops.execute("list_directory", {}) # path defaults to "."
    print(f"List base directory ({workspace_dir}): {json.dumps(list_base, indent=2)}")

    # List subdirectory
    list_sub = file_ops.execute("list_directory", {"path": "subdir"})
    print(f"List subdir ('subdir'): {json.dumps(list_sub, indent=2)}")

    # Read the first file
    read_result = file_ops.execute("read_file", {"path": "test_doc.txt"})
    print(f"Read file 'test_doc.txt': {read_result}")

    # Attempt to read a non-existent file
    read_non_existent = file_ops.execute("read_file", {"path": "non_existent.txt"})
    print(f"Read non-existent file: {read_non_existent}")

    # Move the file
    move_result = file_ops.execute("move_file", {"source_path": "test_doc.txt", "destination_path": "renamed_test_doc.txt"})
    print(f"Move file: {move_result}")

    # List base directory again to see changes
    list_base_after_move = file_ops.execute("list_directory", {})
    print(f"List base directory after move: {json.dumps(list_base_after_move, indent=2)}")

    # Delete the renamed file
    delete_result = file_ops.execute("delete_file", {"path": "renamed_test_doc.txt"})
    print(f"Delete file: {delete_result}")

    # Delete the file in subdirectory
    delete_result_sub = file_ops.execute("delete_file", {"path": "subdir/another_doc.txt"})
    print(f"Delete file in subdir: {delete_result_sub}")

    # Attempt to access outside base_directory (should fail)
    print("\nAttempting path traversal (should be blocked):")
    # Create a file outside the workspace to test against
    with open("../outside_test.txt", "w") as f:
        f.write("This is outside.")

    # Try to read it
    # This path will be resolved from within workspace_dir, so ../../outside_test.txt
    # Or just directly try an absolute path if _resolve_path is robust
    # For this example, let's assume the agent tries a simple traversal
    # The exact path depends on where this script is run relative to the workspace_dir creation.
    # If script is in odyssey/plugins and workspace_dir is odyssey/plugins/agent_workspace_test
    # then "../../../outside_test.txt" would point from inside workspace to outside_test.txt
    # Let's assume the user of the tool provides a path like this:
    naughty_path_read = file_ops.execute("read_file", {"path": "../../outside_test.txt"})
    print(f"Read outside file: {naughty_path_read}")
    os.remove("../outside_test.txt") # Clean up the outside file

    # Clean up the test workspace
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    print(f"\nCleaned up test workspace: {workspace_dir}")
