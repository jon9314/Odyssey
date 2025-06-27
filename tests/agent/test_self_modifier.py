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


class TestSelfModifierGitHub(unittest.TestCase):
    def setUp(self):
        # Mock os.path.isdir to always return True, simulating a git repo
        self.patch_isdir = patch('odyssey.agent.self_modifier.os.path.isdir', return_value=True)
        self.mock_os_isdir = self.patch_isdir.start()

        # Mock os.path.abspath
        self.patch_abspath = patch('odyssey.agent.self_modifier.os.path.abspath', return_value="/fake/repo")
        self.mock_os_abspath = self.patch_abspath.start()

        # Mock _run_git_command for general git operations not under test
        self.patch_run_git = patch('odyssey.agent.self_modifier.SelfModifier._run_git_command')
        self.mock_run_git_command = self.patch_run_git.start()
        # Default behavior for git calls not specific to a test
        self.mock_run_git_command.return_value = ("output", "", 0)


    def tearDown(self):
        self.patch_isdir.stop()
        self.patch_abspath.stop()
        self.patch_run_git.stop()
        patch.stopall() # Stops any other patches that might have been started

    @patch('odyssey.agent.self_modifier.Github')
    def test_init_with_github_credentials(self, MockGithub):
        """Test SelfModifier initialization with GitHub credentials."""
        mock_github_instance = MockGithub.return_value

        modifier = SelfModifier(
            repo_path=".",
            github_token="fake_token",
            repo_owner="testowner",
            repo_name="testrepo"
        )
        MockGithub.assert_called_once_with("fake_token")
        self.assertEqual(modifier.github_client, mock_github_instance)
        self.assertEqual(modifier.repo_owner, "testowner")
        self.assertEqual(modifier.repo_name, "testrepo")

    def test_init_without_github_credentials(self):
        """Test SelfModifier initialization without GitHub credentials."""
        modifier = SelfModifier(repo_path=".")
        self.assertIsNone(modifier.github_client)
        self.assertIsNone(modifier.repo_owner)
        self.assertIsNone(modifier.repo_name)

    @patch('odyssey.agent.self_modifier.Github')
    def test_open_pr_success(self, MockGithub):
        """Test successful PR opening."""
        mock_github_instance = MockGithub.return_value
        mock_repo = MagicMock()
        mock_github_instance.get_repo.return_value = mock_repo

        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/testowner/testrepo/pull/1"
        mock_pr.number = 1
        mock_pr.id = 12345
        mock_repo.create_pull.return_value = mock_pr
        mock_repo.get_pulls.return_value = [] # No existing PRs

        modifier = SelfModifier(
            github_token="fake_token", repo_owner="testowner", repo_name="testrepo"
        )

        # Mock git log command for PR title
        self.mock_run_git_command.side_effect = lambda cmd_parts, **kwargs: ("Test PR Title from commit\nMore details", "", 0) if cmd_parts[:3] == ["log", "-1", "--pretty=%B"] else ("output", "", 0)


        pr_url, pr_number, error = modifier.open_pr(
            branch="feature/test-branch", title=None, body="Test PR body", base_branch="main"
        )

        self.assertEqual(pr_url, "https://github.com/testowner/testrepo/pull/1")
        self.assertEqual(pr_number, 1)
        self.assertIsNone(error)
        mock_github_instance.get_repo.assert_called_once_with("testowner/testrepo")
        mock_repo.create_pull.assert_called_once_with(
            title="Test PR Title from commit", # Title from mocked git log
            body="Test PR body",
            head="feature/test-branch",
            base="main"
        )
        mock_repo.get_pulls.assert_called_once_with(state='open', head='testowner:feature/test-branch')


    @patch('odyssey.agent.self_modifier.Github')
    def test_open_pr_already_exists(self, MockGithub):
        """Test PR opening when a PR for the branch already exists."""
        mock_github_instance = MockGithub.return_value
        mock_repo = MagicMock()
        mock_github_instance.get_repo.return_value = mock_repo

        mock_existing_pr = MagicMock()
        mock_existing_pr.html_url = "https://github.com/testowner/testrepo/pull/existing"
        mock_existing_pr.number = 99
        mock_existing_pr.head.ref = "feature/existing-pr-branch" # Matches head in get_pulls
        mock_existing_pr.base.ref = "main" # Matches base_branch

        # Simulate get_pulls finding an existing PR
        mock_repo.get_pulls.return_value = [mock_existing_pr]

        modifier = SelfModifier(
            github_token="fake_token", repo_owner="testowner", repo_name="testrepo"
        )

        pr_url, pr_number, error = modifier.open_pr(
            branch="feature/existing-pr-branch", title="New PR Title", base_branch="main"
        )

        self.assertEqual(pr_url, mock_existing_pr.html_url)
        self.assertEqual(pr_number, mock_existing_pr.number)
        self.assertIn("PR already exists", error)
        mock_repo.create_pull.assert_not_called() # Should not attempt to create new PR
        mock_repo.get_pulls.assert_called_once_with(state='open', head='testowner:feature/existing-pr-branch')


    @patch('odyssey.agent.self_modifier.Github')
    def test_open_pr_github_api_error(self, MockGithub):
        """Test PR opening when GitHub API call fails."""
        from github import GithubException # Import locally for patching

        mock_github_instance = MockGithub.return_value
        mock_repo = MagicMock()
        mock_github_instance.get_repo.return_value = mock_repo
        mock_repo.get_pulls.return_value = [] # No existing PRs

        # Simulate a GithubException during create_pull
        mock_repo.create_pull.side_effect = GithubException(
            status=422, data={"message": "Validation Failed", "errors": [{"message": "A pull request already exists for testowner:feature/api-error-branch."}]}, headers={}
        )

        modifier = SelfModifier(
            github_token="fake_token", repo_owner="testowner", repo_name="testrepo"
        )

        pr_url, pr_number, error = modifier.open_pr(
            branch="feature/api-error-branch", title="Error PR", base_branch="main"
        )

        self.assertIsNone(pr_url)
        self.assertIsNone(pr_number)
        self.assertIsNotNone(error)
        self.assertIn("Validation Failed", error)
        self.assertIn("Likely PR already exists", error) # Test the specific error parsing

    def test_open_pr_no_github_client(self):
        """Test PR opening when GitHub client is not initialized."""
        modifier = SelfModifier(repo_path=".") # No token, owner, name
        pr_url, pr_number, error = modifier.open_pr(
            branch="feature/no-client-branch", title="No Client PR", base_branch="main"
        )
        self.assertIsNone(pr_url)
        self.assertIsNone(pr_number)
        self.assertIsNotNone(error)
        self.assertIn("PyGithub client not initialized", error)

    @patch('odyssey.agent.self_modifier.SelfModifier.open_pr')
    def test_propose_code_changes_calls_open_pr(self, mock_open_pr):
        """Test that propose_code_changes calls open_pr and returns its results."""
        modifier = SelfModifier(
            github_token="fake_token", repo_owner="testowner", repo_name="testrepo"
        )
        # Mock _run_git_command to simulate git operations succeeding
        # Specific mock for rev-parse
        def mock_git_command_for_propose(cmd_parts, **kwargs):
            if cmd_parts == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return ("main", "", 0) # Current branch
            # For other commands like add, commit, push
            return ("mock git output", "", 0)

        self.mock_run_git_command.side_effect = mock_git_command_for_propose

        # Mock checkout_branch to always succeed
        modifier.checkout_branch = MagicMock(return_value=True)

        # Set return value for the mocked open_pr
        mock_open_pr.return_value = ("http://pr.url/1", 1, None)

        files_content = {"file.py": "print('hello')"}
        commit_message = "Test commit for PR"
        proposal_id = "prop-123"

        branch_name, pr_url, pr_number, pr_error = modifier.propose_code_changes(
            files_content, commit_message, proposal_id=proposal_id
        )

        self.assertIsNotNone(branch_name) # Branch name should be generated
        # Example branch name: "proposal/prop-123_test-commit-for-pr"
        expected_branch_suffix = f"{proposal_id}_test-commit-for-pr" # Simplified check
        self.assertTrue(branch_name.startswith("proposal/"))
        self.assertIn(expected_branch_suffix, branch_name)

        self.assertEqual(pr_url, "http://pr.url/1")
        self.assertEqual(pr_number, 1)
        self.assertIsNone(pr_error)

        mock_open_pr.assert_called_once()
        args, kwargs = mock_open_pr.call_args
        self.assertEqual(kwargs['branch'], branch_name)
        self.assertEqual(kwargs['title'], f"Proposal {proposal_id}: {commit_message.splitlines()[0]}")
        self.assertIn(f"Automated PR for proposal ID: {proposal_id}", kwargs['body'])


if __name__ == '__main__':
    unittest.main()
