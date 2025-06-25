# Handles self-rewriting, GitHub branching, and reloads
import os
import subprocess
import importlib
import logging

# Configure logging for this module
logger = logging.getLogger(__name__)

class SelfModifier:
    def __init__(self, repo_path=".", github_token=None, sandbox_manager=None):
        """
        Initializes the SelfModifier.
        :param repo_path: Path to the Git repository (defaults to current directory).
        :param github_token: GitHub Personal Access Token for PR operations.
        :param sandbox_manager: An instance of a sandbox manager (e.g., from sandbox.py)
                                 to run tests.
        """
        self.repo_path = os.path.abspath(repo_path)
        self.github_token = github_token  # TODO: Use this for actual GitHub API calls
        self.sandbox_manager = sandbox_manager

        if not self._is_git_repo():
            logger.warning(f"Path '{self.repo_path}' is not a Git repository. Some operations will fail.")

        logger.info(f"SelfModifier initialized for repository: {self.repo_path}")

    def _is_git_repo(self) -> bool:
        """Checks if the repo_path is a valid Git repository."""
        return os.path.isdir(os.path.join(self.repo_path, ".git"))

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


    def propose_change(self, files: dict[str, str], message: str, branch_name: str = None) -> str:
        """
        Applies file changes, commits them to a new branch, and pushes the branch.
        :param files: A dictionary where keys are file paths (relative to repo_path)
                      and values are the new content for these files.
        :param message: The commit message.
        :param branch_name: Optional name for the new branch. If None, a default name is generated.
        :return: The name of the branch created and pushed, or an error message.
        """
        logger.info(f"Proposing changes with message: '{message}'")

        if not self._is_git_repo():
            return "Error: Current path is not a Git repository."

        # 1. Get current branch
        current_branch, _, ret_code = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        if ret_code != 0:
            return f"Error getting current branch: {current_branch}"

        # 2. Create a new branch
        if not branch_name:
            branch_name = f"self-modify/{message.lower().replace(' ', '-')[:20]}-{os.urandom(3).hex()}"

        logger.info(f"Creating new branch: {branch_name} from {current_branch}")
        _, stderr, ret_code = self._run_git_command(["checkout", "-b", branch_name, current_branch])
        if ret_code != 0:
            # Attempt to switch to it if it already exists (e.g. from a previous failed attempt)
            _, stderr_checkout, ret_code_checkout = self._run_git_command(["checkout", branch_name])
            if ret_code_checkout != 0:
                return f"Error creating or switching to branch '{branch_name}': {stderr or stderr_checkout}"
            logger.info(f"Switched to existing branch: {branch_name}")


        # 3. Apply file changes
        logger.info(f"Applying file changes to branch '{branch_name}'")
        for file_path, content in files.items():
            full_path = os.path.join(self.repo_path, file_path)
            try:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w') as f:
                    f.write(content)
                logger.debug(f"Wrote changes to {file_path}")
                self._run_git_command(["add", file_path]) # Stage the file
            except Exception as e:
                logger.error(f"Error writing or staging file {file_path}: {e}")
                # Attempt to switch back to original branch on error
                self._run_git_command(["checkout", current_branch], raise_on_error=False)
                return f"Error processing file {file_path}: {e}"

        # 4. Commit changes
        logger.info(f"Committing changes with message: '{message}'")
        _, stderr, ret_code = self._run_git_command(["commit", "-m", message])
        if ret_code != 0:
            # Attempt to switch back to original branch on error
            self._run_git_command(["checkout", current_branch], raise_on_error=False)
            return f"Error committing changes: {stderr}. No changes to commit or other git error."

        # 5. Push the new branch to remote (e.g., origin)
        # This step requires authentication if the repo is private or pushing to protected branches.
        # For now, assumes 'origin' is the remote.
        logger.info(f"Pushing branch '{branch_name}' to remote 'origin'")
        _, stderr, ret_code = self._run_git_command(["push", "-u", "origin", branch_name])
        if ret_code != 0:
            # Don't switch back here, commit is made, but push failed. User might fix manually.
            logger.error(f"Error pushing branch '{branch_name}': {stderr}")
            return f"Changes committed to local branch '{branch_name}', but push failed: {stderr}"

        # 6. Switch back to the original branch (optional, good practice)
        self._run_git_command(["checkout", current_branch], raise_on_error=False)

        logger.info(f"Successfully proposed changes on branch: {branch_name}")
        return branch_name

    def open_pr(self, branch: str, title: str = None, body: str = None, base_branch: str = "main") -> str:
        """
        Opens a Pull Request on GitHub for the given branch.
        :param branch: The branch containing the changes.
        :param title: Optional title for the PR. If None, uses the last commit message of the branch.
        :param body: Optional body/description for the PR.
        :param base_branch: The branch to open the PR against (e.g., 'main', 'develop').
        :return: URL of the created PR, or an error message.
        """
        # This requires GitHub API interaction (e.g., using PyGithub or `gh` CLI)
        # For now, this is a placeholder.
        logger.info(f"Attempting to open PR for branch '{branch}' against '{base_branch}'.")
        if not self.github_token:
            logger.warning("GitHub token not provided. Cannot open PR via API.")
            # Fallback: provide instructions for manual PR or using gh CLI
            try:
                # Check if gh CLI is installed
                subprocess.run(["gh", "--version"], check=True, capture_output=True)

                pr_title = title
                if not pr_title:
                    # Get last commit message for title
                    commit_msg, _, ret_code = self._run_git_command(["log", "-1", "--pretty=%B", branch])
                    if ret_code == 0 and commit_msg:
                        pr_title = commit_msg.splitlines()[0] # Use first line of commit message
                    else:
                        pr_title = f"Proposed changes from branch {branch}"

                pr_body = body if body else f"Automated PR for changes in branch {branch}."

                # Use gh CLI to open PR
                # Ensure you are logged in with `gh auth login` if using this.
                pr_command = ["gh", "pr", "create", "--base", base_branch, "--head", branch, "--title", pr_title, "--body", pr_body]

                logger.info(f"Using 'gh' CLI to create PR: {' '.join(pr_command)}")
                # This command will run in the context of the repo_path.
                # It might require user interaction if not fully authenticated or if there are conflicts.
                # For a fully automated system, direct API calls (PyGithub) are better.
                process = subprocess.run(pr_command, cwd=self.repo_path, capture_output=True, text=True, check=False)

                if process.returncode == 0:
                    pr_url = process.stdout.strip() # gh pr create usually outputs the URL
                    logger.info(f"PR created successfully: {pr_url}")
                    return pr_url
                else:
                    logger.error(f"'gh pr create' failed: {process.stderr}")
                    return f"Error opening PR using 'gh' CLI: {process.stderr}. Please open manually."

            except (FileNotFoundError, subprocess.CalledProcessError):
                logger.warning("'gh' CLI not found or not configured. Please open PR manually.")
                return f"GitHub token not available and 'gh' CLI failed. Please open PR manually for branch '{branch}' against '{base_branch}'."

        # TODO: Implement GitHub API call using self.github_token
        return f"Error: PR opening via API not yet implemented. Please open PR for branch '{branch}' manually."


    def sandbox_test(self, branch: str) -> bool:
        """
        Checks out the specified branch and runs tests in a sandbox.
        :param branch: The branch to test.
        :return: True if tests pass, False otherwise.
        """
        logger.info(f"Starting sandbox test for branch: {branch}")
        if not self.sandbox_manager:
            logger.error("Sandbox manager not provided. Cannot run sandbox tests.")
            return False

        original_branch, _, ret_code = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        if ret_code != 0:
            logger.error(f"Could not get current branch: {original_branch}")
            return False

        try:
            # Fetch latest changes and checkout the branch
            self._run_git_command(["fetch", "origin", branch])
            _, stderr, ret_code = self._run_git_command(["checkout", branch])
            if ret_code != 0:
                logger.error(f"Could not checkout branch '{branch}': {stderr}")
                return False

            # Pull latest changes for the branch
            _, stderr, ret_code = self._run_git_command(["pull", "origin", branch])
            if ret_code != 0:
                logger.warning(f"Could not pull latest changes for branch '{branch}': {stderr}. Proceeding with local version.")

            # TODO: Define what "tests" mean. This could be:
            # 1. Running a specific test script (e.g., scripts/test_runner.py)
            # 2. Checking if the application starts
            # 3. Linting, type checking, etc.
            # For now, assume sandbox_manager has a method like `run_validation_script`
            # and it knows where the project root is or can be told.
            # The sandbox_manager.test_code() expects a script path.

            # Example: Using a predefined test script from the `scripts` directory
            test_script_path = os.path.join(self.repo_path, "scripts", "test_runner.py") # Adjust if needed
            if not os.path.exists(test_script_path):
                logger.error(f"Test script not found at {test_script_path}")
                return False

            logger.info(f"Running test script '{test_script_path}' in sandbox for branch '{branch}'.")
            # The sandbox's test_code method needs to be robust.
            # It should ideally operate on a copy of the checked-out branch, not the live repo_path.
            # For this skeleton, we assume it runs on the current state of repo_path.
            result_output = self.sandbox_manager.test_code(test_script_path)
            logger.debug(f"Sandbox test output:\n{result_output}")

            # Parse result_output to determine pass/fail
            # This is highly dependent on the output format of your test_runner.py
            if "Tests passed" in result_output and "Tests failed" not in result_output and "Error" not in result_output: # Basic check
                logger.info(f"Sandbox tests passed for branch '{branch}'.")
                return True
            else:
                logger.warning(f"Sandbox tests failed for branch '{branch}'. Output:\n{result_output}")
                return False

        except Exception as e:
            logger.error(f"Exception during sandbox test for branch '{branch}': {e}")
            return False
        finally:
            # Always switch back to the original branch
            self._run_git_command(["checkout", original_branch], raise_on_error=False)
            logger.info(f"Switched back to original branch: {original_branch}")


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
