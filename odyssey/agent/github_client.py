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

    def get_pr_ci_status(self, pr_number: Optional[int] = None, head_sha: Optional[str] = None) -> tuple[str, Optional[str], Optional[str]]:
        """
        Retrieves the CI status for a given pull request number or commit SHA.
        Prefers PR number if available.
        :param pr_number: The number of the pull request.
        :param head_sha: The SHA of the commit to check (typically the head commit of a PR's branch).
        :return: A tuple: (status: str, conclusion: Optional[str], html_url: Optional[str])
                 Status can be 'success', 'failure', 'pending', 'neutral', 'action_required', 'cancelled', 'skipped', 'stale', 'timed_out', 'unknown'.
                 Conclusion provides more detail for completed checks (e.g., 'success', 'failure', 'neutral', etc.).
                 HTML_url points to the checks page or the PR if checks URL isn't found.
        """
        if not pr_number and not head_sha:
            raise ValueError("Either pr_number or head_sha must be provided to get CI status.")

        sha_to_check = head_sha
        pr_html_url = None

        try:
            if pr_number:
                pr = self._repo.get_pull(pr_number)
                sha_to_check = pr.head.sha
                pr_html_url = pr.html_url
                logger.info(f"Fetching CI status for PR #{pr_number} (head SHA: {sha_to_check})")
            else:
                logger.info(f"Fetching CI status for commit SHA: {sha_to_check}")

            if not sha_to_check: # Should not happen if pr_number is valid
                logger.error(f"Could not determine commit SHA for PR #{pr_number}.")
                return "unknown", "Could not determine SHA", pr_html_url

            # Get check suites for the commit
            check_suites = self._repo.get_commit(sha_to_check).get_check_suites(accept="application/vnd.github.antiope-preview+json")

            if check_suites.totalCount == 0:
                logger.info(f"No check suites found for SHA {sha_to_check}. Assuming 'neutral' or 'pending' if recent.")
                # Could also check PR's mergeable_state if available and pr_number was given
                if pr_number and pr:
                    # Refresh PR data as mergeable_state can change
                    pr.update()
                    if pr.mergeable_state == "dirty": #  Merge conflicts
                        return "failure", "merge_conflict", pr_html_url
                    if pr.mergeable_state == "unknown": # Still being computed
                        return "pending", "computation_pending", pr_html_url
                    # Other states like 'blocked', 'unstable' might map to pending/failure
                return "neutral", "no_check_suites", pr_html_url

            # Prioritize conclusions: failure > pending > success.
            # GitHub status: 'completed', 'queued', 'in_progress'
            # GitHub conclusion: 'success', 'failure', 'neutral', 'cancelled', 'skipped', 'timed_out', 'action_required'

            overall_status = "success" # Assume success until proven otherwise
            overall_conclusion = "success"
            final_html_url = pr_html_url # Default to PR URL

            pending_found = False
            failure_found = False
            action_required_found = False

            relevant_check_runs_url = None

            for suite in check_suites:
                logger.debug(f"Check Suite: {suite.app.name}, Status: {suite.status}, Conclusion: {suite.conclusion}, URL: {suite.html_url}")

                # Use the URL of the first check suite found (or a specific one if identifiable)
                # The suite.html_url might not be the most direct link to the checks page.
                # Instead, the PR's checks tab URL is often more useful.
                # For now, we'll try to find a specific check run URL or default to PR.

                if suite.conclusion == "failure":
                    overall_status = "failure"
                    overall_conclusion = suite.conclusion
                    failure_found = True
                    # Try to get a more specific URL from check runs
                    check_runs = suite.get_check_runs()
                    for run in check_runs:
                        if run.conclusion == "failure":
                            relevant_check_runs_url = run.html_url
                            break
                    if relevant_check_runs_url: final_html_url = relevant_check_runs_url
                    break # A single failure is enough to mark the whole thing as failed

                if suite.conclusion == "action_required":
                    overall_status = "action_required" # Or consider this 'failure' or 'pending'
                    overall_conclusion = suite.conclusion
                    action_required_found = True
                    # Potentially break or continue to see if there's a hard failure

                if suite.status != "completed": # queued, in_progress
                    pending_found = True
                    # Don't override overall_status if already failure
                    if not failure_found and not action_required_found:
                        overall_status = "pending"
                        overall_conclusion = "pending_suite_status_" + suite.status

                if suite.conclusion and suite.conclusion not in ["success", "neutral", "skipped"] and not failure_found and not action_required_found and not pending_found:
                    # e.g. cancelled, timed_out
                    overall_status = "failure" # Treat these as failures for simplicity
                    overall_conclusion = suite.conclusion

            if pending_found and not failure_found and not action_required_found:
                overall_status = "pending"
                overall_conclusion = "pending_active_checks"

            if not relevant_check_runs_url and pr_html_url:
                # Construct a URL to the checks tab of the PR
                final_html_url = f"{pr_html_url}/checks" if pr_html_url else None


            logger.info(f"Overall CI Status for SHA {sha_to_check} (PR #{pr_number}): {overall_status}, Conclusion: {overall_conclusion}, URL: {final_html_url}")
            return overall_status, overall_conclusion, final_html_url

        except GithubException as e:
            logger.error(f"GitHub API error while fetching CI status for PR #{pr_number}/SHA {sha_to_check}: {e.status} {e.data.get('message', str(e))}")
            return "unknown", f"api_error_{e.status}", pr_html_url
        except Exception as e:
            logger.error(f"Unexpected error fetching CI status for PR #{pr_number}/SHA {sha_to_check}: {e}", exc_info=True)
            return "unknown", "unexpected_error", pr_html_url


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
        main_branch_env = os.getenv("GITHUB_MAIN_BRANCH", "main")
        # Ensure GITHUB_TEST_PR_NUMBER or GITHUB_TEST_HEAD_SHA is set for CI status check example
        test_pr_number_env = os.getenv("GITHUB_TEST_PR_NUMBER")
        test_head_sha_env = os.getenv("GITHUB_TEST_HEAD_SHA")

        # --- Example: Create a PR (comment out if focusing on CI status check) ---
        # head_branch_for_create_example = "test-branch-for-pr-creation-example" # Ensure this branch exists or create it for test
        # logger.info(f"Attempting to create a new PR from branch: {head_branch_for_create_example}")
        # try:
        #     client._repo.get_branch(branch=head_branch_for_create_example)
        #     logger.info(f"Test head branch '{head_branch_for_create_example}' found.")
        #     commits = client.get_commit_messages(head_branch_for_create_example, limit=1)
        #     pr_title_create = f"Test PR Create: {commits[0].splitlines()[0]}" if commits else f"Test PR for branch {head_branch_for_create_example}"
        #     pr_body_create = f"Automated test PR by GitHubClient for `{head_branch_for_create_example}`."
        #     created_pr_url = client.create_pull_request(
        #         title=pr_title_create, body=pr_body_create, head_branch=head_branch_for_create_example, base_branch=main_branch_env
        #     )
        #     if created_pr_url:
        #         logger.info(f"Pull request CREATED successfully: {created_pr_url}")
        #         test_pr_number_env = created_pr_url.split("/")[-1] # Use this new PR for status check
        #     else:
        #         logger.error("Failed to create pull request for example.")
        # except GithubException as ge:
        #     if ge.status == 404: logger.error(f"Branch '{head_branch_for_create_example}' not found. Cannot run create_pull_request example.")
        #     else: logger.error(f"Error with branch '{head_branch_for_create_example}': {ge}")
        # except Exception as ex_create:
        #     logger.error(f"Error in create PR example: {ex_create}")


        # --- Example: Get PR CI Status ---
        if test_pr_number_env:
            logger.info(f"\n--- Checking CI status for PR #{test_pr_number_env} ---")
            status, conclusion, url = client.get_pr_ci_status(pr_number=int(test_pr_number_env))
            logger.info(f"PR #{test_pr_number_env} CI Status: {status}, Conclusion: {conclusion}, URL: {url}")
        elif test_head_sha_env:
            logger.info(f"\n--- Checking CI status for commit SHA {test_head_sha_env} ---")
            status, conclusion, url = client.get_pr_ci_status(head_sha=test_head_sha_env)
            logger.info(f"Commit SHA {test_head_sha_env} CI Status: {status}, Conclusion: {conclusion}, URL: {url}")
        else:
            logger.warning("\nSkipping CI status check example: GITHUB_TEST_PR_NUMBER or GITHUB_TEST_HEAD_SHA env var not set.")
            logger.warning("To test, set one of these to a valid PR number or commit SHA in your GITHUB_REPOSITORY that has CI checks.")


    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
    except Exception as ex:
        logger.error(f"An unexpected error occurred in the example: {ex}", exc_info=True)

    logger.info("GitHubClient direct execution example finished.")
