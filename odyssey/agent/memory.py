"""
Manages the agent's memory, including structured (SQLite), semantic (vector store placeholder),
and backup (JSON placeholder) functionalities. Also includes stubs for Langfuse observability.
"""
import sqlite3
import json
import os
import datetime
import logging
from typing import List, Dict, Any, Optional

# Placeholder for ChromaDB/FAISS client and Langfuse client
# These would be imported if the actual libraries are used.
# from chromadb import Client as ChromaClient # Example
# from faiss import IndexFlatL2 # Example
# from sentence_transformers import SentenceTransformer # Example for embeddings
# from langfuse import Langfuse # Example

# Import the new vector store components
from .vector_store import ChromaVectorStore, VectorStoreInterface # Added VectorStoreInterface

logger = logging.getLogger(__name__)

# Default paths (can be overridden by config)
DEFAULT_DB_PATH = "var/memory/structured_memory.db"
DEFAULT_VECTOR_STORE_PERSIST_PATH = "var/memory/vector_store_chroma" # Specific for Chroma persistence
DEFAULT_VECTOR_STORE_COLLECTION = "odyssey_semantic_collection" # Renamed for clarity
DEFAULT_JSON_BACKUP_PATH = "var/memory/backup/"
DEFAULT_EMBEDDING_MODEL = 'all-MiniLM-L6-v2' # For Chroma's SentenceTransformer

class MemoryManager:
    def __init__(self,
                 db_path: str = DEFAULT_DB_PATH,
                 vector_store_persist_path: str = DEFAULT_VECTOR_STORE_PERSIST_PATH,
                 vector_store_collection_name: str = DEFAULT_VECTOR_STORE_COLLECTION,
                 json_backup_path: str = DEFAULT_JSON_BACKUP_PATH,
                 embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
                 langfuse_client=None):
        """
        Initializes the MemoryManager.
        :param db_path: Path to the SQLite database file.
        :param vector_store_persist_path: Path for ChromaDB persistent storage.
        :param vector_store_collection_name: Name of the ChromaDB collection.
        :param json_backup_path: Directory for JSON backups.
        :param embedding_model_name: Name of the sentence transformer model for embeddings.
        :param langfuse_client: Optional initialized Langfuse client for observability.
        """
        self.db_path = db_path
        # vector_store_path is now vector_store_persist_path for clarity
        self.json_backup_path = json_backup_path
        # embedding_model_name is used by ChromaVectorStore

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # ChromaVectorStore will create its persist_directory if it doesn't exist.
        os.makedirs(self.json_backup_path, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row # Access columns by name
        self._create_tables()

        # --- Vector Store Initialization ---
        self.vector_store: Optional[VectorStoreInterface] = None # Use the interface type hint
        try:
            logger.info(f"Initializing ChromaVectorStore: collection='{vector_store_collection_name}', persist_path='{vector_store_persist_path}', model='{embedding_model_name}'")
            self.vector_store = ChromaVectorStore(
                collection_name=vector_store_collection_name,
                persist_directory=vector_store_persist_path,
                embedding_model_name=embedding_model_name
            )
            logger.info(f"ChromaVectorStore initialized successfully. Current collection count: {self.vector_store.get_collection_count()}")
        except ImportError: # Catch if chromadb or sentence_transformers are missing
            logger.warning("ChromaDB or SentenceTransformers library not found. Semantic memory features will be unavailable.")
            self.vector_store = None # Explicitly set to None
        except Exception as e: # Catch other ChromaDB initialization errors
            logger.error(f"Failed to initialize ChromaVectorStore: {e}", exc_info=True)
            self.vector_store = None # Explicitly set to None

        # --- Langfuse Client ---
        self.langfuse = langfuse_client
        if self.langfuse:
            logger.info("Langfuse client provided and configured.")
        else:
            logger.info("Langfuse client not provided; observability will be limited.")

        logger.info(f"MemoryManager initialized. SQLite DB: {self.db_path}, Vector Store: {self.vector_store_path}, JSON Backup: {self.json_backup_path}")

    def _create_tables(self):
        """Creates necessary SQLite tables if they don't exist."""
        with self.conn:
            # Tasks table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', -- e.g., pending, in_progress, completed, failed
                    timestamp TEXT NOT NULL
                )
            """)
            # Plans table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    details TEXT NOT NULL, -- Could be JSON for complex plans
                    timestamp TEXT NOT NULL
                )
            """)
            # Logs table (for general agent logging, distinct from FastAPI/Uvicorn logs)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'INFO', -- e.g., INFO, WARNING, ERROR, DEBUG
                    timestamp TEXT NOT NULL
                )
            """)
            # Self Modification Log table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS self_modification_log (
                    proposal_id TEXT PRIMARY KEY,
                    branch_name TEXT NOT NULL,
                    commit_message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    validation_output TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_by TEXT
                )
            """)
        logger.info("SQLite tables (tasks, plans, logs, self_modification_log) checked/created.")

    # --- Task Management Methods ---
    def add_task(self, description: str) -> Optional[int]:
        """Adds a new task to the database."""
        timestamp = datetime.datetime.utcnow().isoformat()
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO tasks (description, status, timestamp) VALUES (?, ?, ?)",
                    (description, 'pending', timestamp)
                )
                task_id = cursor.lastrowid
                logger.info(f"Task added with ID: {task_id}, Description: '{description}'")
                self.log_to_langfuse({"event_type": "add_task", "task_id": task_id, "description": description})
                return task_id
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding task: {e}")
            return None

    def get_tasks(self, status_filter: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves tasks, optionally filtered by status."""
        try:
            query = "SELECT id, description, status, timestamp FROM tasks"
            params = []
            if status_filter:
                query += " WHERE status = ?"
                params.append(status_filter)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = self.conn.execute(query, tuple(params))
            tasks = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Retrieved {len(tasks)} tasks.")
            return tasks
        except sqlite3.Error as e:
            logger.error(f"SQLite error getting tasks: {e}")
            return []

    def update_task_status(self, task_id: int, status: str) -> bool:
        """Updates the status of a specific task."""
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "UPDATE tasks SET status = ? WHERE id = ?",
                    (status, task_id)
                )
                if cursor.rowcount > 0:
                    logger.info(f"Task ID {task_id} status updated to '{status}'.")
                    self.log_to_langfuse({"event_type": "update_task_status", "task_id": task_id, "status": status})
                    return True
                else:
                    logger.warning(f"Task ID {task_id} not found for status update.")
                    return False
        except sqlite3.Error as e:
            logger.error(f"SQLite error updating task status for ID {task_id}: {e}")
            return False

    # --- Plan Management Methods (basic stubs) ---
    def add_plan(self, details: str) -> Optional[int]:
        """Adds a new plan to the database."""
        timestamp = datetime.datetime.utcnow().isoformat()
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO plans (details, timestamp) VALUES (?, ?)",
                    (details, timestamp)
                )
                plan_id = cursor.lastrowid
                logger.info(f"Plan added with ID: {plan_id}")
                self.log_to_langfuse({"event_type": "add_plan", "plan_id": plan_id, "details_preview": details[:100]})
                return plan_id
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding plan: {e}")
            return None

    def get_plans(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves plans."""
        try:
            cursor = self.conn.execute("SELECT id, details, timestamp FROM plans ORDER BY timestamp DESC LIMIT ?", (limit,))
            plans = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Retrieved {len(plans)} plans.")
            return plans
        except sqlite3.Error as e:
            logger.error(f"SQLite error getting plans: {e}")
            return []

    # --- Logging Methods ---
    def log_event(self, message: str, level: str = "INFO") -> Optional[int]:
        """Logs a message to the database's logs table."""
        timestamp = datetime.datetime.utcnow().isoformat()
        # Basic validation for level
        allowed_levels = ["INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"]
        if level.upper() not in allowed_levels:
            logger.warning(f"Invalid log level '{level}'. Defaulting to INFO.")
            level = "INFO"
        else:
            level = level.upper()

        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO logs (message, level, timestamp) VALUES (?, ?, ?)",
                    (message, level, timestamp)
                )
                log_id = cursor.lastrowid
                # Avoid recursive logging if this method itself is logged by the main logger
                # For this specific DB log, we might not want to log to stdout via logger.info
                # print(f"DB Log [{level}]: {message} (ID: {log_id})") # Or use a specific DB logger
                self.log_to_langfuse({"event_type": "agent_log", "level": level, "message": message})
                return log_id
        except sqlite3.Error as e:
            logger.error(f"SQLite error logging event: {e}")
            return None

    def get_logs(self, level_filter: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves log messages, optionally filtered by level."""
        try:
            query = "SELECT id, message, level, timestamp FROM logs"
            params = []
            if level_filter:
                query += " WHERE level = ?"
                params.append(level_filter.upper())
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = self.conn.execute(query, tuple(params))
            logs = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Retrieved {len(logs)} log entries from DB.")
            return logs
        except sqlite3.Error as e:
            logger.error(f"SQLite error getting logs: {e}")
            return []

    # --- Self Modification Log Methods ---
    def log_proposal_step(self, proposal_id: str, branch_name: str, commit_message: str,
                          status: str, validation_output: Optional[str] = None,
                          approved_by: Optional[str] = None) -> bool:
        """
        Logs or updates a step in the self-modification proposal lifecycle.
        Uses UPSERT to handle new proposals or update existing ones.

        :param proposal_id: Unique identifier for the proposal.
        :param branch_name: Git branch name associated with the proposal.
        :param commit_message: Commit message for the proposed change.
        :param status: Current status of the proposal (e.g., "proposed", "validation_pending").
        :param validation_output: Output from validation tests (nullable).
        :param approved_by: Identifier of the user/entity that approved the proposal (nullable).
        :return: True if the operation was successful, False otherwise.
        """
        now_timestamp = datetime.datetime.utcnow().isoformat()
        try:
            with self.conn:
                self.conn.execute("""
                    INSERT INTO self_modification_log (
                        proposal_id, branch_name, commit_message, status,
                        validation_output, created_at, updated_at, approved_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(proposal_id) DO UPDATE SET
                        branch_name = excluded.branch_name,
                        commit_message = excluded.commit_message,
                        status = excluded.status,
                        validation_output = excluded.validation_output,
                        updated_at = excluded.updated_at,
                        approved_by = excluded.approved_by
                """, (proposal_id, branch_name, commit_message, status,
                      validation_output, now_timestamp, now_timestamp, approved_by))
            logger.info(f"Proposal step logged for ID '{proposal_id}'. Status: {status}, Updated_at: {now_timestamp}")
            # Log to Langfuse (if integrated)
            self.log_to_langfuse({
                "event_type": "log_proposal_step", "proposal_id": proposal_id, "status": status,
                "branch_name": branch_name, "commit_message": commit_message
            })
            return True
        except sqlite3.Error as e:
            logger.error(f"SQLite error logging proposal step for ID '{proposal_id}': {e}")
            return False

    def get_proposal_log(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current log/status for a given proposal_id.

        :param proposal_id: The unique identifier of the proposal to retrieve.
        :return: A dictionary containing the proposal details if found, otherwise None.
        """
        try:
            cursor = self.conn.execute(
                "SELECT * FROM self_modification_log WHERE proposal_id = ?",
                (proposal_id,)
            )
            row = cursor.fetchone()
            if row:
                logger.debug(f"Retrieved proposal log for ID '{proposal_id}'.")
                return dict(row)
            else:
                logger.info(f"No proposal log found for ID '{proposal_id}'.")
                return None
        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving proposal log for ID '{proposal_id}': {e}")
            return None

    def list_proposals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Lists all self-modification proposals and their current status, ordered by the last update.

        :param limit: Maximum number of proposals to return.
        :return: A list of dictionaries, where each dictionary represents a proposal.
        """
        try:
            cursor = self.conn.execute(
                "SELECT * FROM self_modification_log ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            )
            proposals = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Retrieved {len(proposals)} proposals.")
            return proposals
        except sqlite3.Error as e:
            logger.error(f"SQLite error listing proposals: {e}")
            return []

    # --- Semantic Memory Methods ---
    def add_semantic_memory_event(self, text: str, metadata: dict, event_id: Optional[str] = None) -> Optional[str]:
        """
        Adds a text event and its metadata to the semantic vector store.

        :param text: The text content of the event.
        :param metadata: A dictionary of metadata associated with the text.
        :param event_id: Optional unique ID for this event. If None, one will be generated.
        :return: The ID of the added event, or None if an error occurred or vector store is unavailable.
        """
        if not self.vector_store:
            logger.warning("Vector store not available. Cannot add semantic memory event.")
            return None

        doc_id = event_id or str(datetime.datetime.utcnow().timestamp()) + "_" + os.urandom(4).hex() # More unique default ID
        document = {"text": text, "metadata": metadata, "id": doc_id}

        try:
            added_ids = self.vector_store.add_documents([document])
            if added_ids and added_ids[0] == doc_id:
                logger.info(f"Semantic memory event added with ID: {doc_id}. Text snippet: '{text[:100]}...'")
                self.log_to_langfuse({"event_type": "add_semantic_event", "doc_id": doc_id, "text_preview": text[:100], "metadata": metadata})
                return doc_id
            else:
                logger.error(f"Failed to add semantic memory event. ID mismatch or no ID returned. Expected {doc_id}, got {added_ids}")
                return None
        except Exception as e:
            logger.error(f"Error adding semantic memory event (ID: {doc_id}): {e}", exc_info=True)
            return None

    def semantic_search(self, query_text: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Performs semantic search using the configured vector store.

        :param query_text: The text to search for.
        :param top_k: Number of top results to return.
        :param metadata_filter: Optional filter for metadata (passed to vector store's `where` clause).
        :return: A list of search result dictionaries, including text, metadata, id, and distance.
                 Returns an empty list if vector store is unavailable or an error occurs.
        """
        if not self.vector_store:
            logger.warning("Vector store not available. Cannot perform semantic search.")
            return [{"error": "Semantic search not available / Vector store not initialized."}] # Return error structure

        logger.info(f"Performing semantic search for: '{query_text[:100]}...', top_k: {top_k}, filter: {metadata_filter}")
        try:
            results = self.vector_store.query_similar_documents(
                query_text=query_text,
                top_k=top_k,
                metadata_filter=metadata_filter
            )
            # Log to Langfuse (if integrated) - consider what to log (query, num_results, maybe top result IDs)
            self.log_to_langfuse({"event_type": "semantic_search", "query": query_text, "top_k": top_k, "num_results": len(results)})
            return results
        except Exception as e:
            logger.error(f"Error during semantic search: {e}", exc_info=True)
            return [{"error": f"Error during semantic search: {str(e)}"}]


    # --- Stubs for Future Features --- (semantic_search was here, now implemented above)
    # The old semantic_search stub needs to be removed or this new one replaces it.
    # Assuming this new one replaces it.

    def backup_json(self) -> None:
        """
        (STUB) Backs up critical memory components to JSON files.
        """
        logger.info("(STUB) Backup to JSON called.")
        logger.warning("Backup to JSON not implemented yet.")
        # TODO: Implement backup of SQLite tables (tasks, plans, logs) to JSON files.
        # Consider which tables are critical for backup.

    def log_to_langfuse(self, event: dict) -> None:
        """
        (STUB) Logs an event to Langfuse for observability.
        :param event: A dictionary representing the event to log.
        """
        # In a real implementation, this would use the self.langfuse client.
        # Example: self.langfuse.trace(...) or self.langfuse.event(...)
        logger.info(f"(STUB) Langfuse log event: {json.dumps(event)}")
        # TODO: Implement actual Langfuse logging using the self.langfuse client.
        # Ensure the event structure is compatible with Langfuse's expectations.
        if self.langfuse:
            # self.langfuse.event(name=event.get("event_type", "generic_agent_event"), input=event) # Example
            pass


    def close(self):
        """Closes the SQLite connection."""
        if self.conn:
            self.conn.close()
            logger.info("SQLite connection closed.")

    def __del__(self):
        self.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # --- Example Usage ---
    # Create a mock Langfuse client for the example
    class MockLangfuse:
        def event(self, name, input, metadata, **kwargs):
            logger.info(f"[MockLangfuse] Event: {name}, Input: {str(input)[:50]}..., Meta: {metadata}")
        def trace(self, *args, **kwargs): # Add trace method for context manager
            return self # Return self to act as a context manager
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): pass


    # Define paths for this example run (will create files in the script's directory)
    # For testing, use a temporary directory or ensure cleanup.
    # Using 'var/test_memory/' which should be gitignored if var/ is.
    test_base_dir = "var/test_memory"
    example_db_path = os.path.join(test_base_dir, "example_memory.db")
    # example_vector_path is now example_vector_persist_path
    example_vector_persist_path = os.path.join(test_base_dir, "example_vector_store_chroma") # Updated path
    example_backup_path = os.path.join(test_base_dir, "example_json_backups")

    # Clean up previous example run files if they exist
    if os.path.exists(test_base_dir):
        import shutil
        shutil.rmtree(test_base_dir)
    os.makedirs(test_base_dir, exist_ok=True)


    mock_lf_client = MockLangfuse()
    memory = MemoryManager(
        db_path=example_db_path,
        vector_store_persist_path=example_vector_persist_path, # Updated parameter name
        # vector_store_collection_name can use default
        json_backup_path=example_backup_path,
        # embedding_model_name can use default
        langfuse_client=mock_lf_client
    )

    print("\n--- Task Management ---")
    task_id1 = memory.add_task("Develop a new feature for image processing.")
    task_id2 = memory.add_task("Write documentation for the API.")
    memory.add_task("Fix bug #123 in the UI.")

    if task_id1: memory.update_task_status(task_id1, "in_progress")
    if task_id2: memory.update_task_status(task_id2, "completed")

    all_tasks = memory.get_tasks()
    print(f"All tasks ({len(all_tasks)} found):")
    for task in all_tasks:
        print(f"  ID: {task['id']}, Status: {task['status']}, Desc: {task['description']}, Time: {task['timestamp']}")

    pending_tasks = memory.get_tasks(status_filter="pending")
    print(f"\nPending tasks ({len(pending_tasks)} found):")
    for task in pending_tasks:
        print(f"  ID: {task['id']}, Desc: {task['description']}")

    print("\n--- Plan Management ---")
    plan_id1 = memory.add_plan("Initial plan: 1. Define schema, 2. Implement API, 3. Write tests.")
    plan_id2 = memory.add_plan("Refined plan for feature X: ...")
    all_plans = memory.get_plans()
    print(f"All plans ({len(all_plans)} found):")
    for plan in all_plans:
        print(f"  ID: {plan['id']}, Details: {plan['details'][:60]}..., Time: {plan['timestamp']}")


    print("\n--- Logging Events ---")
    log_id1 = memory.log_event("User 'admin' logged in.", level="INFO")
    log_id2 = memory.log_event("Failed to connect to external service XYZ.", level="ERROR")
    memory.log_event("Data processing started.", level="DEBUG") # DEBUG will be stored as DEBUG
    memory.log_event("Invalid input received for API /abc", level="warning") # will be stored as WARNING

    all_logs = memory.get_logs(limit=10)
    print(f"All logs ({len(all_logs)} found, showing last 10):")
    for log_entry in all_logs:
        print(f"  ID: {log_entry['id']}, Level: {log_entry['level']}, Msg: {log_entry['message']}, Time: {log_entry['timestamp']}")

    error_logs = memory.get_logs(level_filter="ERROR")
    print(f"\nError logs ({len(error_logs)} found):")
    for log_entry in error_logs:
        print(f"  ID: {log_entry['id']}, Msg: {log_entry['message']}")

    print("\n--- Semantic Memory ---")
    if memory.vector_store: # Check if vector_store was initialized
        event1_id = memory.add_semantic_memory_event(
            text="The agent successfully completed task #42 regarding data processing.",
            metadata={"type": "agent_action", "task_id": "42", "status": "success"}
        )
        memory.add_semantic_memory_event(
            text="A critical error occurred in the billing module during an update.",
            metadata={"type": "system_error", "module": "billing", "severity": "critical"},
            event_id="error_billing_001" # Provide custom ID
        )
        memory.add_semantic_memory_event(
            text="User 'john_doe' initiated a new project planning session.",
            metadata={"type": "user_activity", "user": "john_doe", "activity": "planning"}
        )

        print(f"Current semantic memory count: {memory.vector_store.get_collection_count()}")

        search_query = "information about data processing tasks"
        print(f"\nSemantic search for: '{search_query}'")
        semantic_results = memory.semantic_search(search_query, top_k=2)
        if semantic_results and "error" not in semantic_results[0]:
            for res in semantic_results:
                print(f"  ID: {res.get('id')}, Dist: {res.get('distance', -1):.4f}, Text: '{res.get('text', '')[:60]}...', Meta: {res.get('metadata')}")
        else:
            print(f"  Semantic search returned: {semantic_results}")

        search_query_filtered = "billing problems"
        print(f"\nSemantic search for: '{search_query_filtered}' with filter {{'severity': 'critical'}}")
        semantic_results_filtered = memory.semantic_search(search_query_filtered, top_k=1, metadata_filter={"severity": "critical"})
        if semantic_results_filtered and "error" not in semantic_results_filtered[0]:
            for res in semantic_results_filtered:
                print(f"  ID: {res.get('id')}, Dist: {res.get('distance', -1):.4f}, Text: '{res.get('text', '')[:60]}...', Meta: {res.get('metadata')}")
        else:
            print(f"  Semantic search returned: {semantic_results_filtered}")
    else:
        print("  Vector store (ChromaDB) not available, skipping semantic memory example.")


    print("\n--- JSON Backup ---")
    backup_location = memory.backup_json()
    print(f"Backup created at: {backup_location}")
    if "Error" not in backup_location:
        # Check if backup files were created (example for 'events' table)
        events_backup_file = os.path.join(backup_location, "events.json")
        if os.path.exists(events_backup_file):
            print(f"Verified: '{events_backup_file}' exists.")
            with open(events_backup_file, 'r') as f:
                backed_up_events = json.load(f)
            print(f"Number of events in backup: {len(backed_up_events)}")
        else:
            print(f"Error: Backup file '{events_backup_file}' not found!")


    memory.close()
    print("\nMemoryManager example finished.")

    # Optional: Clean up example files after run
    # if os.path.exists(example_db_path): os.remove(example_db_path)
    # if os.path.exists(example_vector_path): shutil.rmtree(example_vector_path)
    # if os.path.exists(example_backup_path): shutil.rmtree(example_backup_path)
    # print("Cleaned up example files.")
