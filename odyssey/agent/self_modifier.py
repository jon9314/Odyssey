# Handles self-rewriting, GitHub branching, and reloads
import os
import subprocess
import importlib
import logging
from typing import Optional # Added for type hinting

from github import Github, GithubException # Import PyGithub

# Configure logging for this module
logger = logging.getLogger(__name__)

class SelfModifier:
    def __init__(self, repo_path=".", github_token=None, repo_owner=None, repo_name=None, sandbox_manager=None):
        """
        Initializes the SelfModifier.
        :param repo_path: Path to the Git repository (defaults to current directory).
        :param github_token: GitHub Personal Access Token for PR operations.
        :param repo_owner: Owner of the GitHub repository (username or organization).
        :param repo_name: Name of the GitHub repository.
        :param sandbox_manager: An instance of a sandbox manager (e.g., from sandbox.py)
                                 to run tests.
        """
        self.repo_path = os.path.abspath(repo_path)
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.sandbox_manager = sandbox_manager
        self.github_client = None

        if self.github_token and self.repo_owner and self.repo_name:
            try:
                self.github_client = Github(self.github_token)
                # Optionally, test connection or get repo object here to fail early
                # self.github_client.get_repo(f"{self.repo_owner}/{self.repo_name}")
                logger.info(f"PyGithub client initialized for repo: {self.repo_owner}/{self.repo_name}")
            except Exception as e: # Catching generic Exception, can be more specific e.g. GithubException
                logger.error(f"Failed to initialize PyGithub client for {self.repo_owner}/{self.repo_name}: {e}")
                self.github_client = None # Ensure client is None if init fails
        else:
            logger.warning("GitHub token, repo owner, or repo name not provided. GitHub PR features will be disabled.")

        if not self._is_git_repo():
            logger.warning(f"Path '{self.repo_path}' is not a Git repository. Some operations will fail.")

        # logger.info(f"SelfModifier initialized for repository: {self.repo_path}") # Covered by specific github init log or warning

    def _is_git_repo(self) -> bool:
        """Checks if the repo_path is a valid Git repository."""
        git_dir = os.path.join(self.repo_path, ".git")
        is_repo = os.path.isdir(git_dir)
        if not is_repo:
            logger.debug(f"Path '{self.repo_path}' .git directory check failed. Not a Git repository.")
        return is_repo
        # return os.path.isdir(os.path.join(self.repo_path, ".git")) # Duplicate line removed

    def _run_git_command(self, command: list, raise_on_error=True) -> tuple[str, str, int]:
        """Helper to run Git commands."""
        if not self._is_git_repo():
            return "", "Not a git repository", 1
        try:
            process = subprocess.run(
                ["git"] + command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False # Don't raise exception here, handle it based on raise_on_error
            )
            if process.returncode != 0 and raise_on_error:
                error_message = f"Git command {' '.join(command)} failed with error: {process.stderr}"
                logger.error(error_message)
                raise subprocess.CalledProcessError(process.returncode, command, output=process.stdout, stderr=process.stderr)
            return process.stdout.strip(), process.stderr.strip(), process.returncode
        except FileNotFoundError:
            logger.error("Git command not found. Is Git installed and in PATH?")
            if raise_on_error:
                raise
            return "", "Git command not found", -1
        except Exception as e:
            logger.error(f"Exception during git command {' '.join(command)}: {e}")
            if raise_on_error:
                raise
            return "", str(e), -2

    def checkout_branch(self, branch_name: str, create_if_not_exists: bool = False, base_branch: Optional[str] = None) -> bool:
        """
        Checks out the specified branch. Can optionally create it if it doesn't exist.
        :param branch_name: The name of the branch to checkout or create.
        :param create_if_not_exists: If True, creates the branch using `git checkout -b`.
        :param base_branch: If creating, the branch to base the new branch off. Defaults to current HEAD.
        :return: True if successful, False otherwise.
        """
        logger.info(f"Attempting to checkout branch: {branch_name}")
        if not self._is_git_repo():
            logger.error(f"Cannot checkout branch '{branch_name}', path '{self.repo_path}' is not a Git repository.")
            return False

        command = ["checkout", branch_name]
        if create_if_not_exists:
            command = ["checkout", "-b", branch_name]
            if base_branch:
                command.append(base_branch)

        stdout, stderr, ret_code = self._run_git_command(command, raise_on_error=False)
        if ret_code == 0:
            logger.info(f"Successfully checked out branch '{branch_name}'. Output: {stdout}")
            return True
        else:
            # If creation was intended and it failed, or if checkout of existing branch failed
            logger.error(f"Failed to checkout branch '{branch_name}'. Stderr: {stderr}, Stdout: {stdout}")
            # Common case: branch already exists if tried with -b
            if create_if_not_exists and ("already exists" in stderr or "already on" in stdout) :
                 logger.info(f"Branch '{branch_name}' already exists or already on it. Attempting regular checkout.")
                 return self.checkout_branch(branch_name, create_if_not_exists=False) # Try simple checkout
            return False

    def propose_code_changes(self, files_content: dict[str, str], commit_message: str, branch_name: str = None, branch_prefix: Optional[str] = None, proposal_id: Optional[str] = None) -> str:
        """
        Applies file changes, commits them to a new branch, and pushes the branch.
        This is an updated version of propose_change.
        :param files_content: A dictionary where keys are file paths (relative to repo_path)
                              and values are the new content for these files.
        :param commit_message: The commit message.
        :param branch_name: Specific name for the new branch. If None, generated using prefix and proposal_id.
        :param branch_prefix: Optional prefix for the new branch name (e.g., "feature", "fix").
        :param proposal_id: Optional unique ID to include in the generated branch name for traceability.
        :return: Tuple (branch_name: str, pr_url: Optional[str], pr_number: Optional[int], error_message: Optional[str])
        :raises: Exception if critical Git operations fail (e.g., creating branch, committing, pushing).
        """
        logger.info(f"Proposing code changes with commit message: '{commit_message}' for proposal_id: {proposal_id}")

        if not self._is_git_repo():
            raise Exception("Error: Current path is not a Git repository.")

        current_branch_stdout, _, ret_code = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], raise_on_error=False)
        if ret_code != 0:
            raise Exception(f"Error getting current branch: {current_branch_stdout}")
        current_branch = current_branch_stdout.strip()
        logger.info(f"Current branch is '{current_branch}'.")

        if not branch_name:
            prefix = branch_prefix or "proposal"
            unique_suffix = proposal_id or os.urandom(4).hex()
            sanitized_commit_msg_part = commit_message.lower().replace(' ', '-').replace('/', '-').replace('\\', '-')
            sanitized_commit_msg_part = "".join(c for c in sanitized_commit_msg_part if c.isalnum() or c == '-')[:30]
            branch_name = f"{prefix}/{unique_suffix}_{sanitized_commit_msg_part}"

        logger.info(f"Target branch for changes: {branch_name}")

        # Create or switch to the target branch
        if not self.checkout_branch(branch_name, create_if_not_exists=True, base_branch=current_branch):
             # If creation with -b failed but branch might exist from previous run, try simple checkout
            if not self.checkout_branch(branch_name, create_if_not_exists=False):
                raise Exception(f"Error creating or switching to branch '{branch_name}'.")
        logger.info(f"Successfully on branch '{branch_name}'.")

        # 3. Apply file changes
        logger.info(f"Applying file changes to branch '{branch_name}'")
        for file_path, new_content in files_content.items(): # Iterate over files_content
            full_path = os.path.join(self.repo_path, file_path)
            try:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w') as f:
                    f.write(new_content) # Use new_content
                logger.debug(f"Wrote changes to {file_path}")
                self._run_git_command(["add", file_path]) # Stage the file
            except Exception as e:
                logger.error(f"Error writing or staging file {file_path}: {e}")
                # Attempt to switch back to original branch on error
                self.checkout_branch(current_branch) # Use the new checkout method
                raise Exception(f"Error processing file {file_path}: {e}")

        # 4. Commit changes
        logger.info(f"Committing changes with message: '{commit_message}'")
        _, stderr, ret_code = self._run_git_command(["commit", "-m", commit_message])
        if ret_code != 0:
            # Attempt to switch back to original branch on error
            self.checkout_branch(current_branch)
            # Check if the error is "nothing to commit"
            if "nothing to commit" in stderr or "no changes added to commit" in stderr:
                logger.warning(f"No changes to commit for branch '{branch_name}'. This might be ok if files were identical or already committed.")
                # If branch is empty (no new commit), decide if this is an error or acceptable.
                # For now, let's assume it's acceptable and proceed as if committed.
            else:
                raise Exception(f"Error committing changes: {stderr}. No changes to commit or other git error.")

        # 5. Push the new branch to remote (e.g., origin)
        logger.info(f"Pushing branch '{branch_name}' to remote 'origin'")
        _, stderr, ret_code = self._run_git_command(["push", "-u", "origin", branch_name, "--force-with-lease"]) # Added --force-with-lease for safety on re-runs
        if ret_code != 0:
            logger.error(f"Error pushing branch '{branch_name}': {stderr}")
            # Don't switch back here, commit is made, but push failed. User might fix manually or retry.
            raise Exception(f"Changes committed to local branch '{branch_name}', but push failed: {stderr}")

        # 6. Switch back to the original branch (optional, good practice)
        self.checkout_branch(current_branch) # Switched back before PR attempt for safety

        logger.info(f"Successfully pushed code changes to branch: {branch_name}")

        # 7. Open a Pull Request
        pr_url, pr_number, pr_error = None, None, None
        if self.github_client: # Only attempt if PyGithub client is initialized
            logger.info(f"Attempting to open PR for branch '{branch_name}'...")
            # Determine default PR title from commit message if not overridden
            pr_title = f"Proposal {proposal_id}: {commit_message.splitlines()[0]}"
            # Determine PR body, could include proposal_id or more details
            pr_body = f"Automated PR for proposal ID: {proposal_id}\n\nBranch: `{branch_name}`\nCommit: `{commit_message}`"

            # Assuming 'main' or a configurable default base branch for PRs.
            # This could be passed in or configured in AppSettings.
            default_base_branch = "main" # Or load from config

            pr_url, pr_number, pr_error = self.open_pr(
                branch=branch_name,
                title=pr_title,
                body=pr_body,
                base_branch=default_base_branch
            )
            if pr_error:
                logger.error(f"Failed to open PR for branch '{branch_name}': {pr_error}")
                # Return branch name and PR error, but not fatal to proposal if push succeeded
            else:
                logger.info(f"PR opened successfully: {pr_url} (Number: {pr_number})")
        else:
            logger.warning(f"Skipping PR creation for branch '{branch_name}' as GitHub client is not configured.")
            pr_error = "GitHub client not configured, PR not created."

        return branch_name, pr_url, pr_number, pr_error

    def merge_branch(self, branch_to_merge: str, target_branch: str = "main", delete_branch_after_merge: bool = True) -> tuple[bool, str]:
        """
        Merges a specified branch into a target branch (e.g., main) and optionally deletes the merged branch.
        :param branch_to_merge: The name of the branch to merge.
        :param target_branch: The branch to merge into (default: "main").
        :param delete_branch_after_merge: Whether to delete the local and remote merged branch (default: True).
        :return: Tuple (success: bool, message: str)
        """
        logger.info(f"Attempting to merge branch '{branch_to_merge}' into '{target_branch}'.")
        if not self._is_git_repo():
            return False, "Not a Git repository."

        original_branch_stdout, _, ret_code = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], raise_on_error=False)
        if ret_code != 0:
            return False, f"Could not get current branch: {original_branch_stdout}"
        current_branch = original_branch_stdout.strip()

        try:
            # 1. Checkout the target branch
            if not self.checkout_branch(target_branch):
                return False, f"Failed to checkout target branch '{target_branch}'."

            # 2. Pull latest changes on the target branch
            logger.info(f"Pulling latest changes for target branch '{target_branch}'.")
            _, stderr_pull, ret_code_pull = self._run_git_command(["pull", "origin", target_branch], raise_on_error=False)
            if ret_code_pull != 0:
                logger.warning(f"Failed to pull latest changes for '{target_branch}': {stderr_pull}. Merge might use stale version.")
                # Depending on policy, this could be a hard failure.

            # 3. Merge the feature branch
            logger.info(f"Merging '{branch_to_merge}' into '{target_branch}'.")
            # Using --no-ff to create a merge commit, good for history. Can be changed.
            _, stderr_merge, ret_code_merge = self._run_git_command(["merge", "--no-ff", branch_to_merge], raise_on_error=False)
            if ret_code_merge != 0:
                # Attempt to abort merge on conflict
                self._run_git_command(["merge", "--abort"], raise_on_error=False)
                logger.error(f"Failed to merge '{branch_to_merge}' into '{target_branch}': {stderr_merge}")
                return False, f"Merge conflict or other error merging '{branch_to_merge}'. Details: {stderr_merge}"

            # 4. Push the target branch with merged changes
            logger.info(f"Pushing merged '{target_branch}' to origin.")
            _, stderr_push, ret_code_push = self._run_git_command(["push", "origin", target_branch], raise_on_error=False)
            if ret_code_push != 0:
                logger.error(f"Failed to push merged '{target_branch}': {stderr_push}")
                # This is a problem: merge is local but not remote.
                return False, f"Local merge successful, but failed to push '{target_branch}': {stderr_push}"

            logger.info(f"Successfully merged '{branch_to_merge}' into '{target_branch}' and pushed.")

            # 5. Optionally delete the merged branch (local and remote)
            if delete_branch_after_merge:
                logger.info(f"Deleting branch '{branch_to_merge}' locally and remotely.")
                _, stderr_delete_local, ret_code_delete_local = self._run_git_command(["branch", "-d", branch_to_merge], raise_on_error=False)
                if ret_code_delete_local == 0:
                    logger.info(f"Deleted local branch '{branch_to_merge}'.")
                else:
                    logger.warning(f"Could not delete local branch '{branch_to_merge}': {stderr_delete_local}")

                _, stderr_delete_remote, ret_code_delete_remote = self._run_git_command(["push", "origin", "--delete", branch_to_merge], raise_on_error=False)
                if ret_code_delete_remote == 0:
                    logger.info(f"Deleted remote branch '{branch_to_merge}'.")
                else:
                    # This is not critical if local delete worked and merge is pushed
                    logger.warning(f"Could not delete remote branch '{branch_to_merge}': {stderr_delete_remote}")

            return True, f"Successfully merged '{branch_to_merge}' into '{target_branch}'."

        except Exception as e:
            logger.error(f"Exception during merge_branch operation: {e}", exc_info=True)
            return False, f"An unexpected error occurred during merge: {str(e)}"
        finally:
            # Switch back to the branch active before this operation started
            self.checkout_branch(current_branch)


    def open_pr(self, branch: str, title: str = None, body: str = None, base_branch: str = "main") -> str:
        """
        Opens a Pull Request on GitHub for the given branch.
        :param branch: The branch containing the changes.
        :param title: Optional title for the PR. If None, uses the last commit message of the branch.
        :param body: Optional body/description for the PR.
        :param base_branch: The branch to open the PR against (e.g., 'main', 'develop').
        :return: Tuple (pr_url: Optional[str], pr_number: Optional[int], error_message: Optional[str])
        """
        logger.info(f"Attempting to open PR for branch '{branch}' against '{base_branch}'.")

        if not self.github_client:
            msg = "PyGithub client not initialized (missing token, owner, or repo name). Cannot open PR."
            logger.error(msg)
            return None, None, msg

        try:
            repo_full_name = f"{self.repo_owner}/{self.repo_name}"
            repo = self.github_client.get_repo(repo_full_name)
            logger.debug(f"Successfully connected to repository: {repo_full_name}")

            pr_title = title
            if not pr_title:
                # Get last commit message for title
                commit_msg_stdout, _, ret_code = self._run_git_command(["log", "-1", "--pretty=%B", branch], raise_on_error=False)
                if ret_code == 0 and commit_msg_stdout:
                    pr_title = commit_msg_stdout.splitlines()[0]  # Use first line
                else:
                    pr_title = f"Automated PR: Proposed changes from branch {branch}"
                logger.info(f"Using commit message for PR title: '{pr_title}'")

            pr_body_content = body if body else f"Automated PR for changes in branch `{branch}`."
            # You could add more details to the body, e.g., link to proposal_id if available

            # Check if a PR already exists for this branch
            # Note: PyGithub's get_pulls can be slow on large repos.
            # A more targeted check might be needed if performance is an issue.
            open_prs = repo.get_pulls(state='open', head=f'{self.repo_owner}:{branch}')
            for existing_pr in open_prs:
                if existing_pr.head.ref == branch and existing_pr.base.ref == base_branch:
                    logger.warning(f"PR already exists for branch '{branch}' into '{base_branch}': {existing_pr.html_url}")
                    return existing_pr.html_url, existing_pr.number, f"PR already exists: {existing_pr.html_url}"

            logger.info(f"Creating PR: Title='{pr_title}', Head='{branch}', Base='{base_branch}'")
            created_pr = repo.create_pull(
                title=pr_title,
                body=pr_body_content,
                head=branch,  # The branch where your changes are
                base=base_branch  # The branch you want to merge into
            )
            logger.info(f"Successfully created PR: {created_pr.html_url} (ID: {created_pr.id}, Number: {created_pr.number})")
            return created_pr.html_url, created_pr.number, None

        except GithubException as e:
            logger.error(f"GitHub API error while opening PR for branch '{branch}': {e.status} - {e.data}")
            # Attempt to parse common errors for more specific messages
            error_detail = e.data.get('message', str(e))
            if 'errors' in e.data and e.data['errors']:
                # Example: "A pull request already exists for <owner>:<branch>."
                if any("A pull request already exists" in err.get('message', '') for err in e.data['errors']):
                    logger.warning(f"GitHub indicated a PR already exists for branch '{branch}'. Attempting to find it.")
                    # Try to find the existing PR again, as the initial check might have missed it due to timing or specific states.
                    # This part can be complex if the error message doesn't provide a direct link.
                    # For now, return a generic "already exists" type message.
                    return None, None, f"Error: {error_detail} (Likely PR already exists for '{branch}')"
            return None, None, f"GitHub API error: {error_detail}"
        except Exception as e:
            logger.error(f"Unexpected error while opening PR for branch '{branch}': {e}", exc_info=True)
            return None, None, f"Unexpected error: {str(e)}"

    # Updated method signature and logic
    def sandbox_test(self, repo_clone_path: str, proposal_id: str) -> tuple[bool, str]:
        """
        Runs validation tests for the code in the specified repository clone path using Docker.
        This method assumes the correct branch is already checked out in repo_clone_path.
        :param repo_clone_path: The absolute path to the cloned repository where the proposal branch is checked out.
        :param proposal_id: The ID of the proposal, used for naming Docker images/containers.
        :return: Tuple (success: bool, output_log: str)
        """
        logger.info(f"Starting sandbox Docker validation for proposal '{proposal_id}' in path: {repo_clone_path}")
        if not self.sandbox_manager:
            msg = "Sandbox manager not provided to SelfModifier. Cannot run sandbox tests."
            logger.error(msg)
            return False, msg

        # Ensure sandbox_manager has the new method.
        if not hasattr(self.sandbox_manager, 'run_validation_in_docker'):
            msg = "Sandbox manager does not support 'run_validation_in_docker'. Update sandbox or SelfModifier initialization."
            logger.error(msg)
            return False, msg

        try:
            # The repo_clone_path is already the specific directory with the checked-out branch.
            # No need for SelfModifier to do further git operations here for testing.
            # It directly calls the sandbox_manager's Docker validation method.
            success, output_log = self.sandbox_manager.run_validation_in_docker(repo_clone_path, proposal_id)

            if success:
                logger.info(f"Sandbox Docker validation PASSED for proposal '{proposal_id}'.")
            else:
                logger.warning(f"Sandbox Docker validation FAILED for proposal '{proposal_id}'.")

            logger.debug(f"Sandbox validation output for proposal '{proposal_id}':\n{output_log}")
            return success, output_log

        except Exception as e:
            error_msg = f"Exception during sandbox_test for proposal '{proposal_id}': {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg


    def merge_pr(self, pr_id: str, merge_method: str = "merge") -> bool: # Changed return to bool
        """
        Merges the specified Pull Request on GitHub.
        :param pr_id: The ID or URL of the Pull Request.
        :param merge_method: Method to use for merging (e.g., "merge", "squash", "rebase").
        :return: True if merge was successful, False otherwise.
        """
        # This requires GitHub API interaction.
        logger.info(f"Attempting to merge PR '{pr_id}' using method '{merge_method}'.")
        if not self.github_token:
            logger.warning("GitHub token not provided. Cannot merge PR via API.")
            # Fallback: provide instructions for manual merge or using gh CLI
            try:
                # Use gh CLI to merge PR
                # gh pr merge <pr-number-or-url> --merge | --rebase | --squash
                merge_flag = f"--{merge_method}"
                pr_merge_command = ["gh", "pr", "merge", pr_id, merge_flag, "--delete-branch"] # Also delete branch after merge

                logger.info(f"Using 'gh' CLI to merge PR: {' '.join(pr_merge_command)}")
                process = subprocess.run(pr_merge_command, cwd=self.repo_path, capture_output=True, text=True, check=False)

                if process.returncode == 0:
                    logger.info(f"PR '{pr_id}' merged successfully using 'gh' CLI.")
                    return True
                else:
                    logger.error(f"'gh pr merge' failed: {process.stderr}")
                    return False

            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.warning(f"'gh' CLI not found or failed during merge: {e}. Please merge PR manually.")
                return False

        # TODO: Implement GitHub API call using self.github_token
        logger.error("PR merging via API not yet implemented.")
        return False

    def reload_code(self) -> None:
        """
        Attempts to hot-reload modules or restart parts of the application.
        This is highly application-specific.
        """
        logger.info("Attempting to reload code...")
        # Option 1: Re-import specific modules (if safe and designed for it)
        # Example:
        # try:
        #     importlib.reload(odyssey.agent.planner) # Reload a specific module
        #     importlib.reload(odyssey.plugins.some_plugin)
        #     logger.info("Relevant modules reloaded.")
        # except Exception as e:
        #     logger.error(f"Error reloading modules: {e}")

        # Option 2: Signal the main application to restart or re-initialize components.
        # This might involve setting a flag or using a more complex mechanism
        # if the application runs in multiple processes (e.g., FastAPI + Celery).

        # Option 3: If running under a process manager like Supervisor or systemd,
        # or even Docker, it might be possible to trigger a graceful restart of the service.
        # This is outside the scope of this class usually.

        # For a simple, single-process application, you might need to design a reload mechanism.
        # For Uvicorn with --reload, changes to watched files trigger a reload automatically.
        # This method might be more about re-initializing internal states post-reload.

        logger.warning("Code reload mechanism is application-specific and not fully implemented here.")
        print("Placeholder: Code reload would happen here.")
        # For now, we can simulate by re-importing a known module if needed by tests,
        # but actual hot-reloading is complex.
        try:
            # Example: if you have a central config module that might change
            # import odyssey.config.loader # Fictional config loader
            # importlib.reload(odyssey.config.loader)
            # odyssey.config.loader.load_settings() # Re-apply settings
            pass
        except Exception as e:
            logger.error(f"Placeholder reload error: {e}")


if __name__ == '__main__':
    # Example Usage (requires a Git repo and potentially GitHub CLI configured)
    # Ensure you are in the root of your 'odyssey' git repository to run this example.

    print("Running SelfModifier example...")
    logging.basicConfig(level=logging.INFO)

    # Mock sandbox manager for this example
    class MockSandbox:
        def test_code(self, script_path):
            logger.info(f"(MockSandbox) 'Testing' script: {script_path}")
            # Simulate test pass/fail based on script name or content for demo
            if "fail" in script_path.lower():
                logger.warning("(MockSandbox) Simulating test failure.")
                return "Tests failed: Mock failure condition met."
            logger.info("(MockSandbox) Simulating test pass.")
            return "Tests passed: All mock checks OK."

    # Create a dummy test_runner.py for the sandbox test example
    scripts_dir = os.path.join(os.getcwd(), "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    dummy_test_runner_path = os.path.join(scripts_dir, "test_runner.py")
    if not os.path.exists(dummy_test_runner_path):
        with open(dummy_test_runner_path, "w") as f:
            f.write("#!/usr/bin/env python\nprint('Mock test_runner.py executing...')\nprint('Tests passed')")
        os.chmod(dummy_test_runner_path, 0o755)


    # Initialize SelfModifier - assumes current directory is the git repo.
    # For GitHub operations, you'd typically load GITHUB_TOKEN from .env
    # modifier = SelfModifier(github_token=os.getenv("GITHUB_TOKEN"), sandbox_manager=MockSandbox())
    modifier = SelfModifier(sandbox_manager=MockSandbox()) # No GitHub token for local demo

    # 1. Propose a change
    # Create a dummy file to change
    dummy_file_path = "dummy_change_file.txt"
    with open(dummy_file_path, "w") as f:
        f.write("Initial content.\n")

    # Stage it if it's new, so git knows about it for diffing later
    modifier._run_git_command(["add", dummy_file_path], raise_on_error=False)
    modifier._run_git_command(["commit", "-m", "Add dummy_change_file.txt for testing self_modifier", "--allow-empty"], raise_on_error=False)


    file_changes = {
        dummy_file_path: f"Updated content by SelfModifier at {os.times().user}\nSecond line."
    }
    commit_message = "Test: SelfModifier proposes a change to dummy file"
    # Ensure a unique branch name to avoid conflicts if run multiple times
    test_branch_name = f"test-self-modifier-proposal-{os.urandom(2).hex()}"

    print(f"\n--- Proposing Change on branch {test_branch_name} ---")
    branch_result = modifier.propose_change(file_changes, commit_message, branch_name=test_branch_name)
    print(f"Propose change result: {branch_result}")

    if "Error" not in branch_result:
        created_branch = branch_result # propose_change returns branch name on success

        # 2. Open a PR (will likely use gh CLI or show manual instructions)
        print(f"\n--- Opening PR for branch {created_branch} ---")
        pr_result = modifier.open_pr(created_branch, title=f"Automated Test PR for {created_branch}", base_branch="main") # Assuming 'main' is your default branch
        print(f"Open PR result: {pr_result}")
        # pr_id_for_merge would be extracted from pr_result if successful (e.g., the PR number or URL)

        # 3. Test the branch in a sandbox
        print(f"\n--- Sandbox Testing branch {created_branch} ---")
        test_passed = modifier.sandbox_test(created_branch)
        print(f"Sandbox test passed: {test_passed}")

        if test_passed:
            # 4. Merge the PR (will likely use gh CLI or show manual instructions)
            # This step is highly interactive or needs robust API setup.
            # For this example, we'll assume pr_result contains a valid PR identifier if gh CLI worked.
            if "Error" not in pr_result and pr_result.startswith("http"): # A URL implies success from gh create
                pr_identifier_for_merge = pr_result
                print(f"\n--- Merging PR {pr_identifier_for_merge} ---")
                # merge_result = modifier.merge_pr(pr_identifier_for_merge) # This will try to merge and delete branch
                # print(f"Merge PR result: {merge_result}")
                # if merge_result:
                #     print("PR merged successfully.")
                #     # 5. Reload code (placeholder)
                #     modifier.reload_code()
                # else:
                #     print("PR merge failed or was skipped.")
                print(f"SKIPPING MERGE for PR {pr_identifier_for_merge} in this example to avoid auto-merging test branches.")
                print("If this were real, merge_pr would be called.")

            else:
                print(f"Skipping merge because PR creation might have failed or was manual: {pr_result}")
        else:
            print(f"Skipping merge because sandbox tests failed for branch {created_branch}.")

        # Clean up: delete the local and remote test branch if it wasn't merged and deleted
        # This is for tidiness after the example run.
        # In a real scenario, failed branches might be kept for inspection.
        print(f"\n--- Cleaning up test branch {created_branch} ---")
        modifier._run_git_command(["checkout", "main"], raise_on_error=False) # Switch to main first
        modifier._run_git_command(["branch", "-D", created_branch], raise_on_error=False)
        print(f"Deleted local branch: {created_branch}")
        # Deleting remote branch (if it was pushed and not merged/deleted by PR)
        # This command might fail if the branch was already deleted (e.g. by gh pr merge --delete-branch)
        # or if it was never pushed successfully.
        # modifier._run_git_command(["push", "origin", "--delete", created_branch], raise_on_error=False)
        # print(f"Attempted to delete remote branch: {created_branch}")
        print(f"SKIPPING remote branch deletion for branch: {created_branch} in this example.")


    # Clean up the dummy file
    if os.path.exists(dummy_file_path):
        os.remove(dummy_file_path)
        modifier._run_git_command(["add", dummy_file_path], raise_on_error=False) # To stage the deletion
        modifier._run_git_command(["commit", "-m", "Clean up dummy_change_file.txt from self_modifier test"], raise_on_error=False)
        print(f"Cleaned up {dummy_file_path}")

    print("\nSelfModifier example finished.")
