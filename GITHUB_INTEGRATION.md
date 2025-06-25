# GitHub Integration for Odyssey Self-Modification

This document outlines how to configure Odyssey to allow it to create branches, push changes, and open Pull Requests (PRs) on GitHub automatically.

## Configuration

The GitHub integration relies on several environment variables for authentication and repository information.

### Required Environment Variables

1.  **`GITHUB_TOKEN`**:
    *   **Description**: A GitHub Personal Access Token (PAT) that grants Odyssey permission to interact with your repository.
    *   **Required Scopes**: The PAT needs the `repo` scope to allow for operations like creating branches, pushing code, and opening/merging pull requests. If you want to use fine-grained PATs, ensure it has `Read and Write` access for `Contents` and `Pull requests`.
    *   **How to Generate**:
        1.  Go to your GitHub account settings.
        2.  Navigate to **Developer settings** > **Personal access tokens** > **Tokens (classic)** or **Fine-grained tokens**.
        3.  Click **Generate new token**.
        4.  Give the token a descriptive name (e.g., "odyssey_agent_pat").
        5.  Select the expiration period for the token.
        6.  Under **Scopes** (for classic PATs), select the `repo` scope.
        7.  For **Fine-grained tokens**:
            *   Select the **Resource owner**.
            *   Choose **Only select repositories** and pick the repository Odyssey will work with.
            *   Under **Repository permissions**:
                *   Set **Contents** to `Read and write`.
                *   Set **Pull requests** to `Read and write`.
                *   (Optional) You might need `Read` access for **Metadata** (usually default).
        8.  Click **Generate token** and copy the token immediately. You will not be able to see it again.
    *   **Security Note**: Treat this token like a password. Do not hardcode it into your source code. Store it securely, for example, in a `.env` file that is not committed to version control, or as a secret in your deployment environment.

2.  **`GITHUB_REPOSITORY`**:
    *   **Description**: The full name of the GitHub repository that Odyssey will interact with.
    *   **Format**: `owner/repository_name` (e.g., `my-username/my-odyssey-project`).
    *   **Example**: `GITHUB_REPOSITORY="your-github-username/your-repo"`

3.  **`MAIN_BRANCH_NAME`** (Optional):
    *   **Description**: The name of the main development branch in your repository where pull requests should typically be targeted.
    *   **Default**: If not set, Odyssey defaults to using `"main"`.
    *   **Example**: `MAIN_BRANCH_NAME="develop"` or `MAIN_BRANCH_NAME="master"`

### How Odyssey Uses These Variables

*   The `SelfModifier` class in `odyssey/agent/self_modifier.py` and the `GitHubClient` class in `odyssey/agent/github_client.py` will automatically attempt to read these environment variables during initialization if the corresponding parameters (`github_token`, `github_repo_name`, `main_branch_name`) are not explicitly passed to their constructors.

## Usage Notes

*   **Branch Naming**: When Odyssey proposes changes, it will create a new branch. The branch name is typically generated based on a prefix (e.g., "proposal"), a unique ID, and a sanitized version of the commit message.
*   **Pull Request (PR) Creation**:
    *   After pushing changes to the new branch, Odyssey will attempt to create a PR.
    *   The PR title will usually be derived from the first line of the commit message on the new branch.
    *   The PR body will be automatically generated and may include a proposal ID if provided during the operation.
*   **Logging**: Information about branch creation, PR URLs, and any errors encountered during GitHub operations will be logged by the application. This is helpful for tracking and debugging. (The prompt mentioned storing PR URL/status in `MemoryManager` and updating a proposal log; currently, this is handled via standard Python logging. True `MemoryManager` integration would be a further enhancement).
*   **Error Handling**:
    *   The system includes basic retry mechanisms for transient network errors when interacting with the GitHub API.
    *   If a PR already exists for a given head branch to a base branch, the system will log this and return the URL of the existing PR if found.
    *   If the `GITHUB_TOKEN` is missing or invalid, or if the `gh` CLI (fallback mechanism) is not configured, PR creation will fail, and errors will be logged.
*   **`gh` CLI Fallback**: If the `GITHUB_TOKEN` is not available or `GitHubClient` fails to initialize, `SelfModifier` may attempt to use the GitHub CLI (`gh`) for operations like creating PRs. For this to work, the `gh` CLI must be installed and authenticated in the environment where Odyssey is running. However, for fully automated workflows, relying on the `GITHUB_TOKEN` and PyGithub is recommended.

## Enabling the Feature

1.  Ensure you have `PyGithub` installed (it's added to `odyssey/requirements.txt`). If not, run `pip install -r odyssey/requirements.txt`.
2.  Set the environment variables `GITHUB_TOKEN` and `GITHUB_REPOSITORY` in your environment (e.g., in your shell, a `.env` file loaded by your application, or your deployment configuration).
3.  Optionally, set `MAIN_BRANCH_NAME` if your main branch is not named "main".

Once configured, when Odyssey's self-modification features are triggered to propose and apply code changes, it should automatically handle pushing to a new branch and creating a pull request.
