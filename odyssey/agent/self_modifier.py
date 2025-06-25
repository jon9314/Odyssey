# Handles self-rewriting, GitHub branching, and reloads
import os
import subprocess
import importlib
import logging
from typing import Optional # Added Optional

from odyssey.agent.github_client import GitHubClient # Import GitHubClient

# Configure logging for this module
logger = logging.getLogger(__name__)

class SelfModifier:
    def __init__(self, repo_path=".", github_token: Optional[str] = None, github_repo_name: Optional[str] = None, sandbox_manager=None, main_branch_name: Optional[str] = None):
        """
        Initializes the SelfModifier.
        :param repo_path: Path to the Git repository (defaults to current directory).
        :param github_token: GitHub Personal Access Token for PR operations. Reads from GITHUB_TOKEN env var if None.
        :param github_repo_name: GitHub repository name (e.g., "owner/repo"). Reads from GITHUB_REPOSITORY env var if None.
        :param sandbox_manager: An instance of a sandbox manager (e.g., from sandbox.py) to run tests.
        :param main_branch_name: The name of the main branch in the repository (e.g., "main", "master"). Reads from MAIN_BRANCH_NAME env var if None, defaults to "main".
        """
        self.repo_path = os.path.abspath(repo_path)
        self.github_token = github_token # Will be used by GitHubClient if provided
        self.github_repo_name = github_repo_name # Will be used by GitHubClient if provided
        self.sandbox_manager = sandbox_manager
        self.main_branch_name = main_branch_name or os.getenv("MAIN_BRANCH_NAME", "main")

        self._gh_client: Optional[GitHubClient] = None
        if self.github_token or os.getenv("GITHUB_TOKEN"): # Check if token is available directly or via env
            try:
                # Initialize GitHubClient. It will use env vars if specific args are None.
                self._gh_client = GitHubClient(token=self.github_token, repo_name=self.github_repo_name)
                logger.info("GitHubClient initialized successfully within SelfModifier.")
            except ValueError as e:
                logger.warning(f"Failed to initialize GitHubClient: {e}. PR features will be limited.")
        else:
            logger.info("GitHub token not provided. GitHubClient not initialized. PR features will rely on CLI or be manual.")


        if not self._is_git_repo():
            logger.warning(f"Path '{self.repo_path}' is not a Git repository. Some operations will fail.")

        logger.info(f"SelfModifier initialized for repository: {self.repo_path}. Main branch: '{self.main_branch_name}'")

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
        :return: The name of the branch created and pushed.
        :raises: Exception if critical Git operations fail (e.g., creating branch, committing).
        """
        logger.info(f"Proposing code changes with commit message: '{commit_message}'")

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
        self.checkout_branch(current_branch)

        logger.info(f"Successfully proposed code changes on branch: {branch_name}")
        # Return both branch name and original (base) branch for PR creation convenience
        return branch_name, current_branch

    def merge_branch(self, branch_to_merge: str, target_branch: Optional[str] = None, delete_branch_after_merge: bool = True) -> tuple[bool, str]:
        """
        Merges a specified branch into a target branch (e.g., main) and optionally deletes the merged branch.
        :param branch_to_merge: The name of the branch to merge.
        :param target_branch: The branch to merge into. Defaults to self.main_branch_name.
        :param delete_branch_after_merge: Whether to delete the local and remote merged branch (default: True).
        :return: Tuple (success: bool, message: str)
        """
        _target_branch = target_branch or self.main_branch_name
        logger.info(f"Attempting to merge branch '{branch_to_merge}' into '{_target_branch}'.")
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


    def create_pull_request(self, head_branch: str, base_branch: Optional[str] = None, title: Optional[str] = None, body: Optional[str] = None, proposal_id: Optional[str] = None) -> Optional[str]:
        """
        Opens a Pull Request on GitHub for the given branch using GitHubClient.
        :param head_branch: The name of the branch where your changes are implemented.
        :param base_branch: The name of the branch you want the changes pulled into. Defaults to self.main_branch_name.
        :param title: Optional title for the PR. If None, uses the first line of the last commit message on the head_branch.
        :param body: Optional body/description for the PR. If None, a default body is generated.
        :param proposal_id: Optional proposal ID for logging and inclusion in PR body.
        :return: URL of the created PR, or None if creation failed.
        """
        _base_branch = base_branch or self.main_branch_name
        logger.info(f"Attempting to open PR for branch '{head_branch}' against '{_base_branch}'.")

        if not self._gh_client:
            logger.warning("GitHubClient not initialized. Cannot open PR via API. Please configure GITHUB_TOKEN and GITHUB_REPOSITORY.")
            # Try falling back to gh CLI if available
            return self._open_pr_with_cli(head_branch, title, body, _base_branch)

        try:
            pr_title = title
            if not pr_title:
                # Try to get the last commit message from the local repo first for the head_branch
                # This assumes head_branch is currently checked out or accessible locally
                # If this SelfModifier instance just created and pushed head_branch, it might not be locally available
                # unless we checkout to it. A safer bet is to use GitHubClient to get commits from remote.
                commit_messages = self._gh_client.get_commit_messages(branch_name=head_branch, limit=1)
                if commit_messages:
                    pr_title = commit_messages[0].splitlines()[0]
                else: # Fallback if no commit messages found via API (e.g., branch not pushed yet, unlikely here)
                    commit_msg_stdout, _, ret_code = self._run_git_command(["log", "-1", "--pretty=%B", head_branch], raise_on_error=False)
                    if ret_code == 0 and commit_msg_stdout.strip():
                        pr_title = commit_msg_stdout.strip().splitlines()[0]
                    else:
                        pr_title = f"Proposed changes from branch {head_branch}"
                logger.info(f"Using PR Title: '{pr_title}'")

            pr_body = body
            if not pr_body:
                pr_body = f"Automated PR for changes in branch `{head_branch}`."
                if proposal_id:
                    pr_body += f"\nProposal ID: {proposal_id}"
                # Potentially add more details from recent commits if desired
                # recent_commits = self._gh_client.get_commit_messages(branch_name=head_branch, limit=3)
                # if recent_commits:
                #     pr_body += "\n\nRecent commits:\n" + "\n".join([f"- {msg.splitlines()[0]}" for msg in recent_commits])

            pr_url = self._gh_client.create_pull_request(
                title=pr_title,
                body=pr_body,
                head_branch=head_branch,
                base_branch=_base_branch
            )

            if pr_url:
                # Log for MemoryManager / proposal log (simulated)
                logger.info(f"PR_SUCCESS: Proposal ID '{proposal_id if proposal_id else 'N/A'}', Branch: '{head_branch}', PR URL: {pr_url}")
            else:
                logger.error(f"PR_FAILURE: Proposal ID '{proposal_id if proposal_id else 'N/A'}', Branch: '{head_branch}'. Failed to create PR using API.")
            return pr_url

        except Exception as e:
            logger.error(f"An unexpected error occurred in create_pull_request: {e}", exc_info=True)
            return None

    def _open_pr_with_cli(self, branch: str, title: Optional[str], body: Optional[str], base_branch: str) -> Optional[str]:
        """Fallback to open PR using GitHub CLI."""
        logger.info(f"Attempting to open PR for branch '{branch}' against '{base_branch}' using 'gh' CLI.")
        try:
            subprocess.run(["gh", "--version"], check=True, capture_output=True, text=True) # Check for gh
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("'gh' CLI not found or not configured. Cannot open PR.")
            return f"GitHubClient not available and 'gh' CLI failed. Please open PR manually for branch '{branch}' against '{base_branch}'."

        pr_title = title
        if not pr_title:
            commit_msg, _, ret_code = self._run_git_command(["log", "-1", "--pretty=%B", branch], raise_on_error=False)
            if ret_code == 0 and commit_msg:
                pr_title = commit_msg.splitlines()[0]
            else:
                pr_title = f"Proposed changes from branch {branch}"

        pr_body = body if body else f"Automated PR for changes in branch {branch} (via gh CLI)."
        pr_command = ["gh", "pr", "create", "--base", base_branch, "--head", branch, "--title", pr_title, "--body", pr_body]
        logger.info(f"Executing 'gh' CLI command: {' '.join(pr_command)}")

        try:
            process = subprocess.run(pr_command, cwd=self.repo_path, capture_output=True, text=True, check=True)
            pr_url = process.stdout.strip()
            logger.info(f"PR created successfully using 'gh' CLI: {pr_url}")
            # Log for MemoryManager / proposal log (simulated)
            logger.info(f"PR_SUCCESS_CLI: Branch: '{branch}', PR URL: {pr_url}")
            return pr_url
        except subprocess.CalledProcessError as e:
            logger.error(f"'gh pr create' failed: {e.stderr}")
            logger.info(f"PR_FAILURE_CLI: Branch: '{branch}'. Failed to create PR using gh CLI: {e.stderr}")
            return f"Error opening PR using 'gh' CLI: {e.stderr}. Please open manually."
        except Exception as e:
            logger.error(f"Unexpected error using 'gh pr create': {e}", exc_info=True)
            return f"Unexpected error opening PR using 'gh' CLI. Please open manually."


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

        # Step 1: Check CI Status before attempting merge
        pr_number_to_check = None
        if isinstance(pr_id, str) and pr_id.startswith("http"):
            try:
                pr_number_to_check = int(pr_id.split('/')[-1])
            except ValueError:
                logger.error(f"Could not parse PR number from URL: {pr_id}")
                return False # Cannot check CI status
        elif isinstance(pr_id, int):
            pr_number_to_check = pr_id
        elif isinstance(pr_id, str) and pr_id.isdigit():
            pr_number_to_check = int(pr_id)

        if not pr_number_to_check:
            logger.error(f"Invalid pr_id format '{pr_id}' for checking CI status. Expected PR number or full URL.")
            return False

        logger.info(f"Checking CI status for PR #{pr_number_to_check} before attempting merge.")
        ci_passed, ci_status_message = self.check_pr_ci_status(pr_number=pr_number_to_check, poll_retries=5, poll_interval=15)

        if not ci_passed:
            logger.error(f"CI checks for PR #{pr_number_to_check} did not pass or are not complete. Status: {ci_status_message}. Merge aborted.")
            # Log this to proposal log
            logger.info(f"MERGE_ABORTED_CI: PR #{pr_number_to_check}, Reason: CI failed or pending, Details: {ci_status_message}")
            return False

        logger.info(f"CI checks for PR #{pr_number_to_check} passed. Proceeding with merge attempt.")
        logger.info(f"MERGE_ATTEMPT_CI_PASSED: PR #{pr_number_to_check}, Details: {ci_status_message}")


        # Step 2: Attempt Merge (CLI or API)
        if not self._gh_client:
            logger.warning("GitHubClient not initialized. Cannot merge PR via API. Falling back to CLI if available.")
            # Fallback to CLI
            try:
                subprocess.run(["gh", "--version"], check=True, capture_output=True, text=True)
                merge_flag = f"--{merge_method}"
                pr_identifier_cli = str(pr_number_to_check) # Use the validated PR number

                pr_merge_command = ["gh", "pr", "merge", pr_identifier_cli, merge_flag, "--delete-branch"]
                logger.info(f"Using 'gh' CLI to merge PR: {' '.join(pr_merge_command)}")
                process = subprocess.run(pr_merge_command, cwd=self.repo_path, capture_output=True, text=True, check=False)
                if process.returncode == 0:
                    logger.info(f"PR_MERGED_CLI: PR #{pr_identifier_cli} merged successfully using 'gh' CLI.")
                    return True
                else:
                    logger.error(f"MERGE_FAILED_CLI: 'gh pr merge' failed for PR #{pr_identifier_cli}: {process.stderr}")
                    return False
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.warning(f"MERGE_FAILED_CLI_ERROR: 'gh' CLI not found or failed during merge: {e}. Please merge PR manually.")
                return False
            except Exception as e:
                logger.error(f"MERGE_FAILED_CLI_UNEXPECTED_ERROR: Unexpected error during 'gh pr merge': {e}", exc_info=True)
                return False

        # If GitHubClient is available, use it (conceptually, as merge_pr isn't implemented in GitHubClient yet)
        logger.error("PR merging via PyGithub API not yet implemented in GitHubClient. Only CLI fallback is currently functional if GitHubClient is None.")
        # Example of what it might look like if GitHubClient had merge_pr:
        # try:
        #     merge_success = self._gh_client.merge_pr_api(pr_number_to_check, merge_method) # Hypothetical method
        #     if merge_success:
        #         logger.info(f"PR_MERGED_API: PR #{pr_number_to_check} merged successfully via API.")
        #         return True
        #     else:
        #         logger.error(f"MERGE_FAILED_API: PR #{pr_number_to_check} failed to merge via API.")
        #         return False
        # except Exception as e:
        #     logger.error(f"MERGE_FAILED_API_ERROR: Error merging PR #{pr_number_to_check} using API: {e}")
        #     return False
        return False # Default to false as API merge is not implemented in GitHubClient

    def check_pr_ci_status(self, pr_number: Optional[int] = None, head_sha: Optional[str] = None, poll_retries: int = 0, poll_interval: int = 30) -> tuple[bool, str]:
        """
        Checks the CI status of a pull request. Can optionally poll if status is pending.
        :param pr_number: The number of the pull request.
        :param head_sha: The SHA of the commit to check (if pr_number is not available).
        :param poll_retries: Number of times to poll if the status is 'pending'. 0 means no polling.
        :param poll_interval: Seconds to wait between polls.
        :return: Tuple (ci_passed: bool, message: str including status, conclusion, and URL).
        """
        if not self._gh_client:
            logger.warning("GitHubClient not initialized. Cannot check PR CI status via API.")
            return False, "GitHubClient not available to check CI status."

        if not pr_number and not head_sha:
            msg = "Cannot check CI status: Either pr_number or head_sha must be provided."
            logger.error(msg)
            return False, msg

        attempt = 0
        while attempt <= poll_retries:
            if attempt > 0:
                logger.info(f"Polling PR CI status (attempt {attempt}/{poll_retries}), waiting {poll_interval}s...")
                import time
                time.sleep(poll_interval)

            status, conclusion, html_url = self._gh_client.get_pr_ci_status(pr_number=pr_number, head_sha=head_sha)

            # Proposal Log Update
            log_message_ci_status = f"CI_STATUS: PR_NUM='{pr_number if pr_number else 'N/A'}', SHA='{head_sha if head_sha else 'N/A'}', Status='{status}', Conclusion='{conclusion}', URL='{html_url}'"
            logger.info(log_message_ci_status)

            if status == "success":
                return True, f"CI checks passed. Status: {status}, Conclusion: {conclusion or 'N/A'}. Details: {html_url or 'N/A'}"
            elif status == "pending":
                if attempt < poll_retries:
                    attempt += 1
                    continue # Go to next poll attempt
                else:
                    return False, f"CI checks still pending after {poll_retries} retries. Status: {status}, Conclusion: {conclusion or 'N/A'}. Details: {html_url or 'N/A'}"
            elif status in ["failure", "action_required", "cancelled", "timed_out"]:
                return False, f"CI checks failed or requires attention. Status: {status}, Conclusion: {conclusion or 'N/A'}. Details: {html_url or 'N/A'}"
            elif status == "neutral" or status == "skipped":
                 # Depending on policy, neutral/skipped might be acceptable. For now, let's say it's not a hard pass for merge.
                 # Or, treat neutral as pass if no failures.
                 # Let's consider neutral/skipped as a pass IF no failures are present.
                 # The current get_pr_ci_status logic already tries to find any failure.
                 # If it returns neutral, it implies no hard failures were found.
                 logger.info(f"CI status is '{status}'. Considering this as acceptable for merge if no explicit failures were reported.")
                 return True, f"CI checks reported '{status}'. No explicit failures. Details: {html_url or 'N/A'}"
            else: # unknown or other states
                return False, f"CI status is unknown or in an unhandled state: {status}, Conclusion: {conclusion or 'N/A'}. Details: {html_url or 'N/A'}"

        return False, "CI check polling finished without a definitive success." # Should be covered by else in loop

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
    # For GitHub operations, ensure GITHUB_TOKEN, GITHUB_REPOSITORY, and MAIN_BRANCH_NAME (optional, defaults to 'main')
    # environment variables are set if not passing them directly.
    modifier = SelfModifier(
        sandbox_manager=MockSandbox(),
        # github_token=os.getenv("GITHUB_TOKEN"), # Handled by GitHubClient if None
        # github_repo_name=os.getenv("GITHUB_REPOSITORY"), # Handled by GitHubClient if None
        # main_branch_name=os.getenv("MAIN_BRANCH_NAME") # Handled by SelfModifier constructor
    )

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
    proposal_uuid = f"proposal_{os.urandom(4).hex()}" # Example proposal ID

    print(f"\n--- Proposing Code Changes on branch {test_branch_name} (Proposal ID: {proposal_uuid}) ---")
    try:
        # propose_code_changes now returns (branch_name, original_base_branch)
        created_branch, original_base_branch = modifier.propose_code_changes(
            files_content=file_changes,
            commit_message=commit_message,
            branch_name=test_branch_name,
            proposal_id=proposal_uuid
        )
        print(f"Code changes proposed successfully on local branch: {created_branch} (based off {original_base_branch}), and pushed to remote.")

        # 2. Open a PR using the new method
        print(f"\n--- Creating Pull Request for branch {created_branch} (Proposal ID: {proposal_uuid}) ---")
        # Base branch for PR can be specified, or it defaults to self.main_branch_name (e.g. 'main')
        # which was determined from current branch when propose_code_changes was called if not specified
        pr_title = f"Automated Test PR for {created_branch} ({proposal_uuid})"
        pr_body = f"This is an automated test pull request for proposal {proposal_uuid}.\nChanges are in branch `{created_branch}`."

        # base_branch_for_pr = original_base_branch # This is the branch it was created from
        # Or use the configured main branch:
        base_branch_for_pr = modifier.main_branch_name

        pr_url = modifier.create_pull_request(
            head_branch=created_branch,
            base_branch=base_branch_for_pr, # Explicitly use the determined original base or configured main
            title=pr_title,
            body=pr_body,
            proposal_id=proposal_uuid
        )
        print(f"Create Pull Request result: {pr_url}")

        # 3. Test the branch in a sandbox
        # For sandbox testing, SelfModifier's sandbox_test expects a path to a clone where the branch is checked out.
        # The current SelfModifier is operating on the main repo_path.
        # If tests need to run on the *committed and pushed* state, this is fine.
        # The example `sandbox_test` takes `created_branch` which is not a path.
        # This part of the example needs clarification on how `sandbox_test` is supposed to get the code.
        # Assuming for now that `sandbox_test` can work with the current `repo_path`
        # after checking out `created_branch`.
        print(f"\n--- Sandbox Testing branch {created_branch} (Proposal ID: {proposal_uuid}) ---")
        # Before testing, ensure the created_branch is checked out in the repo_path
        # modifier.checkout_branch(created_branch) # This might be needed if sandbox_test doesn't handle it
        # The current sandbox_test in SelfModifier seems to take repo_clone_path and proposal_id.
        # It doesn't do the checkout itself.
        # For this example, let's assume the current repo_path *is* the clone path and the branch is active.
        # This part of the original example was: test_passed = modifier.sandbox_test(created_branch)
        # which is incorrect as sandbox_test expects a path.
        # We'll simulate it by just logging for now as the sandbox_test might need rework or a proper clone.

        # To properly use sandbox_test, one would typically:
        # 1. Clone the repo to a temporary location.
        # 2. Checkout the specific `created_branch` in that clone.
        # 3. Pass the path to this temporary clone to `sandbox_test`.
        # This is skipped in this CLI example for brevity, as `sandbox_manager.run_validation_in_docker`
        # expects a path where Dockerfile and code exist.

        print(f"SKIPPING actual sandbox_test for branch {created_branch} in this CLI example.")
        print("  (To run, SelfModifier's sandbox_test would need a proper clone path with the branch checked out)")
        test_passed = True # Assume pass for example flow

        if test_passed: # Conceptual sandbox test from example
            if pr_url and not isinstance(pr_url, str) or not pr_url.startswith("Error"): # Check if pr_url is a valid URL string
                pr_number_for_ci_check = None
                try:
                    pr_number_for_ci_check = int(pr_url.split('/')[-1])
                except (ValueError, AttributeError, IndexError):
                    logger.warning(f"Could not parse PR number from PR URL '{pr_url}' for CI check. Skipping CI check and merge.")

                if pr_number_for_ci_check:
                    print(f"\n--- Checking CI Status for PR #{pr_number_for_ci_check} (URL: {pr_url}) ---")
                    # Poll for CI status with retries
                    # In a real scenario, polling might happen asynchronously or over a longer period.
                    # For this example, using a few retries with a short interval.
                    ci_passed, ci_message = modifier.check_pr_ci_status(pr_number=pr_number_for_ci_check, poll_retries=3, poll_interval=10) # Poll for ~30s
                    print(f"CI Check Result for PR #{pr_number_for_ci_check}: {'PASSED' if ci_passed else 'FAILED/PENDING'}. Message: {ci_message}")

                    if ci_passed:
                        print(f"\n--- Attempting to Merge PR #{pr_number_for_ci_check} (Conceptual) ---")
                        # The merge_pr in SelfModifier now includes CI check again, but check_pr_ci_status handles logging better for this example.
                        # For this example, we'll call merge_pr directly, assuming the CI check inside it will also pass if we got here.
                        # Or, we can rely on the check we just did.
                        # Let's assume the earlier check_pr_ci_status is the gate.

                        # merge_successful = modifier.merge_pr(pr_id=str(pr_number_for_ci_check), merge_method="squash")
                        # print(f"Merge PR result: {merge_successful}")
                        # if merge_successful:
                        #     print(f"PR #{pr_number_for_ci_check} merged successfully (conceptually).")
                        #     modifier.reload_code()
                        # else:
                        #     print(f"PR #{pr_number_for_ci_check} merge failed or was skipped (conceptually).")
                        print(f"SKIPPING ACTUAL MERGE for PR #{pr_number_for_ci_check} in this example. merge_pr would be called here.")
                        print("If merge_pr were called, it would re-check CI status as a safeguard.")
                    else:
                        print(f"Skipping merge for PR #{pr_number_for_ci_check} because CI checks did not pass or are still pending.")
                else:
                    print(f"Could not determine PR number from URL '{pr_url}'. Skipping CI check and merge.")
            else:
                print(f"Skipping CI check and merge because PR creation might have failed or PR URL is invalid: {pr_url}")
        else:
            print(f"Skipping CI check and merge because sandbox tests failed (conceptually) for branch {created_branch}.")

        # Clean up: delete the local test branch
        # Remote branch deletion would typically happen if PR is merged and "delete branch on merge" is set,
        # or could be done explicitly via API/CLI if PR is closed without merging.
        print(f"\n--- Cleaning up local test branch {created_branch} ---")
        current_checkout, _, _ = modifier._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        if current_checkout.strip() == created_branch: # If current branch is the one to delete
             modifier.checkout_branch(base_branch_for_pr) # Switch to base branch first

        modifier._run_git_command(["branch", "-D", created_branch], raise_on_error=False)
        print(f"Deleted local branch: {created_branch}")
        print(f"SKIPPING remote branch deletion for branch: {created_branch} in this example (usually handled by PR merge).")

    except Exception as e:
        logger.error(f"Error during SelfModifier example operation: {e}", exc_info=True)
        print(f"An error occurred: {e}")


    # Clean up the dummy file
    if os.path.exists(dummy_file_path):
        # Need to ensure we are on a branch that can commit, or handle if on detached HEAD
        current_main_branch = modifier.main_branch_name
        modifier.checkout_branch(current_main_branch)
        os.remove(dummy_file_path)
        modifier._run_git_command(["add", dummy_file_path], raise_on_error=False) # To stage the deletion
        modifier._run_git_command(["commit", "-m", "Clean up dummy_change_file.txt from self_modifier test"], raise_on_error=False)
        print(f"Cleaned up {dummy_file_path}")

    print("\nSelfModifier example finished.")
