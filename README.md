# Odyssey: A Self-Rewriting AI Agent

Odyssey is an open-source AI agent that can rewrite its own code, manage tasks, and grow its own capabilities over time.  
It uses Ollama-hosted LLMs, a hybrid memory system, and a plugin-based architecture for safe, observable self-improvement.

## Features

- **Self-Rewriting:** Proposes, tests, and merges its own code changes via GitHub.
- **Dual LLMs:** Uses both a local CPU model and a LAN-based GPU model via Ollama.
- **Hybrid Memory:** Combines SQLite (structured), Chroma/FAISS (vector/semantic), and JSON (backup); all actions observable via Langfuse.
- **Web UI:** Manage tasks, logs, memory, and agent config in your browser.
- **Extensible Tools:** Easily add plugins (file ops, calendar, OCR, browser, etc).
- **Dockerized:** Backend, frontend, Valkey, Langfuse, and Ollama all run with Docker Compose.

## Quickstart

### 1. Clone & Configure

```sh
git clone https://github.com/your-org/odyssey.git
cd odyssey
cp config/settings.example.yaml config/settings.yaml
cp .env.example .env
# Edit configs as needed (Ollama endpoints, secrets)

## Self-Modification Pipeline

Odyssey can modify its own codebase through a structured, multi-step pipeline. This process ensures changes are proposed, validated in an isolated environment, and then explicitly approved before being merged.

### Workflow

The self-modification workflow consists of the following stages:

1.  **Propose Change:**
    *   An agent (or a user via the API) identifies a need for a code modification.
    *   A proposal is submitted, including the specific file contents to be changed/added and a descriptive commit message.
    *   The system receives this proposal, creates a new Git branch with a unique name (e.g., `proposal/prop_xxxxxxxxxx_description`), applies the file changes, and commits them to this new branch.
    *   The proposal is logged in the `MemoryManager` with an initial status like "proposed".

2.  **Validate Change:**
    *   Upon successful proposal submission, an asynchronous background task (`run_sandbox_validation_task`) is automatically triggered.
    *   This task performs the following in an isolated environment (ideally using Docker):
        *   Clones the repository to a temporary, isolated location.
        *   Checks out the specific proposal branch.
        *   **Build & Startup (if applicable):** If the project involves a build step or runs as a service (e.g., defined by a `Dockerfile`), it attempts to build and start it.
        *   **Health Checks (if applicable):** Performs health checks to ensure the service started correctly.
        *   **Run Tests:** Executes automated tests (e.g., unit tests, integration tests) defined in the project.
    *   The validation task captures all output (stdout, stderr) from these steps.
    *   The proposal's status in `MemoryManager` is updated throughout this process (e.g., "validation_in_progress", "validation_passed", "validation_failed"), and the captured output is stored.

3.  **Review Proposal:**
    *   Users or other agent processes can monitor the status of proposals using the API.
    *   They can list all proposals or fetch the detailed status and validation output for a specific proposal.

4.  **Approve or Reject:**
    *   **Approval:** If the validation stage was successful (status "validation_passed"), the proposal can be approved. This typically requires an explicit action from a user or a trusted automated process.
    *   **Rejection:** A proposal can be rejected at any point, especially if validation fails or if the proposed change is deemed undesirable.
    *   The approval or rejection action updates the proposal's status in `MemoryManager`.

5.  **Merge Change (if Approved):**
    *   Upon approval, another asynchronous background task (`merge_approved_proposal_task`) is triggered.
    *   This task uses the `SelfModifier` component to:
        *   Check out the main development branch (e.g., "main").
        *   Merge the approved proposal branch into the main branch.
        *   Push the updated main branch to the remote repository.
        *   Optionally, delete the merged proposal branch (both local and remote).
    *   The proposal's status in `MemoryManager` is updated to "merge_in_progress" and then to "merged" upon success, or "merge_failed" if issues occur (e.g., merge conflicts that cannot be automatically resolved).

### API Endpoints

The following API endpoints are available for managing the self-modification pipeline. All endpoints are prefixed with `/api/v1`.

*   **`POST /self-modify/propose`**
    *   **Description:** Submits a new code change proposal.
    *   **Request Body:**
        ```json
        {
          "files_content": {
            "path/to/file1.py": "new content for file1...",
            "another/path/file2.txt": "content for file2..."
          },
          "commit_message": "feat: Implement new feature X and update documentation",
          "branch_prefix": "feature" // Optional, defaults to "proposal"
        }
        ```
    *   **Response (202 Accepted):**
        ```json
        {
          "proposal_id": "prop_abc123xyz",
          "branch_name": "feature/prop_abc123xyz_implement_new_feature",
          "status": "validation_pending", // Or "proposed" initially, then quickly "validation_pending"
          "message": "Proposal submitted successfully. Code changes created, logged, and validation task triggered."
        }
        ```

*   **`GET /self-modify/proposals`**
    *   **Description:** Lists all self-modification proposals and their current statuses.
    *   **Query Parameters:**
        *   `limit` (int, optional, default: 50): Maximum number of proposals to return.
    *   **Response (200 OK):** An array of proposal status objects.
        ```json
        [
          {
            "proposal_id": "prop_abc123xyz",
            "branch_name": "feature/prop_abc123xyz_implement_new_feature",
            "commit_message": "feat: Implement new feature X and update documentation",
            "status": "validation_passed",
            "validation_output": "All tests passed. Docker build successful...",
            "created_at": "2023-10-27T10:30:00Z",
            "updated_at": "2023-10-27T10:45:00Z",
            "approved_by": null
          },
          // ... other proposals
        ]
        ```

*   **`GET /self-modify/proposals/{proposal_id}`**
    *   **Description:** Returns the full log/status for a specific proposal.
    *   **Path Parameter:** `proposal_id` (string, required).
    *   **Response (200 OK):** A single proposal status object (same structure as array elements above).
    *   **Response (404 Not Found):** If the proposal ID does not exist.

*   **`POST /self-modify/proposals/{proposal_id}/approve`**
    *   **Description:** Marks a proposal as approved (if validation passed) and triggers the merge process.
    *   **Path Parameter:** `proposal_id` (string, required).
    *   **Response (200 OK):**
        ```json
        {
          "proposal_id": "prop_abc123xyz",
          "branch_name": "feature/prop_abc123xyz_implement_new_feature",
          "status": "merge_pending", // Or "user_approved" initially, then quickly "merge_pending"
          "message": "Proposal 'prop_abc123xyz' approved by api_user. Merge task triggered."
        }
        ```
    *   **Response (404 Not Found):** If proposal ID does not exist.
    *   **Response (409 Conflict):** If the proposal is not in a state that can be approved (e.g., "validation_failed").

*   **`POST /self-modify/proposals/{proposal_id}/reject`**
    *   **Description:** Marks a proposal as rejected.
    *   **Path Parameter:** `proposal_id` (string, required).
    *   **Response (200 OK):**
        ```json
        {
          "proposal_id": "prop_abc123xyz",
          "branch_name": "feature/prop_abc123xyz_implement_new_feature",
          "status": "rejected",
          "message": "Proposal 'prop_abc123xyz' has been successfully rejected."
        }
        ```
    *   **Response (404 Not Found):** If proposal ID does not exist.

### Example API Calls (using `curl`)

Replace `YOUR_PROPOSAL_ID` with an actual ID obtained from the propose step.

1.  **Propose a new change:**
    ```bash
    curl -X POST -H "Content-Type: application/json" \
    -d '{
      "files_content": {
        "src/odyssey/agent/new_module.py": "def hello():\n  print(\"Hello from new module!\")"
      },
      "commit_message": "feat: Add new_module with hello function",
      "branch_prefix": "dev"
    }' \
    http://localhost:8000/api/v1/self-modify/propose | jq
    ```
    *(Capture the `proposal_id` and `branch_name` from the response for subsequent calls.)*

2.  **List all proposals:**
    ```bash
    curl -X GET http://localhost:8000/api/v1/self-modify/proposals | jq
    ```

3.  **Get status of a specific proposal:**
    ```bash
    curl -X GET http://localhost:8000/api/v1/self-modify/proposals/YOUR_PROPOSAL_ID | jq
    ```
    *(Wait for validation to complete. Check status; it should be `validation_passed` or `validation_failed`.)*

4.  **Approve a validated proposal:**
    *(Only if status from step 3 is `validation_passed`)*
    ```bash
    curl -X POST http://localhost:8000/api/v1/self-modify/proposals/YOUR_PROPOSAL_ID/approve | jq
    ```
    *(Monitor Celery logs and Git repository for merge. Check status again with GET endpoint; should eventually be `merged`.)*

5.  **Reject a proposal:**
    ```bash
    curl -X POST http://localhost:8000/api/v1/self-modify/proposals/YOUR_PROPOSAL_ID/reject | jq
    ```

### Approval Mode

Odyssey supports two approval modes for self-modification proposals, configurable via the `SELF_MOD_APPROVAL_MODE` setting (in your `.env` file or environment variables):

*   **`manual`** (Default and Recommended):
    *   After a proposal's changes have been successfully validated in the sandbox (status: `validation_passed`), it requires explicit approval via the `POST /api/v1/self-modify/proposals/{proposal_id}/approve` API endpoint before it can be merged.
    *   This is the safest mode, ensuring a human or a trusted external system reviews validated changes.

*   **`auto`**:
    *   If a proposal successfully passes the sandbox validation (status: `validation_passed`), the system will automatically:
        1.  Mark the proposal as "auto_approved" (with `approved_by: system_auto_approval`).
        2.  Immediately trigger the `merge_approved_proposal_task` to merge the changes into the main development branch.
        3.  Update the status to "merge_pending".
    *   No manual API call to the `/approve` endpoint is needed in this mode.

**Configuration:**

To enable auto-approval, set the environment variable:
```ini
SELF_MOD_APPROVAL_MODE=auto
```
Or, if using a primary YAML configuration that `pydantic-settings` reads before environment variables, you could define it there:
```yaml
# In config/settings.yaml (example)
SELF_MOD_APPROVAL_MODE: auto
```
However, environment variables typically take precedence with `pydantic-settings`.

⚠️ **Warning:** The `auto` approval mode is potentially risky as it allows the agent to merge code into its main branch without direct human intervention after validation. While the validation step aims to ensure code quality and safety, it might not catch all issues. **Use `auto` mode with extreme caution, preferably only in isolated test environments or when the validation pipeline is exceptionally robust and trusted.**
