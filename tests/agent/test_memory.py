import unittest
import os
import sqlite3
import datetime
import shutil # For cleaning up test directories
from odyssey.agent.memory import MemoryManager

# Use a dedicated test directory for database files to avoid conflicts
TEST_DB_DIR = "var/test_memory_manager"
TEST_DB_PATH = os.path.join(TEST_DB_DIR, "test_memory.db")
TEST_VECTOR_STORE_PATH = os.path.join(TEST_DB_DIR, "test_vector_store")
TEST_JSON_BACKUP_PATH = os.path.join(TEST_DB_DIR, "test_json_backups")

class TestMemoryManagerSelfModificationLog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create the test database directory before any tests run."""
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)
        os.makedirs(TEST_DB_DIR, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Remove the test database directory after all tests have run."""
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

    def setUp(self):
        """Set up a fresh MemoryManager and database for each test."""
        # Ensure a clean database file for each test
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

        self.memory = MemoryManager(
            db_path=TEST_DB_PATH,
            vector_store_persist_path=TEST_VECTOR_STORE_PATH, # Corrected param name
            json_backup_path=TEST_JSON_BACKUP_PATH
        )
        # Manually ensure the self_modification_log table exists for these tests
        # In a real scenario, MemoryManager's __init__ handles this.
        # However, to be explicit for testing this specific feature:
        with self.memory.conn:
            self.memory.conn.execute("""
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


    def tearDown(self):
        """Close the connection and clean up the database file after each test."""
        self.memory.close()
        # if os.path.exists(TEST_DB_PATH):
        #     os.remove(TEST_DB_PATH) # Keep DB for inspection if a test fails, setUpClass handles full cleanup

    def test_log_new_proposal(self):
        """Test logging a completely new proposal."""
        proposal_id = "prop_001"
        branch_name = "feature/new-thing"
        commit_message = "Initial proposal for new thing"
        status = "proposed"

        success = self.memory.log_proposal_step(
            proposal_id, branch_name, commit_message, status
        )
        self.assertTrue(success)

        log_entry = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry['proposal_id'], proposal_id)
        self.assertEqual(log_entry['branch_name'], branch_name)
        self.assertEqual(log_entry['commit_message'], commit_message)
        self.assertEqual(log_entry['status'], status)
        self.assertIsNone(log_entry['validation_output'])
        self.assertIsNone(log_entry['approved_by'])
        self.assertIsNotNone(log_entry['created_at'])
        self.assertIsNotNone(log_entry['updated_at'])
        self.assertEqual(log_entry['created_at'], log_entry['updated_at']) # First entry

    def test_update_existing_proposal(self):
        """Test updating an existing proposal's status and other fields."""
        proposal_id = "prop_002"
        initial_branch = "feature/update-test"
        initial_commit = "Initial commit for update"
        initial_status = "proposed"

        # Log initial proposal
        self.memory.log_proposal_step(proposal_id, initial_branch, initial_commit, initial_status)
        initial_log = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(initial_log)
        initial_created_at = initial_log['created_at']
        initial_updated_at = initial_log['updated_at']

        # Ensure a slight delay for timestamp comparison if system is too fast
        # In a real test environment, you might mock datetime.datetime.utcnow()
        # For simplicity here, we assume file system timestamp resolution or a small sleep might be needed
        # but typically SQLite operations are fast enough that subsequent ops will have distinct timestamps.
        # For this test, we'll rely on the logic that updated_at is always set to "now".

        updated_status = "validation_passed"
        validation_output = "All tests green."
        updated_commit_msg = "Updated: Validated proposal" # Commit message might change

        success = self.memory.log_proposal_step(
            proposal_id, initial_branch, updated_commit_msg, # Branch might be same, commit msg might change
            updated_status, validation_output=validation_output, approved_by="validator_bot"
        )
        self.assertTrue(success)

        updated_log = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(updated_log)
        self.assertEqual(updated_log['proposal_id'], proposal_id)
        self.assertEqual(updated_log['branch_name'], initial_branch) # Assuming branch name doesn't change on status update
        self.assertEqual(updated_log['commit_message'], updated_commit_msg)
        self.assertEqual(updated_log['status'], updated_status)
        self.assertEqual(updated_log['validation_output'], validation_output)
        self.assertEqual(updated_log['approved_by'], "validator_bot")
        self.assertEqual(updated_log['created_at'], initial_created_at) # created_at should not change
        self.assertNotEqual(updated_log['updated_at'], initial_updated_at) # updated_at should change

    def test_get_non_existent_proposal(self):
        """Test retrieving a proposal that does not exist."""
        log_entry = self.memory.get_proposal_log("prop_non_existent_id_12345")
        self.assertIsNone(log_entry)

    def test_list_proposals(self):
        """Test listing all proposals."""
        proposals_data = [
            {"id": "prop_list_001", "branch": "list/b1", "commit": "c1", "status": "proposed"},
            {"id": "prop_list_002", "branch": "list/b2", "commit": "c2", "status": "merged"},
            {"id": "prop_list_003", "branch": "list/b3", "commit": "c3", "status": "rejected", "vo": "failed", "ab": "reviewer"},
        ]

        for p_data in proposals_data:
            self.memory.log_proposal_step(
                p_data["id"], p_data["branch"], p_data["commit"], p_data["status"],
                validation_output=p_data.get("vo"), approved_by=p_data.get("ab")
            )
            # Simulate time passing for updated_at ordering
            # In a real scenario, ensure timestamps are distinct enough for reliable ordering tests
            # For this test, sequential logging should be sufficient if operations are not instantaneous.

        listed_proposals = self.memory.list_proposals(limit=10)
        self.assertEqual(len(listed_proposals), len(proposals_data))

        # Check if they are ordered by updated_at DESC (most recent first)
        # This requires knowing the insertion order or mocking timestamps carefully.
        # Assuming insertion order here means prop_list_003 is most recent.
        self.assertEqual(listed_proposals[0]['proposal_id'], "prop_list_003")
        self.assertEqual(listed_proposals[1]['proposal_id'], "prop_list_002")
        self.assertEqual(listed_proposals[2]['proposal_id'], "prop_list_001")

        # Test limit
        limited_proposals = self.memory.list_proposals(limit=1)
        self.assertEqual(len(limited_proposals), 1)
        self.assertEqual(limited_proposals[0]['proposal_id'], "prop_list_003")
        self.assertIn('pr_url', limited_proposals[0]) # Check new fields are present even if None

    def test_log_proposal_with_pr_details(self):
        """Test logging a new proposal step that includes PR details."""
        proposal_id = "prop_pr_001"
        branch_name = "feature/with-pr"
        commit_message = "Proposal with PR info"
        status = "pr_open"
        pr_url = "https://github.com/example/repo/pull/123"
        pr_id = "123"
        pr_status = "open"

        success = self.memory.log_proposal_step(
            proposal_id, branch_name, commit_message, status,
            pr_url=pr_url, pr_id=pr_id, pr_status=pr_status
        )
        self.assertTrue(success)

        log_entry = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry['proposal_id'], proposal_id)
        self.assertEqual(log_entry['branch_name'], branch_name)
        self.assertEqual(log_entry['status'], status)
        self.assertEqual(log_entry['pr_url'], pr_url)
        self.assertEqual(log_entry['pr_id'], pr_id)
        self.assertEqual(log_entry['pr_status'], pr_status)
        self.assertIsNotNone(log_entry['created_at'])
        self.assertIsNotNone(log_entry['updated_at'])

    def test_update_proposal_with_pr_details_later(self):
        """Test logging a proposal first, then updating it with PR details."""
        proposal_id = "prop_pr_002"
        branch_name = "feature/no-pr-yet"
        commit_message = "Initial commit, no PR"
        initial_status = "proposed"

        # Log initial proposal without PR info
        self.memory.log_proposal_step(proposal_id, branch_name, commit_message, initial_status)
        log_entry_before_pr = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(log_entry_before_pr)
        self.assertIsNone(log_entry_before_pr['pr_url'])
        initial_created_at = log_entry_before_pr['created_at']

        # Now update with PR info
        updated_status = "pr_open"
        pr_url = "https://github.com/example/repo/pull/124"
        pr_id = "124"
        pr_status = "open"

        success = self.memory.log_proposal_step(
            proposal_id, branch_name, commit_message, # commit_message could also be updated
            updated_status,
            pr_url=pr_url, pr_id=pr_id, pr_status=pr_status
        )
        self.assertTrue(success)

        log_entry_after_pr = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(log_entry_after_pr)
        self.assertEqual(log_entry_after_pr['status'], updated_status)
        self.assertEqual(log_entry_after_pr['pr_url'], pr_url)
        self.assertEqual(log_entry_after_pr['pr_id'], pr_id)
        self.assertEqual(log_entry_after_pr['pr_status'], pr_status)
        self.assertEqual(log_entry_after_pr['created_at'], initial_created_at) # Should not change
        self.assertNotEqual(log_entry_after_pr['updated_at'], log_entry_before_pr['updated_at'])

    def test_update_pr_status_on_existing_proposal(self):
        """Test updating only the pr_status of a proposal that already has PR info."""
        proposal_id = "prop_pr_003"
        branch_name = "feature/pr-status-update"
        commit_message = "PR status will change"
        initial_pr_url = "https://github.com/example/repo/pull/125"
        initial_pr_id = "125"
        initial_pr_status = "open"

        # Log initial proposal with PR info
        self.memory.log_proposal_step(
            proposal_id, branch_name, commit_message, "pr_open",
            pr_url=initial_pr_url, pr_id=initial_pr_id, pr_status=initial_pr_status
        )

        log_entry_before_update = self.memory.get_proposal_log(proposal_id)

        # Now update only the pr_status (and main status)
        updated_main_status = "pr_merged" # Example main status change
        updated_pr_status = "merged"

        success = self.memory.log_proposal_step(
            proposal_id, branch_name, commit_message,
            updated_main_status, # Main status
            pr_status=updated_pr_status # Only PR status updated, URL and ID should persist
        )
        self.assertTrue(success)

        log_entry_after_update = self.memory.get_proposal_log(proposal_id)
        self.assertIsNotNone(log_entry_after_update)
        self.assertEqual(log_entry_after_update['status'], updated_main_status)
        self.assertEqual(log_entry_after_update['pr_url'], initial_pr_url) # Should persist
        self.assertEqual(log_entry_after_update['pr_id'], initial_pr_id) # Should persist
        self.assertEqual(log_entry_after_update['pr_status'], updated_pr_status) # Should update
        self.assertNotEqual(log_entry_after_update['updated_at'], log_entry_before_update['updated_at'])


    def test_log_proposal_step_db_error(self):
        """Test handling of SQLite errors during log_proposal_step."""
        # Intentionally close the connection to simulate an error
        self.memory.close()

        success = self.memory.log_proposal_step("prop_err", "b", "c", "s")
        self.assertFalse(success) # Should fail gracefully

        # Re-open for subsequent tests if necessary, or rely on setUp/tearDown
        # For this test, we expect it to fail and don't need to re-open here.
        # The tearDown method will attempt to close again, which is fine.
        # Re-initialize for other tests in setUp.
        # self.setUp() # Re-initialize memory manager for next test
        # Re-creating the memory instance to ensure it's fresh after closing.
        # This is important because setUp might not be called if tearDown itself fails
        # or if we want to isolate this re-initialization.
        # However, standard unittest practice is that setUp IS called before each test.
        # So, if self.memory.close() works, the next test's self.setUp() will provide a fresh one.
        # The self.setUp() call here is more of a direct re-initialization for *this specific sequence*
        # if we didn't want to rely on the next test cycle's setUp.
        # For robust test isolation, relying on setUp for each test is better.
        # Let's ensure setUp is indeed creating a new instance.
        if os.path.exists(TEST_DB_PATH): # Clean up DB file before re-init for this specific test's recovery
            os.remove(TEST_DB_PATH)
        self.memory = MemoryManager(
            db_path=TEST_DB_PATH,
            vector_store_persist_path=TEST_VECTOR_STORE_PATH, # Use the renamed param
            json_backup_path=TEST_JSON_BACKUP_PATH
        )


    def test_get_proposal_log_db_error(self):
        """Test handling of SQLite errors during get_proposal_log."""
        self.memory.close()
        log_entry = self.memory.get_proposal_log("prop_get_err")
        self.assertIsNone(log_entry)
        self.setUp()

    def test_list_proposals_db_error(self):
        """Test handling of SQLite errors during list_proposals."""
        self.memory.close()
        proposals = self.memory.list_proposals()
        self.assertEqual(proposals, []) # Should return empty list on error
        self.setUp()

if __name__ == '__main__':
    # Ensure odyssey.agent.memory can be imported
    # This might require adjusting PYTHONPATH if running this script directly
    # e.g., export PYTHONPATH=$PYTHONPATH:/path/to/your/project/root
    # For simplicity, assume it's runnable via a test runner that handles paths.
    unittest.main()


# New test class for semantic memory functionalities
from unittest.mock import MagicMock, patch

class TestMemoryManagerSemanticMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_DIR): # Ensure test dir is clean for this class too
            shutil.rmtree(TEST_DB_DIR)
        os.makedirs(TEST_DB_DIR, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

    def setUp(self):
        # For these tests, we primarily want to mock the vector_store interaction
        # We still need a MemoryManager instance, but its vector_store will be a mock.
        # The actual ChromaVectorStore is tested in test_vector_store.py

        # Patch ChromaVectorStore specifically for MemoryManager's instantiation
        # This is a bit tricky because MemoryManager instantiates it directly.
        # A common way is to patch the class in the module where MemoryManager imports it.
        self.mock_vector_store_instance = MagicMock()

        # We need to ensure that when MemoryManager calls ChromaVectorStore(...),
        # it gets our mock_vector_store_instance.
        # The patch should target 'odyssey.agent.memory.ChromaVectorStore'
        self.patcher = patch('odyssey.agent.memory.ChromaVectorStore', return_value=self.mock_vector_store_instance)
        self.MockChromaVectorStore = self.patcher.start()

        self.memory = MemoryManager(
            db_path=os.path.join(TEST_DB_DIR, "semantic_test_db.sqlite"),
            vector_store_persist_path=os.path.join(TEST_DB_DIR, "semantic_test_vs_chroma"),
            json_backup_path=os.path.join(TEST_DB_DIR, "semantic_test_json_backup")
        )
        # Crucially, after MemoryManager is initialized, its self.vector_store should be our mock
        self.assertEqual(self.memory.vector_store, self.mock_vector_store_instance)


    def tearDown(self):
        self.patcher.stop() # Important to stop the patch
        self.memory.close() # Close SQLite connection
        # setUpClass and tearDownClass handle the directory cleanup

    def test_add_semantic_memory_event(self):
        text = "Test semantic event"
        metadata = {"source": "test"}
        event_id_prop = "event_001"

        # Configure mock to simulate successful add
        self.mock_vector_store_instance.add_documents.return_value = [event_id_prop]

        returned_id = self.memory.add_semantic_memory_event(text, metadata, event_id=event_id_prop)

        self.assertEqual(returned_id, event_id_prop)
        self.mock_vector_store_instance.add_documents.assert_called_once_with(
            [{"text": text, "metadata": metadata, "id": event_id_prop}]
        )

    def test_add_semantic_memory_event_no_vector_store(self):
        self.memory.vector_store = None # Simulate vector store not being available
        returned_id = self.memory.add_semantic_memory_event("text", {})
        self.assertIsNone(returned_id)

    def test_semantic_search_success(self):
        query = "Search for similar items"
        top_k = 3
        mock_filter = {"type": "test_filter"}
        expected_results = [
            {"id": "res1", "text": "Result 1", "metadata": {}, "distance": 0.1},
            {"id": "res2", "text": "Result 2", "metadata": {}, "distance": 0.2},
        ]
        self.mock_vector_store_instance.query_similar_documents.return_value = expected_results

        results = self.memory.semantic_search(query, top_k=top_k, metadata_filter=mock_filter)

        self.assertEqual(results, expected_results)
        self.mock_vector_store_instance.query_similar_documents.assert_called_once_with(
            query_text=query, top_k=top_k, metadata_filter=mock_filter
        )

    def test_semantic_search_no_vector_store(self):
        self.memory.vector_store = None # Simulate vector store not being available
        results = self.memory.semantic_search("query")
        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0])
        self.assertIn("Vector store not initialized", results[0]["error"])

    def test_semantic_search_vector_store_error(self):
        # Simulate an error during the vector store query
        self.mock_vector_store_instance.query_similar_documents.side_effect = Exception("Vector DB Error")

        results = self.memory.semantic_search("query")
        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0])
        self.assertIn("Vector DB Error", results[0]["error"])

# If running this file directly, ensure both test classes are picked up.
# This might require adjusting how unittest.main() is called or running tests via a test runner.
# For now, if __name__ == '__main__': unittest.main() is called, it will run all TestCases in the file.

class TestMemoryManagerHybridQuery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)
        os.makedirs(TEST_DB_DIR, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

    def setUp(self):
        # Patch ChromaVectorStore for MemoryManager's __init__
        self.patcher = patch('odyssey.agent.memory.ChromaVectorStore', MagicMock())
        self.MockChromaVS = self.patcher.start()

        self.memory = MemoryManager(
            db_path=os.path.join(TEST_DB_DIR, "hybrid_test_db.sqlite"),
            vector_store_persist_path=os.path.join(TEST_DB_DIR, "hybrid_test_vs_chroma")
        )
        # Mock the individual data fetching methods that hybrid_query will call
        self.memory.semantic_search = MagicMock(return_value=[])
        self.memory.get_tasks = MagicMock(return_value=[])
        self.memory.get_logs = MagicMock(return_value=[])
        self.memory.get_plans = MagicMock(return_value=[])
        self.memory.list_proposals = MagicMock(return_value=[])

    def tearDown(self):
        self.patcher.stop()
        self.memory.close()

    def test_hybrid_query_semantic_only(self):
        query_text = "find relevant documents"
        semantic_top_k = 2
        mock_semantic_results = [
            {"id": "sem1", "text": "Semantic result 1", "metadata": {"timestamp": "2023-01-01T10:00:00"}, "distance": 0.1},
            {"id": "sem2", "text": "Semantic result 2", "metadata": {"timestamp": "2023-01-01T11:00:00"}, "distance": 0.2},
        ]
        self.memory.semantic_search.return_value = mock_semantic_results

        response = self.memory.hybrid_query(query_text=query_text, semantic_top_k=semantic_top_k)

        self.memory.semantic_search.assert_called_once_with(
            query_text=query_text, top_k=semantic_top_k, metadata_filter=None
        )
        self.assertEqual(len(response["results"]), 2)
        self.assertEqual(response["results"][0]["source_type"], "semantic_match")
        self.assertAlmostEqual(response["results"][0]["relevance_score"], 0.9) # 1.0 - 0.1
        self.assertEqual(response["results"][0]["content"]["id"], "sem1")
        # Results should be sorted by timestamp (mock data has sem2 later, so it should be first if sort works)
        # Oh, my mock data for semantic results has sem2 later, but distance is higher (less relevant).
        # The current sort is by timestamp. Let's check that.
        # sem2 (11:00) should come before sem1 (10:00)
        self.assertEqual(response["results"][0]["content"]["id"], "sem2") # After sorting by timestamp desc

    def test_hybrid_query_structured_only_tasks(self):
        query_text = "" # No semantic query
        structured_options = {
            "include_tasks": True, "task_status_filter": "pending", "task_limit": 1
        }
        mock_tasks = [
            {"id": 1, "description": "Pending task 1", "status": "pending", "timestamp": "2023-01-02T10:00:00"},
        ]
        self.memory.get_tasks.return_value = mock_tasks

        response = self.memory.hybrid_query(
            query_text=query_text, semantic_top_k=0, structured_options=structured_options
        )

        self.memory.get_tasks.assert_called_once_with(status_filter="pending", limit=1)
        self.memory.semantic_search.assert_not_called() # Or called with top_k=0
        self.assertEqual(len(response["results"]), 1)
        self.assertEqual(response["results"][0]["source_type"], "task")
        self.assertEqual(response["results"][0]["content"]["id"], 1)

    def test_hybrid_query_mixed_results_and_sorting(self):
        query_text = "mixed query"
        semantic_top_k = 1
        structured_options = {"include_db_logs": True, "db_log_limit": 1}

        # Semantic result is older
        mock_semantic_results = [{"id": "sem_old", "text": "Old semantic", "metadata": {"timestamp": "2023-01-01T00:00:00"}, "distance": 0.3}]
        # DB log is newer
        mock_db_logs = [{"id": 10, "message": "Newer DB log", "level": "INFO", "timestamp": "2023-01-03T00:00:00"}]

        self.memory.semantic_search.return_value = mock_semantic_results
        self.memory.get_logs.return_value = mock_db_logs

        response = self.memory.hybrid_query(
            query_text=query_text, semantic_top_k=semantic_top_k, structured_options=structured_options
        )

        self.assertEqual(len(response["results"]), 2)
        # Expect newer DB log first due to timestamp sorting
        self.assertEqual(response["results"][0]["source_type"], "db_log")
        self.assertEqual(response["results"][0]["content"]["id"], 10)
        self.assertEqual(response["results"][1]["source_type"], "semantic_match")
        self.assertEqual(response["results"][1]["content"]["id"], "sem_old")

    def test_hybrid_query_no_options_or_query(self):
        # Test with empty query text and no structured options, should return empty results
        response = self.memory.hybrid_query(query_text="", semantic_top_k=0, structured_options={})
        self.assertEqual(len(response["results"]), 0)
        self.memory.semantic_search.assert_not_called() # Or called with top_k=0 -> which it is
        self.memory.get_tasks.assert_not_called()
        self.memory.get_logs.assert_not_called()

    def test_hybrid_query_includes_all_types(self):
        query_text = "everything"
        options = {
            "include_tasks": True, "task_limit": 1,
            "include_db_logs": True, "db_log_limit": 1,
            "include_plans": True, "plan_limit": 1,
            "include_proposals": True, "proposal_limit": 1
        }
        self.memory.semantic_search.return_value = [{"id": "s1", "text": "s", "distance": 0.1, "metadata": {"timestamp": "2023-01-01T12:00:00"}}]
        self.memory.get_tasks.return_value = [{"id": 1, "description": "t", "timestamp": "2023-01-01T11:00:00"}]
        self.memory.get_logs.return_value = [{"id": 1, "message": "l", "timestamp": "2023-01-01T10:00:00"}]
        self.memory.get_plans.return_value = [{"id": 1, "details": "p", "timestamp": "2023-01-01T09:00:00"}]
        self.memory.list_proposals.return_value = [{"proposal_id": "prop1", "commit_message": "cm", "updated_at": "2023-01-01T08:00:00"}]

        response = self.memory.hybrid_query(query_text, semantic_top_k=1, structured_options=options)

        self.assertEqual(len(response["results"]), 5)
        source_types = [r["source_type"] for r in response["results"]]
        self.assertIn("semantic_match", source_types)
        self.assertIn("task", source_types)
        self.assertIn("db_log", source_types)
        self.assertIn("plan", source_types)
        self.assertIn("proposal", source_types)

        # Check sorting (most recent first)
        self.assertEqual(response["results"][0]["source_type"], "semantic_match") # 12:00
        self.assertEqual(response["results"][1]["source_type"], "task") # 11:00
        self.assertEqual(response["results"][2]["source_type"], "db_log") # 10:00
        self.assertEqual(response["results"][3]["source_type"], "plan") # 09:00
        self.assertEqual(response["results"][4]["source_type"], "proposal") # 08:00

        self.memory.semantic_search.assert_called_once()
        self.memory.get_tasks.assert_called_once()
        self.memory.get_logs.assert_called_once()
        self.memory.get_plans.assert_called_once()
        self.memory.list_proposals.assert_called_once()
