import logging
import os
from typing import Optional

from github import Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)

class GitHubClient:
    """
    A client for interacting with the GitHub API using PyGithub.
    """
    def __init__(self, token: Optional[str] = None, repo_name: Optional[str] = None):
        """
        Initializes the GitHub client.
        :param token: GitHub Personal Access Token. Reads from GITHUB_TOKEN env var if not provided.
        :param repo_name: The name of the repository (e.g., "owner/repo"). Reads from GITHUB_REPOSITORY env var if not provided.
        :raises ValueError: If the token or repository name is not provided or found in env vars.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.repo_name = repo_name or os.getenv("GITHUB_REPOSITORY")

        if not self.token:
            raise ValueError("GitHub token not provided and GITHUB_TOKEN environment variable is not set.")
        if not self.repo_name:
            raise ValueError("GitHub repository name not provided and GITHUB_REPOSITORY environment variable is not set.")

        try:
            self._gh = Github(self.token)
            self._repo = self._gh.get_repo(self.repo_name)
            logger.info(f"GitHubClient initialized for repository: {self.repo_name}")
        except GithubException as e:
            logger.error(f"Failed to initialize GitHub client or get repository '{self.repo_name}': {e.status} {e.data}")
            raise ValueError(f"Failed to initialize GitHub client: {e.data.get('message', 'Unknown error')}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during GitHubClient initialization: {e}")
            raise ValueError(f"An unexpected error occurred: {str(e)}") from e

    def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str, retry_attempts: int = 2) -> Optional[str]:
        """
        Creates a pull request on GitHub.
        :param title: The title of the pull request.
        :param body: The description/body of the pull request.
        :param head_branch: The name of the branch where your changes are implemented.
        :param base_branch: The name of the branch you want the changes pulled into (e.g., "main", "develop").
        :param retry_attempts: Number of times to retry on specific GitHub errors.
        :return: The URL of the created pull request, or None if creation failed.
        """
        logger.info(f"Attempting to create PR: '{title}' from '{head_branch}' to '{base_branch}' in repo '{self.repo_name}'")
        try:
            pr = self._repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
                maintainer_can_modify=True # Allow maintainers to modify the PR branch
            )
            logger.info(f"Successfully created pull request: {pr.html_url}")
            return pr.html_url
        except GithubException as e:
            # Retry logic for specific transient errors if desired
            # For example, if e.status == 502 (Bad Gateway) or similar network-related issues.
            # A more robust retry would check specific error messages or types.
            if retry_attempts > 0 and e.status in [500, 502, 503, 504]:
                logger.warning(f"GitHub API error (status {e.status}): {e.data.get('message', str(e))}. Retrying {retry_attempts} more times...")
                import time
                time.sleep(3) # Wait a bit before retrying
                return self.create_pull_request(title, body, head_branch, base_branch, retry_attempts - 1)

            # Check if PR already exists (GitHub returns a 422 Unprocessable Entity error)
            if e.status == 422 and e.data and "errors" in e.data:
                for error in e.data["errors"]:
                    if "A pull request already exists" in error.get("message", ""):
                        logger.warning(f"Pull request from '{head_branch}' to '{base_branch}' already exists.")
                        # Try to find the existing PR
                        existing_prs = self._repo.get_pulls(state='open', head=f'{self._repo.owner.login}:{head_branch}', base=base_branch)
                        if existing_prs.totalCount > 0:
                            existing_pr_url = existing_prs[0].html_url
                            logger.info(f"Found existing PR: {existing_pr_url}")
                            return existing_pr_url
                        else:
                            logger.warning(f"Could not find the existing PR for '{head_branch}' to '{base_branch}' despite error message.")
                        return None # Or raise a custom exception

            logger.error(f"Failed to create pull request: {e.status} {e.data.get('message', str(e))}")
            logger.error(f"Details: {e.data}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while creating pull request: {e}", exc_info=True)
            return None

    def get_commit_messages(self, branch_name: str, limit: int = 5) -> list[str]:
        """
        Retrieves the last few commit messages from a given branch.
        :param branch_name: The name of the branch.
        :param limit: The maximum number of commit messages to retrieve.
        :return: A list of commit messages.
        """
        try:
            branch = self._repo.get_branch(branch_name)
            commits = self._repo.get_commits(sha=branch.commit.sha)
            messages = [commit.commit.message for commit in commits[:limit]]
            return messages
        except GithubException as e:
            logger.error(f"Failed to get commit messages for branch '{branch_name}': {e.status} {e.data}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting commit messages for '{branch_name}': {e}", exc_info=True)
            return []

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Starting GitHubClient direct execution example (requires GITHUB_TOKEN and GITHUB_REPOSITORY environment variables)")

    # This example assumes you have set:
    # GITHUB_TOKEN: Your GitHub Personal Access Token with repo scope
    # GITHUB_REPOSITORY: Your repository in "owner/repo_name" format
    # And that a branch named "test-branch-for-pr" exists in your repo,
    # relative to a "main" branch.

    try:
        client = GitHubClient() # Relies on env vars

        # Example: Create a PR
        # Ensure 'test-branch-for-pr' exists and has commits not in 'main'
        # And that GITHUB_MAIN_BRANCH environment variable is set (e.g., to 'main' or 'master')
        main_branch = os.getenv("GITHUB_MAIN_BRANCH", "main")
        head_branch = "test-branch-for-pr" # Replace with a real branch in your test repo

        # Check if the head branch exists (basic check)
        try:
            client._repo.get_branch(branch=head_branch)
            logger.info(f"Test head branch '{head_branch}' found.")
        except GithubException as ge:
            if ge.status == 404:
                logger.error(f"Test head branch '{head_branch}' not found in repo '{client.repo_name}'. Please create it and push some unique commits for this example to work.")
            else:
                logger.error(f"Error checking head branch '{head_branch}': {ge}")
            exit(1)

        # Try to get last commit message from head_branch for PR title
        commits = client.get_commit_messages(head_branch, limit=1)
        if commits:
            pr_title = f"Test PR: {commits[0].splitlines()[0]}"
            pr_body = f"This is an automated test PR created by GitHubClient for branch `{head_branch}`.\n\nRecent commits:\n" + "\n".join([f"- {c}" for c in commits])
        else:
            pr_title = f"Test PR for branch {head_branch}"
            pr_body = f"This is an automated test PR created by GitHubClient for branch `{head_branch}`."

        logger.info(f"Attempting to create PR with title: '{pr_title}'")
        pr_url = client.create_pull_request(
            title=pr_title,
            body=pr_body,
            head_branch=head_branch,
            base_branch=main_branch
        )

        if pr_url:
            logger.info(f"Pull request created successfully: {pr_url}")
        else:
            logger.error("Failed to create pull request.")

    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
    except Exception as ex:
        logger.error(f"An unexpected error occurred in the example: {ex}", exc_info=True)

    logger.info("GitHubClient direct execution example finished.")
