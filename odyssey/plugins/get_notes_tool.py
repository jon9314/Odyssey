"""
GetNotesTool for the Odyssey agent.
Retrieves saved notes from the agent's structured memory, optionally filtered by tag or date.
This tool demonstrates dependency injection of the MemoryManager.
"""
import logging
from typing import Dict, Any, Optional, List
import datetime
from odyssey.agent.tool_manager import ToolInterface
from odyssey.agent.memory import MemoryManager # For type hinting and usage

logger = logging.getLogger("odyssey.plugins.get_notes_tool")

class GetNotesTool(ToolInterface):
    """
    A tool to retrieve notes previously saved in the agent's memory.
    Notes can be filtered by a specific tag and/or retrieved if saved since a given date/time.
    Requires MemoryManager to be injected.
    """
    name: str = "get_notes"
    description: str = "Retrieves saved notes from the agent's memory. Can filter by tag and/or a 'since' timestamp."

    def __init__(self, memory_manager: MemoryManager):
        """
        Initializes the GetNotesTool with a MemoryManager instance.

        Args:
            memory_manager: An instance of the MemoryManager for retrieving notes.
        """
        super().__init__()
        if not memory_manager:
            raise ValueError("MemoryManager instance is required for GetNotesTool.")
        self.memory_manager = memory_manager
        logger.info(f"[{self.name}] Initialized with MemoryManager.")

    def execute(self, tag: Optional[str] = None, since: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """
        Retrieves notes from memory, applying optional filters.

        Args:
            tag (Optional[str]): If provided, only retrieve notes with this tag.
            since (Optional[str]): If provided, an ISO 8601 formatted date/time string.
                                   Only retrieve notes created at or after this time.
            limit (int): Maximum number of notes to return. Defaults to 20.


        Returns:
            Dict[str, Any]: A dictionary with "result" (a list of found notes)
                            and "status": "success", or "error" message and "status": "error".
                            Each note in the list is a dictionary.
        """
        log_message = f"[{self.name}] execute called."
        if tag: log_message += f" tag='{tag}'"
        if since: log_message += f" since='{since}'"
        log_message += f" limit={limit}"
        logger.info(log_message)

        since_dt: Optional[datetime.datetime] = None
        if since:
            try:
                since_dt = datetime.datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                err_msg = "Invalid 'since' date/time format. Please use ISO 8601 format (e.g., YYYY-MM-DDTHH:MM:SSZ)."
                logger.warning(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}

        try:
            # We are using the 'logs' table with a specific level 'USER_NOTE' for notes.
            # The MemoryManager's get_logs method can filter by level.
            # Tag filtering will need to be done on the 'message' content post-retrieval for now.
            # Timestamp filtering also needs to be post-retrieval based on current MemoryManager.get_logs.

            # A more ideal MemoryManager would have:
            # get_notes(tag: Optional[str], since: Optional[datetime], limit: int)

            # Current approach: Fetch all 'USER_NOTE' logs and then filter.
            all_user_notes_raw = self.memory_manager.get_logs(level_filter="USER_NOTE", limit=limit * 5) # Fetch more to filter

            filtered_notes = []
            for raw_note_entry in all_user_notes_raw:
                # Expected format from SaveNoteTool's log_event: "NOTE_CONTENT: ... TAG: ..."
                message_content = raw_note_entry.get("message", "")

                # Filter by tag
                if tag:
                    if not f"TAG: {tag}" in message_content: # Simple string match for tag
                        continue

                # Filter by timestamp
                if since_dt:
                    try:
                        entry_timestamp_dt = datetime.datetime.fromisoformat(raw_note_entry.get("timestamp","").replace("Z", "+00:00"))
                        # Ensure both are offset-aware for comparison or convert both to naive UTC
                        if entry_timestamp_dt.tzinfo is None: # if naive, assume UTC
                             entry_timestamp_dt = entry_timestamp_dt.replace(tzinfo=datetime.timezone.utc)
                        if since_dt.tzinfo is None:
                             since_dt = since_dt.replace(tzinfo=datetime.timezone.utc)

                        if entry_timestamp_dt < since_dt:
                            continue
                    except ValueError:
                        logger.warning(f"[{self.name}] Could not parse timestamp for note ID {raw_note_entry.get('id')}. Skipping for 'since' filter.")
                        continue

                # Reconstruct the note for the result
                # This is a bit hacky due to storing notes in the generic log message.
                # A dedicated notes table would be much cleaner.
                note_text = message_content
                extracted_tag = None
                if "TAG: " in message_content:
                    parts = message_content.split("TAG: ", 1)
                    note_text = parts[0].replace("NOTE_CONTENT: ", "").strip()
                    if len(parts) > 1:
                        extracted_tag = parts[1].strip()
                else:
                    note_text = note_text.replace("NOTE_CONTENT: ", "").strip()

                reconstructed_note = {
                    "id": raw_note_entry.get("id"),
                    "note": note_text,
                    "tag": extracted_tag,
                    "timestamp": raw_note_entry.get("timestamp")
                }
                filtered_notes.append(reconstructed_note)
                if len(filtered_notes) >= limit:
                    break

            logger.info(f"[{self.name}] Retrieved {len(filtered_notes)} notes matching criteria.")
            return {"result": filtered_notes, "status": "success"}

        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error retrieving notes: {e}", exc_info=True)
            return {"error": f"An unexpected error occurred while retrieving notes: {str(e)}", "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Optional. Filter notes by this specific tag."
                    },
                    "since": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Optional. Retrieve notes created at or after this ISO 8601 timestamp (e.g., '2023-01-15T10:00:00Z')."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional. Maximum number of notes to return.",
                        "default": 20
                    }
                },
                "required": []
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock MemoryManager for testing
    class MockMemoryManagerForGet:
        def __init__(self):
            self.notes_log_db = [] # Simulates the 'logs' table
            self.id_counter = 0

        def log_event(self, message: str, level: str) -> int: # For SaveNoteTool to populate
            self.id_counter +=1
            entry = {
                "id": self.id_counter,
                "message": message,
                "level": level.upper(),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
            }
            self.notes_log_db.append(entry)
            return self.id_counter

        def get_logs(self, level_filter: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
            # This mock directly returns what would be in the 'logs' table for 'USER_NOTE'
            if level_filter == "USER_NOTE":
                return [log for log in self.notes_log_db if log["level"] == "USER_NOTE"][:limit]
            return []

    mock_memory = MockMemoryManagerForGet()

    # Populate with some notes using a mock SaveNoteTool logic for this test
    # (or directly populate mock_memory.notes_log_db)
    mock_memory.log_event(message="NOTE_CONTENT: Meeting agenda for Monday TAG: work", level="USER_NOTE")
    time.sleep(0.01) # ensure slight timestamp difference
    mock_memory.log_event(message="NOTE_CONTENT: Grocery list: milk, eggs, bread", level="USER_NOTE")
    time.sleep(0.01)
    since_timestamp_obj = datetime.datetime.utcnow()
    time.sleep(0.01)
    mock_memory.log_event(message="NOTE_CONTENT: Ideas for weekend trip TAG: personal", level="USER_NOTE")
    time.sleep(0.01)
    mock_memory.log_event(message="NOTE_CONTENT: Follow up with John Doe TAG: work", level="USER_NOTE")

    tool = GetNotesTool(memory_manager=mock_memory)

    print("Schema:", tool.get_schema())

    print("\n--- Test Cases ---")
    print("1. Get all notes (default limit):")
    res1 = tool.execute()
    print(res1)

    print("\n2. Get notes with tag 'work':")
    res2 = tool.execute(tag="work")
    print(res2)
    if res2['status'] == 'success':
      assert all("work" in (n.get('tag') or '') for n in res2['result'])

    print("\n3. Get notes with tag 'personal':")
    res3 = tool.execute(tag="personal")
    print(res3)
    if res3['status'] == 'success':
      assert all("personal" in (n.get('tag') or '') for n in res3['result'])

    print(f"\n4. Get notes since {since_timestamp_obj.isoformat()}Z:")
    res4 = tool.execute(since=since_timestamp_obj.isoformat() + "Z")
    print(res4)
    # Verification for 'since' is more complex with mock data unless timestamps are precise.

    print("\n5. Get notes with tag 'nonexistent':")
    res5 = tool.execute(tag="nonexistent")
    print(res5)
    if res5['status'] == 'success':
      assert len(res5['result']) == 0

    print("\n6. Get notes with invalid 'since' format:")
    res6 = tool.execute(since="not-a-date")
    print(res6)
    assert res6['status'] == 'error'
```
