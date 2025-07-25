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
from .langfuse_client import LangfuseClientWrapper as ActualLangfuseClientWrapper

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
                 langfuse_wrapper: Optional[ActualLangfuseClientWrapper] = None): # Updated to langfuse_wrapper
        """
        Initializes the MemoryManager.
        :param db_path: Path to the SQLite database file.
        :param vector_store_persist_path: Path for ChromaDB persistent storage.
        :param vector_store_collection_name: Name of the ChromaDB collection.
        :param json_backup_path: Directory for JSON backups.
        :param embedding_model_name: Name of the sentence transformer model for embeddings.
        :param langfuse_wrapper: Optional instance of LangfuseClientWrapper for observability.
        """
        self.db_path = db_path
        self.json_backup_path = json_backup_path

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.json_backup_path, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

        # Vector Store Initialization
        self.vector_store: Optional[VectorStoreInterface] = None
        try:
            logger.info(f"Initializing ChromaVectorStore: collection='{vector_store_collection_name}', persist_path='{vector_store_persist_path}', model='{embedding_model_name}'")
            self.vector_store = ChromaVectorStore(
                collection_name=vector_store_collection_name,
                persist_directory=vector_store_persist_path,
                embedding_model_name=embedding_model_name
            )
            logger.info(f"ChromaVectorStore initialized. Collection count: {self.vector_store.get_collection_count()}")
        except ImportError:
            logger.warning("ChromaDB/SentenceTransformers not found. Semantic memory unavailable.")
            self.vector_store = None
        except Exception as e:
            logger.error(f"Failed to initialize ChromaVectorStore: {e}", exc_info=True)
            self.vector_store = None

        # Langfuse Client Wrapper
        self.langfuse_wrapper = langfuse_wrapper # Store the passed wrapper
        if self.langfuse_wrapper and self.langfuse_wrapper.active:
            logger.info("Langfuse client wrapper provided and active.")
        else:
            logger.info("Langfuse client wrapper not provided or not active; observability will be limited.")

        # Updated log message to reflect correct variable for vector store path
        logger.info(f"MemoryManager initialized. SQLite DB: {self.db_path}, Vector Store Persist Path: {vector_store_persist_path}, JSON Backup: {self.json_backup_path}")

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
                    approved_by TEXT,
                    pr_url TEXT,
                    pr_id TEXT,
                    pr_status TEXT
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
                desc_snippet = description[:100] + "..." if len(description) > 100 else description
                logger.info(f"Task added with ID: {task_id}, Description snippet: '{desc_snippet}'")
                self.log_to_langfuse({
                    "event_type": "memory_add_task", # More specific event name
                    "task_id": task_id,
                    "input": {"description": description, "initial_status": "pending"},
                    "output": {"task_id": task_id}
                })
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
                    self.log_to_langfuse({
                        "event_type": "memory_update_task_status",
                        "task_id": task_id,
                        "input": {"new_status": status},
                        "output": {"updated": True}
                    })
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
                self.log_to_langfuse({
                    "event_type": "memory_add_plan",
                    "plan_id": plan_id,
                    "input": {"details_preview": details[:200]}, # Log more preview
                    "output": {"plan_id": plan_id}
                })
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
                self.log_to_langfuse({
                    "event_type": "memory_db_log_event_written", # Specific name
                    "log_id": log_id,
                    "input": {"message": message, "level": level},
                    "output": {"log_id": log_id}
                })
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
                          approved_by: Optional[str] = None,
                          pr_url: Optional[str] = None, pr_id: Optional[str] = None, # Changed from pr_number to pr_id to match schema type
                          pr_status: Optional[str] = None) -> bool:
        """
        Logs or updates a step in the self-modification proposal lifecycle.
        Uses UPSERT to handle new proposals or update existing ones.

        :param proposal_id: Unique identifier for the proposal.
        :param branch_name: Git branch name associated with the proposal.
        :param commit_message: Commit message for the proposed change.
        :param status: Current status of the proposal (e.g., "proposed", "validation_pending", "pr_open").
        :param validation_output: Output from validation tests (nullable).
        :param approved_by: Identifier of the user/entity that approved the proposal (nullable).
        :param pr_url: URL of the pull request (nullable).
        :param pr_id: ID or number of the pull request (nullable).
        :param pr_status: Status of the pull request (e.g., "open", "merged", "closed") (nullable).
        :return: True if the operation was successful, False otherwise.
        """
        now_timestamp = datetime.datetime.utcnow().isoformat()
        try:
            with self.conn:
                # Check if record exists to decide if created_at needs to be set
                cursor = self.conn.execute("SELECT proposal_id FROM self_modification_log WHERE proposal_id = ?", (proposal_id,))
                exists = cursor.fetchone()

                if exists:
                    # Update existing record
                    self.conn.execute("""
                        UPDATE self_modification_log SET
                            branch_name = ?, commit_message = ?, status = ?,
                            validation_output = ?, updated_at = ?, approved_by = ?,
                            pr_url = COALESCE(?, pr_url),
                            pr_id = COALESCE(?, pr_id),
                            pr_status = COALESCE(?, pr_status)
                        WHERE proposal_id = ?
                    """, (branch_name, commit_message, status, validation_output,
                          now_timestamp, approved_by, pr_url, pr_id, pr_status, proposal_id))
                else:
                    # Insert new record
                    self.conn.execute("""
                        INSERT INTO self_modification_log (
                            proposal_id, branch_name, commit_message, status,
                            validation_output, created_at, updated_at, approved_by,
                            pr_url, pr_id, pr_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (proposal_id, branch_name, commit_message, status,
                          validation_output, now_timestamp, now_timestamp, approved_by,
                          pr_url, pr_id, pr_status))

            logger.info(f"Proposal step logged for ID '{proposal_id}'. Status: {status}, PR Status: {pr_status}, Updated_at: {now_timestamp}")

            langfuse_input = {
                "branch_name": branch_name,
                "commit_message": commit_message,
                "status": status,
                "validation_output_snippet": validation_output[:100] if validation_output else None,
                "approved_by": approved_by,
                "pr_url": pr_url,
                "pr_id": pr_id,
                "pr_status": pr_status
            }
            # Remove None values from langfuse_input to keep logs clean
            langfuse_input_cleaned = {k: v for k, v in langfuse_input.items() if v is not None}

            self.log_to_langfuse({
                "event_type": "memory_log_proposal_step",
                "proposal_id": proposal_id,
                "input": langfuse_input_cleaned,
                "output": {"updated": True}
            })
            return True
        except sqlite3.Error as e:
            logger.error(f"SQLite error logging proposal step for ID '{proposal_id}': {e}", exc_info=True)
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
                self.log_to_langfuse({
                    "event_type": "memory_add_semantic_event",
                    "doc_id": doc_id,
                    "input": {"text_snippet": text[:200], "metadata": metadata, "provided_id": event_id},
                    "output": {"stored_id": doc_id}
                })
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
            self.log_to_langfuse({
                "event_type": "memory_semantic_search",
                "input": {"query_text_snippet": query_text[:200], "top_k": top_k, "metadata_filter": metadata_filter},
                "output": {"num_results": len(results), "first_result_id": results[0]['id'] if results else None}
            })
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

    def log_to_langfuse(self, event_data: dict) -> None:
        """Send an event dictionary to Langfuse if the wrapper is active."""
        if self.langfuse_wrapper and self.langfuse_wrapper.active:
            event_name = event_data.pop("event_type", "memory_manager_event") # Use event_type or a default

            # Separate input/output if present, rest goes to metadata
            input_data = event_data.pop("input", None)
            output_data = event_data.pop("output", None)

            # Remaining event_data items are considered metadata
            metadata = event_data

            # If a specific trace_id (object or string) isn't passed, this event might not be linked
            # or the LangfuseClientWrapper might create a default trace for it.
            # For MemoryManager events, it's often good if they are part of a larger operation's trace.
            # The caller of MemoryManager methods would ideally pass a parent_trace_obj.
            # For now, if no trace_id is passed, it will create a new trace per event.
            # This might be too granular; consider how to manage traces for sequences of memory ops.
            # For now, let's assume trace_id is None if not explicitly passed by instrumented methods.
            # This means instrumented methods MUST be updated to create/pass traces.
            # Let's simplify: MemoryManager's internal methods will create their own trace if one isn't implicitly available.
            # The LangfuseClientWrapper's log_event can handle creating a default trace.

            # For now, the instrumented methods will just call this with event_data.
            # The trace management (creating a top-level trace for an operation and passing it down)
            # should ideally happen at a higher level (e.g., in API handlers or Celery tasks).
            # If MemoryManager methods are called without a parent trace, they will create their own.

            # Let's adjust the wrapper's log_event to take trace_id, and here we might not always have one.
            # The wrapper will handle creating a trace if trace_id is None.
            self.langfuse_wrapper.log_event(
                trace_id=None, # Let wrapper create a trace if no parent context
                name=event_name,
                input=input_data,
                output=output_data,
                metadata=metadata
            )
        # else:
            # logger.debug(f"Langfuse not active. Event not logged: {event_name}")


    def close(self):
        """Closes the SQLite connection."""
        if self.conn:
            self.conn.close()
            logger.info("SQLite connection closed.")

    def __del__(self):
        self.close()


