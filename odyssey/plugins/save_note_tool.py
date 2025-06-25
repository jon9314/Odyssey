"""
SaveNoteTool for the Odyssey agent.
Allows saving a textual note, optionally with a tag, into the agent's structured memory.
This tool demonstrates dependency injection of the MemoryManager.
"""
import logging
from typing import Dict, Any, Optional
from odyssey.agent.tool_manager import ToolInterface
from odyssey.agent.memory import MemoryManager # For type hinting and usage

logger = logging.getLogger("odyssey.plugins.save_note_tool")

class SaveNoteTool(ToolInterface):
    """
    A tool to save a textual note into the agent's memory system.
    It can optionally include a tag for categorization or later retrieval.
    Requires MemoryManager to be injected.
    """
    name: str = "save_note"
    description: str = "Saves a textual note to the agent's memory. Can include an optional tag for categorization."

    def __init__(self, memory_manager: MemoryManager):
        """
        Initializes the SaveNoteTool with a MemoryManager instance.

        Args:
            memory_manager: An instance of the MemoryManager for storing notes.
        """
        super().__init__() # Sets up name, description from class attributes
        if not memory_manager:
            raise ValueError("MemoryManager instance is required for SaveNoteTool.")
        self.memory_manager = memory_manager
        logger.info(f"[{self.name}] Initialized with MemoryManager.")

    def execute(self, note: str, tag: Optional[str] = None) -> Dict[str, Any]:
        """
        Saves the provided note content to memory.

        Args:
            note (str): The textual content of the note to save.
            tag (Optional[str]): An optional tag to categorize the note.

        Returns:
            Dict[str, Any]: A dictionary with "result" (confirmation message including note ID)
                            and "status": "success", or "error" message and "status": "error".
        """
        if not note or not isinstance(note, str) or not note.strip():
            err_msg = "Note content cannot be empty."
            logger.warning(f"[{self.name}] Attempted to save empty note.")
            return {"error": err_msg, "status": "error"}

        logger.info(f"[{self.name}] Attempting to save note. Tag: '{tag if tag else 'None'}' Content snippet: '{note[:50]}...'")

        try:
            # We use MemoryManager's log_event method for simplicity, defining a specific 'event_type'.
            # A dedicated 'add_note' method in MemoryManager might be cleaner in the long run.
            content_payload = {"note_content": note}
            metadata_payload = {}
            if tag:
                content_payload["tag"] = tag # Include tag in content for easier querying if needed
                metadata_payload["tag"] = tag

            # Using 'agent_note' as a specific type for these memory entries
            note_id = self.memory_manager.log_event(
                message=f"Note: {note[:100]}{'...' if len(note) > 100 else ''}", # For the 'message' field in logs table
                level="NOTE", # Custom level for notes, or use INFO
                # source=self.name, # This is for the 'source' field in the generic logs table
                # For SaveNoteTool, we might want to use a more specific table if we had one,
                # or a specific 'event_type' if using the generic 'events' table.
                # The current MemoryManager spec has add_task, add_plan, log_event.
                # Let's use log_event and store the note in the message, tag in metadata.
            )
            # Re-evaluating based on current MemoryManager:
            # The `log_event` method in MemoryManager stores to a `logs` table with (message, level, timestamp).
            # This is not ideal for structured notes.
            # Let's assume we'll add a more generic `add_structured_data` or adapt `store_event` in MemoryManager later.
            # For now, as a placeholder that uses an existing MemoryManager method, we'll log it.
            # A better approach for the future would be:
            # note_id = self.memory_manager.add_note(content=note, tag=tag, category="agent_note")

            # Using log_event as a temporary measure.
            # This will store the note in the `logs` table.
            log_content = f"NOTE_CONTENT: {note}"
            if tag:
                log_content += f" TAG: {tag}"

            # For now, let's use a dedicated "NOTE" level for these entries in the logs table
            db_log_id = self.memory_manager.log_event(message=log_content, level="USER_NOTE")


            if db_log_id is not None:
                success_msg = f"Note saved successfully with ID {db_log_id}."
                if tag: success_msg += f" (Tag: '{tag}')"
                logger.info(f"[{self.name}] {success_msg}")
                return {"result": success_msg, "note_id": db_log_id, "status": "success"}
            else:
                err_msg = "Failed to save note to memory (database error)."
                logger.error(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error saving note: {e}", exc_info=True)
            return {"error": f"An unexpected error occurred while saving the note: {str(e)}", "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "The textual content of the note to be saved."
                    },
                    "tag": {
                        "type": "string",
                        "description": "An optional tag to categorize or group the note."
                    }
                },
                "required": ["note"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock MemoryManager for testing this tool standalone
    class MockMemoryManager:
        def __init__(self):
            self.log_id_counter = 0
            self.notes_log = []
        def log_event(self, message: str, level: str = "INFO") -> Optional[int]:
            self.log_id_counter += 1
            entry = {"id": self.log_id_counter, "message": message, "level": level, "timestamp": datetime.datetime.utcnow().isoformat()}
            self.notes_log.append(entry)
            logger.info(f"[MockMemoryManager] Logged event: {entry}")
            return self.log_id_counter
        def query(self, q_str, limit=10, event_type_filter=None, source_filter=None): # Placeholder
            return []

    mock_memory = MockMemoryManager()
    tool = SaveNoteTool(memory_manager=mock_memory)

    print("Schema:", tool.get_schema())

    print("\n--- Test Cases ---")
    print("1. Save a simple note:")
    res1 = tool.execute(note="Remember to buy milk.")
    print(res1)

    print("\n2. Save a note with a tag:")
    res2 = tool.execute(note="Project Alpha kickoff meeting notes: Key decisions...", tag="project_alpha")
    print(res2)

    print("\n3. Attempt to save an empty note (should fail):")
    res3 = tool.execute(note=" ")
    print(res3)

    print("\n4. Attempt to save a note with None content (should fail):")
    try:
        res4 = tool.execute(note=None) # type: ignore
        print(res4)
    except Exception as e: # Pydantic validation might catch this earlier if used in an API
        print(f"Error with None note: {e}")


    print("\nMock Memory Manager Log Contents:")
    for logged_note in mock_memory.notes_log:
        print(logged_note)
```
