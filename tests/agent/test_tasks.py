import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY
import os # For os.path.join

# Import the Celery app and tasks
from odyssey.agent.celery_app import celery_app
from odyssey.agent.tasks import run_sandbox_validation_task, merge_approved_proposal_task

# To run Celery tasks synchronously for testing:
# celery_app.conf.update(task_always_eager=True)
# This should be done before tasks are imported or at least before they are executed.
# For more complex scenarios, especially with task state, using a Celery test framework
# or running a worker might be needed. For unit tests focusing on task logic,
# mocking and synchronous execution is often sufficient.

class TestSelfModificationTasks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Apply synchronous execution for all tests in this class
        celery_app.conf.update(task_always_eager=True)

    @classmethod
    def tearDownClass(cls):
        # Reset to default Celery behavior if needed by other test suites
        celery_app.conf.update(task_always_eager=False)


    @patch('odyssey.agent.tasks.tempfile.mkdtemp')
    @patch('odyssey.agent.tasks.shutil.rmtree')
    @patch('odyssey.agent.tasks.subprocess.run')
    @patch('odyssey.agent.tasks.SelfModifier')
    @patch('odyssey.agent.tasks.MemoryManager')
    @patch('odyssey.agent.tasks.AppSettings') # Mock AppSettings to control repo_path etc.
    @patch('odyssey.agent.tasks.Sandbox') # Mock Sandbox
    @patch('odyssey.agent.tasks.os.path.exists') # Mock os.path.exists for script check
    def test_run_sandbox_validation_task_success_script_found(
        self, mock_os_path_exists, mock_sandbox_cls, mock_app_settings_cls, mock_memory_manager_cls,
        mock_self_modifier_cls, mock_subprocess_run, mock_shutil_rmtree, mock_tempfile_mkdtemp
    ):
        proposal_id = "prop_valid_001"
        branch_name = "feature/valid-branch"
        mock_repo_path = "/path/to/main_repo"
        mock_temp_dir = "/tmp/val_prop_valid_001_xyz"
        original_commit_msg = "Test commit message"

        # Configure mocks
        mock_tempfile_mkdtemp.return_value = mock_temp_dir

        mock_settings_instance = mock_app_settings_cls.return_value
        mock_settings_instance.memory_db_path = "dummy_db.sqlite"
        mock_settings_instance.repo_path = mock_repo_path # Source repo for clone

        mock_mm_instance = mock_memory_manager_cls.return_value
        mock_mm_instance.get_proposal_log.return_value = {
            'proposal_id': proposal_id, 'branch_name': branch_name,
            'commit_message': original_commit_msg, 'status': 'proposed'
        }

        mock_sm_instance_local = mock_self_modifier_cls.return_value # For the temp_repo_dir
        mock_sm_instance_local.checkout_branch.return_value = True

        # Mock subprocess.run for git clone
        mock_clone_result = MagicMock()
        mock_clone_result.returncode = 0
        mock_clone_result.stdout = "Cloned successfully"
        mock_clone_result.stderr = ""

        # Mock subprocess.run for test script execution
        mock_test_script_result = MagicMock()
        mock_test_script_result.returncode = 0
        mock_test_script_result.stdout = "All tests passed!"
        mock_test_script_result.stderr = ""

        # Order of calls for subprocess.run: 1. git clone, 2. test script
        mock_subprocess_run.side_effect = [mock_clone_result, mock_test_script_result]

        mock_os_path_exists.return_value = True # Assume test script exists

        # Execute the task
        result = run_sandbox_validation_task.delay(proposal_id, branch_name).get(timeout=10) # .get() for eager result

        # Assertions
        mock_tempfile_mkdtemp.assert_called_once()
        mock_subprocess_run.assert_any_call(
            ["git", "clone", mock_repo_path, mock_temp_dir],
            capture_output=True, text=True, check=False
        )
        mock_self_modifier_cls.assert_called_with(repo_path=mock_temp_dir) # SM for temp dir
        mock_sm_instance_local.checkout_branch.assert_called_with(branch_name)

        mock_os_path_exists.assert_called_with(os.path.join(mock_temp_dir, "scripts/run_tests.sh"))
        mock_subprocess_run.assert_any_call(
            [os.path.join(mock_temp_dir, "scripts/run_tests.sh")],
            cwd=mock_temp_dir, capture_output=True, text=True, check=False, timeout=ANY
        )

        mock_mm_instance.log_proposal_step.assert_any_call(
            proposal_id=proposal_id, branch_name=branch_name, status="validation_in_progress",
            commit_message=original_commit_msg
        )
        mock_mm_instance.log_proposal_step.assert_called_with(
            proposal_id=proposal_id, branch_name=branch_name, status="validation_passed",
            commit_message=original_commit_msg, validation_output=ANY # Check content if needed
        )
        self.assertEqual(result['status'], "validation_passed")
        mock_shutil_rmtree.assert_called_with(mock_temp_dir)
        mock_mm_instance.close.assert_called_once()


    @patch('odyssey.agent.tasks.SelfModifier')
    @patch('odyssey.agent.tasks.MemoryManager')
    @patch('odyssey.agent.tasks.AppSettings')
    def test_merge_approved_proposal_task_success(
        self, mock_app_settings_cls, mock_memory_manager_cls, mock_self_modifier_cls
    ):
        proposal_id = "prop_merge_001"
        branch_name = "feature/merge-branch"
        commit_msg = "Feature ready for merge"
        approved_by = "test_approver"
        validation_out = "Tests passed."

        mock_settings_instance = mock_app_settings_cls.return_value
        mock_settings_instance.memory_db_path = "dummy_db.sqlite"
        mock_settings_instance.repo_path = "/path/to/main_repo"
        # Mock settings.get for main_branch_name
        mock_settings_instance.get.return_value = "main" # Default to main if not found by .get


        mock_mm_instance = mock_memory_manager_cls.return_value
        mock_mm_instance.get_proposal_log.return_value = {
            'proposal_id': proposal_id, 'branch_name': branch_name, 'status': 'user_approved',
            'commit_message': commit_msg, 'approved_by': approved_by, 'validation_output': validation_out
        }

        mock_sm_instance = mock_self_modifier_cls.return_value
        mock_sm_instance.merge_branch.return_value = (True, "Merge successful via mock.")

        # Execute the task
        result = merge_approved_proposal_task.delay(proposal_id).get(timeout=5)

        # Assertions
        mock_app_settings_cls.assert_called_once()
        mock_memory_manager_cls.assert_called_once_with(db_path="dummy_db.sqlite")
        mock_self_modifier_cls.assert_called_once_with(repo_path="/path/to/main_repo")

        mock_mm_instance.get_proposal_log.assert_called_once_with(proposal_id)
        mock_mm_instance.log_proposal_step.assert_any_call(
            proposal_id=proposal_id, branch_name=branch_name, status="merge_in_progress",
            commit_message=commit_msg, approved_by=approved_by, validation_output=validation_out
        )
        mock_sm_instance.merge_branch.assert_called_once_with(
            branch_to_merge=branch_name, target_branch="main", delete_branch_after_merge=True
        )
        mock_mm_instance.log_proposal_step.assert_called_with(
            proposal_id=proposal_id, branch_name=branch_name, status="merged",
            commit_message=commit_msg, approved_by=approved_by,
            validation_output=f"{validation_out} | Merge attempt: Merge successful via mock."
        )
        self.assertEqual(result['status'], "merged")
        self.assertEqual(result['message'], "Merge successful via mock.")
        mock_mm_instance.close.assert_called_once()

    @patch('odyssey.agent.tasks.SelfModifier')
    @patch('odyssey.agent.tasks.MemoryManager')
    @patch('odyssey.agent.tasks.AppSettings')
    def test_merge_approved_proposal_task_merge_fails(
        self, mock_app_settings_cls, mock_memory_manager_cls, mock_self_modifier_cls
    ):
        proposal_id = "prop_merge_002"
        branch_name = "feature/merge-fail-branch"
        # ... (setup other fields like above) ...
        commit_msg = "This will fail merge"

        mock_settings_instance = mock_app_settings_cls.return_value
        mock_settings_instance.get.return_value = "main"


        mock_mm_instance = mock_memory_manager_cls.return_value
        mock_mm_instance.get_proposal_log.return_value = {
            'proposal_id': proposal_id, 'branch_name': branch_name, 'status': 'user_approved',
            'commit_message': commit_msg
        }

        mock_sm_instance = mock_self_modifier_cls.return_value
        mock_sm_instance.merge_branch.return_value = (False, "Simulated merge conflict.")

        result = merge_approved_proposal_task.delay(proposal_id).get(timeout=5)

        mock_mm_instance.log_proposal_step.assert_called_with(
            proposal_id=proposal_id, branch_name=branch_name, status="merge_failed",
            commit_message=commit_msg, approved_by=None,
            validation_output=" | Merge attempt: Simulated merge conflict." # Initial VO is None
        )
        self.assertEqual(result['status'], "merge_failed")
        self.assertEqual(result['message'], "Simulated merge conflict.")

    # TODO: Add more tests:
    # - run_sandbox_validation_task:
    #   - Test script not found
    #   - Test script fails (returncode != 0)
    #   - Git clone fails
    #   - Git checkout fails
    #   - General exception during task
    # - merge_approved_proposal_task:
    #   - Proposal not found in DB
    #   - Proposal not in 'user_approved' status
    #   - General exception during task


if __name__ == '__main__':
    unittest.main()
