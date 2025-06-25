import unittest
from unittest.mock import patch, MagicMock

from odyssey.agent.self_modifier import SelfModifier
# Assuming Sandbox is in odyssey.agent.sandbox
from odyssey.agent.sandbox import Sandbox

class TestSelfModifierSandbox(unittest.TestCase):

    @patch('odyssey.agent.self_modifier.os.path.abspath')
    @patch('odyssey.agent.self_modifier.os.path.isdir') # To mock _is_git_repo check
    def test_sandbox_test_delegates_to_sandbox_manager(self, mock_os_isdir, mock_os_abspath):
        # Setup mocks for SelfModifier initialization
        mock_os_abspath.return_value = "/fake/repo/path"
        mock_os_isdir.return_value = True # Assume it's a git repo

        # Mock the sandbox_manager and its run_validation_in_docker method
        mock_sandbox_mgr_instance = MagicMock(spec=Sandbox)
        mock_sandbox_mgr_instance.run_validation_in_docker.return_value = (True, "Docker validation success log")

        # Initialize SelfModifier with the mocked sandbox_manager
        modifier = SelfModifier(repo_path=".", sandbox_manager=mock_sandbox_mgr_instance)

        repo_clone_path = "/tmp/cloned_repo_for_test"
        proposal_id = "prop_test_123"

        # Call the sandbox_test method
        success, output_log = modifier.sandbox_test(repo_clone_path, proposal_id)

        # Assertions
        self.assertTrue(success)
        self.assertEqual(output_log, "Docker validation success log")
        mock_sandbox_mgr_instance.run_validation_in_docker.assert_called_once_with(repo_clone_path, proposal_id)

    @patch('odyssey.agent.self_modifier.os.path.abspath')
    @patch('odyssey.agent.self_modifier.os.path.isdir')
    def test_sandbox_test_no_sandbox_manager(self, mock_os_isdir, mock_os_abspath):
        mock_os_abspath.return_value = "/fake/repo/path"
        mock_os_isdir.return_value = True

        modifier = SelfModifier(repo_path=".", sandbox_manager=None) # No sandbox manager

        repo_clone_path = "/tmp/cloned_repo_for_test"
        proposal_id = "prop_test_456"

        success, output_log = modifier.sandbox_test(repo_clone_path, proposal_id)

        self.assertFalse(success)
        self.assertIn("Sandbox manager not provided", output_log)

    @patch('odyssey.agent.self_modifier.os.path.abspath')
    @patch('odyssey.agent.self_modifier.os.path.isdir')
    def test_sandbox_test_sandbox_manager_missing_method(self, mock_os_isdir, mock_os_abspath):
        mock_os_abspath.return_value = "/fake/repo/path"
        mock_os_isdir.return_value = True

        mock_sandbox_mgr_instance = MagicMock(spec=Sandbox)
        # Remove the method to simulate it being missing
        del mock_sandbox_mgr_instance.run_validation_in_docker

        modifier = SelfModifier(repo_path=".", sandbox_manager=mock_sandbox_mgr_instance)

        repo_clone_path = "/tmp/cloned_repo_for_test"
        proposal_id = "prop_test_789"

        success, output_log = modifier.sandbox_test(repo_clone_path, proposal_id)
        self.assertFalse(success)
        self.assertIn("does not support 'run_validation_in_docker'", output_log)


if __name__ == '__main__':
    unittest.main()
