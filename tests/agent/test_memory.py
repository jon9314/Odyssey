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
            vector_store_path=TEST_VECTOR_STORE_PATH,
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
                    approved_by TEXT
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
        self.setUp() # Re-initialize memory manager for next test

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
