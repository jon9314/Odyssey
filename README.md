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
    *   This task performs the following in an isolated environment (ideally using Docker, with security features like read-only filesystems and resource limits applied, which are configurable via advanced settings):
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

## Sandbox Infrastructure for Code Validation

To ensure that proposed code changes are safe and functional before being integrated, Odyssey employs a sandbox system. This system is a critical component of the self-modification pipeline, providing an isolated environment for testing.

### Purpose of the Sandbox

The primary goal of the sandbox is to execute and validate proposed code changes without affecting the running application or the main codebase. It aims to:
*   **Isolate Execution:** Prevent proposed code from accessing sensitive host resources, secrets, or unintended network locations.
*   **Verify Functionality:** Confirm that the changes allow the application to build, start, pass health checks, and successfully execute its test suite.
*   **Provide Feedback:** Capture detailed logs and a clear success/failure signal for each validation attempt, which is then used to decide if a proposal can be approved.

### Core Operations (How it Works)

The current sandbox implementation (`Sandbox` class in `odyssey/agent/sandbox.py`) is primarily Docker-based. The core validation method is `run_validation_in_docker()`:

1.  **Input:** It receives an absolute path to a temporary clone of the repository where the specific proposal's branch has already been checked out, and a unique `proposal_id`.
2.  **Dockerfile Check:** It first looks for a `Dockerfile` at the root of the provided repository clone. If not found, validation typically fails.
3.  **Docker Image Build:** It builds a Docker image from this `Dockerfile` using `docker build`. A unique tag is generated for the image (e.g., `odyssey-proposal-<proposal_id>-<random_hex>`). Build logs (stdout, stderr) are captured.
4.  **Docker Container Run:** The newly built image is run as a new Docker container. This step includes:
    *   Assigning a unique container name.
    *   Applying security restrictions:
        *   `--read-only`: Container's root filesystem is read-only.
        *   `--cap-drop=ALL`: All Linux capabilities are dropped.
        *   `--security-opt=no-new-privileges`: Prevents processes from gaining more privileges.
    *   Applying resource limits (configurable via settings):
        *   `--memory <limit>`
        *   `--cpus <limit>` (if specified)
    *   Configurable network mode (defaulting to "bridge").
    *   Port mapping: The application's port inside the container (e.g., 8000) is mapped to a specific host port to enable health checks from the host.
5.  **Application Startup & Health Check:**
    *   After starting the container, the sandbox attempts to verify that the application within the container has started successfully.
    *   It does this by making HTTP GET requests to a configurable health check endpoint (e.g., `http://localhost:<host_port>/health`) in a retry loop for a certain duration.
6.  **Test Execution:**
    *   If the health check passes, the sandbox executes a configurable test command (e.g., `python -m unittest discover -s ./tests`) inside the running container using `docker exec`.
    *   The success or failure of the tests is determined by the exit code of this command. Logs (stdout, stderr) from the test execution are captured.
7.  **Result Aggregation:** The sandbox determines an overall validation success or failure based on the outcomes of the build, container run, health check, and test execution phases.
8.  **Resource Cleanup:** In a `finally` block (ensuring it runs even if errors occur), the sandbox stops and removes the Docker container, and then removes the Docker image that was built.
9.  **Output:** The method returns a tuple: `(success: bool, output_log: str)`, where `output_log` contains a detailed transcript of all operations, including Docker command outputs and internal logging messages.

### Integration with the Self-Modification Pipeline

The sandbox is invoked as part of an asynchronous Celery task:

1.  When a code change is proposed (via `POST /api/v1/self-modify/propose`), the `run_sandbox_validation_task` Celery task is triggered.
2.  This task:
    *   Creates a fresh clone of the main repository in a temporary directory.
    *   Checks out the specific `branch_name` associated with the proposal in this temporary clone.
    *   Instantiates the `Sandbox` class, configuring it with settings from `AppSettings` (e.g., health check endpoint, test command, Docker resource limits).
    *   Instantiates a `SelfModifier` configured to operate on the temporary clone and equipped with the `Sandbox` instance.
    *   Calls `local_self_modifier.sandbox_test(repo_clone_path=temp_repo_dir, proposal_id=proposal_id)`.
    *   The `SelfModifier.sandbox_test()` method directly calls `sandbox_instance.run_validation_in_docker()`.
3.  The success/failure result and the detailed `output_log` from the sandbox are then used by `run_sandbox_validation_task` to update the proposal's record in `MemoryManager` (setting status to "validation_passed" or "validation_failed" and storing the log in `validation_output`).

### Reviewing Sandbox Logs and Proposal Status

Developers and administrators can review the outcome of sandbox validations:

*   **API Endpoints:**
    *   `GET /api/v1/self-modify/proposals/{proposal_id}`: Provides the detailed status for a specific proposal. The `status` field will indicate "validation_passed", "validation_failed", "validation_in_progress", etc. The `validation_output` field contains the comprehensive log from the sandbox operations.
    *   `GET /api/v1/self-modify/proposals`: Lists all proposals, allowing a quick overview of their current statuses.
*   **Interpreting `validation_output`:** This field is key for debugging failed validations. It includes:
    *   Logs from the `Sandbox` class itself detailing each step.
    *   `stdout` and `stderr` from Docker build commands.
    *   `stdout` and `stderr` from Docker run commands (though often minimal for detached containers).
    *   Logs from the health check attempts.
    *   `stdout` and `stderr` from the `docker exec` test command.

### Extending or Modifying the Sandbox

The sandbox system is designed to be adaptable:

*   **Configuration (Easiest Modification):**
    *   Many sandbox behaviors can be tuned via `AppSettings` (defined in `odyssey/agent/main.py` and configurable via environment variables or `.env` files). These include:
        *   `SANDBOX_HEALTH_CHECK_ENDPOINT`
        *   `SANDBOX_APP_PORT_IN_CONTAINER`
        *   `SANDBOX_HOST_PORT_FOR_HEALTH_CHECK`
        *   `SANDBOX_DEFAULT_TEST_COMMAND`
        *   `SANDBOX_DOCKER_MEMORY_LIMIT`
        *   `SANDBOX_DOCKER_CPU_LIMIT`
        *   `SANDBOX_DOCKER_NETWORK`
        *   `SANDBOX_DOCKER_NO_NEW_PRIVILEGES`
    *   Adjusting these settings is the first approach for customizing validation.

*   **Alternative Sandboxing Technologies:**
    *   The core sandboxing logic is encapsulated within the `Sandbox` class, primarily in the `run_validation_in_docker()` method.
    *   To replace Docker with another technology (e.g., Podman, systemd-nspawn, Firecracker, WebAssembly runtimes like Wasmtime/Wasmer if applicable):
        1.  Modify or replace `Sandbox.run_validation_in_docker()` with a new method implementing the desired technology.
        2.  Ensure this new method adheres to the same contract: accepting `repo_clone_path` and `proposal_id`, and returning `(success: bool, output_log: str)`.
        3.  Update `SelfModifier.sandbox_test()` if the method name it calls on the sandbox manager instance changes.
    *   The rest of the pipeline (Celery task, API) would largely remain unchanged as long as this contract is met.

*   **Customizing Validation Steps:**
    *   The sequence of operations (build, run, health check, tests) is currently implemented within `Sandbox.run_validation_in_docker()`. To alter this sequence, add new checks (e.g., linting, security scans), or change how health checks or tests are invoked, this method is the primary place for modification.

*   **Test Scripts and Definitions:**
    *   It's important to remember that the sandbox *provides the environment* for testing; the *actual tests* (e.g., Python unittest files, pytest suites, shell scripts) are part of the codebase of the proposal being validated.
    *   To change what tests are run, you would modify the test scripts within your project and ensure the `SANDBOX_DEFAULT_TEST_COMMAND` (or a custom command for a specific proposal type if you extend the system) correctly invokes them.

### Developer Usage Example for Sandbox Testing (Conceptual)

While the sandbox is primarily invoked by the automated Celery pipeline, a developer might want to test the sandbox mechanism itself or a specific proposal branch more directly. This typically involves:

1.  Ensuring the `odyssey.agent.Sandbox` class is importable.
2.  Having a local clone of the repository with the desired branch checked out.
3.  Writing a small Python script:

    ```python
    # conceptual_sandbox_test.py
    from odyssey.agent.sandbox import Sandbox
    from odyssey.agent.main import AppSettings # To get configurations
    import os
    import logging

    logging.basicConfig(level=logging.DEBUG) # See detailed logs

    if __name__ == "__main__":
        # Load settings to get sandbox configurations
        settings = AppSettings()

        # Path to your local repo clone where the branch is checked out
        repo_path = "/path/to/your/cloned/odyssey_proposal_branch"
        proposal_id_for_test = "dev_test_001"

        # Ensure the path is absolute
        abs_repo_path = os.path.abspath(repo_path)
        if not os.path.isdir(abs_repo_path) or not os.path.exists(os.path.join(abs_repo_path, "Dockerfile")):
            print(f"Error: Path {abs_repo_path} is not a valid directory or does not contain a Dockerfile.")
            exit(1)

        print(f"Testing sandbox with repo: {abs_repo_path}, proposal_id: {proposal_id_for_test}")

        sandbox = Sandbox(
            health_check_endpoint=settings.SANDBOX_HEALTH_CHECK_ENDPOINT,
            app_port_in_container=settings.SANDBOX_APP_PORT_IN_CONTAINER,
            host_port_for_health_check=settings.SANDBOX_HOST_PORT_FOR_HEALTH_CHECK, # Ensure this port is free on host
            test_command=settings.SANDBOX_DEFAULT_TEST_COMMAND.split(), # Or provide custom
            docker_memory_limit=settings.SANDBOX_DOCKER_MEMORY_LIMIT,
            docker_cpu_limit=settings.SANDBOX_DOCKER_CPU_LIMIT,
            docker_network=settings.SANDBOX_DOCKER_NETWORK,
            docker_no_new_privileges=settings.SANDBOX_DOCKER_NO_NEW_PRIVILEGES
        )

        success, output = sandbox.run_validation_in_docker(abs_repo_path, proposal_id_for_test)

        print("\n--- Sandbox Execution Finished ---")
        print(f"Overall Success: {success}")
        print("--- Output Log ---")
        print(output)
        print("--- End of Log ---")
    ```
This script would allow a developer to run the `run_validation_in_docker` method directly on a specified local path, helping to debug the sandbox logic or test a `Dockerfile` and test setup for a proposal.

## Best Practices, Troubleshooting, and Production Considerations

This section provides guidance on best practices, troubleshooting common issues, and considerations for running Odyssey's memory and observability systems effectively, especially in production-like environments.

### I. Data Security and PII (Personally Identifiable Information)

*   **Semantic Memory Content:**
    *   **Be Mindful of Ingested Data:** The semantic memory (vector store) will store and index the text you provide to it via `MemoryManager.add_semantic_memory_event()`. If this source text contains PII or sensitive information, that information will reside in your vector database.
    *   **Recommendation:** Implement data sanitization or anonymization in your data ingestion pipelines *before* feeding text into Odyssey's semantic memory if PII should not be stored or indexed.
*   **Logging (Python & Langfuse):**
    *   **Python Logs:** Odyssey's Python logs aim to use snippets for potentially long or sensitive free-text fields at the `INFO` level (e.g., task descriptions, semantic text snippets). However, `DEBUG` level logs can be very verbose and may include full outputs from sandboxed processes or Docker commands.
        *   **Recommendation:** Avoid running with `DEBUG` level logging in production unless actively troubleshooting a specific issue. Ensure debug logs, if generated, are stored securely and have appropriate retention policies.
    *   **Langfuse Traces:**
        *   LLM prompts and responses are sent to Langfuse, as this is crucial for observability and debugging LLM interactions. If these prompts/responses contain PII, that data will be in your Langfuse instance.
        *   For other operations (memory events, proposal steps), Odyssey generally logs snippets of free-text data and structured metadata. However, entire metadata dictionaries associated with semantic entries or filters used in queries are logged.
        *   **Recommendation:** Be aware of what data is being processed by Odyssey. If PII is involved, understand that it will be part of Langfuse traces. Consider Langfuse's data handling and security features if you are using Langfuse Cloud, or your own security measures if self-hosting Langfuse. For highly sensitive PII, advanced redaction techniques prior to LLM interaction or Langfuse logging might be necessary (this is currently outside Odyssey's built-in capabilities but could be a custom extension).
*   **Configuration Secrets:**
    *   Ensure API keys (like `LANGFUSE_SECRET_KEY`, `OLLAMA_API_KEY` if used, etc.) and other secrets are managed securely, preferably through environment variables or a secrets management system, and *never* hardcoded into the codebase or version control. The `.env` file method is suitable for local development but requires careful handling for production.

### II. Langfuse Observability

*   **Setup & Configuration:**
    *   Ensure `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` environment variables are correctly set for the Odyssey backend and Celery workers.
    *   The default `LANGFUSE_HOST` is `http://localhost:3000`, suitable for the provided `docker-compose.yml` setup. For Langfuse Cloud, use `https://cloud.langfuse.com`.
*   **Troubleshooting Connection Issues:**
    *   **Check Keys/Host:** Double-check that your public key, secret key, and host URL are accurate.
    *   **Network Accessibility:** If self-hosting Langfuse, ensure the Langfuse server is reachable from where the Odyssey backend and Celery workers are running (e.g., correct Docker networking, firewall rules).
    *   **Odyssey Logs:** Check Odyssey's startup logs. The `LangfuseClientWrapper` will log whether it initialized successfully or why it failed (e.g., "Langfuse not configured" or specific connection errors).
    *   **Langfuse Server Logs:** If self-hosting, check the logs of your Langfuse Docker container for any errors.
*   **Understanding Traces in Langfuse UI:**
    *   **LLM Calls:** Traces named like "OllamaClient.ask.StandaloneTrace" or "OllamaClient.generate_embeddings.StandaloneTrace" (or with custom names if provided by the caller) capture individual LLM interactions. Inside these, you'll find a "generation" step with prompt, completion, model, tokens, latency, etc.
    *   **Memory Events:** Events from `MemoryManager` (e.g., "memory_add_task", "memory_semantic_search") are typically logged as distinct events within new traces by default. Metadata will include IDs, snippets of input, and summaries of output.
    *   **Proposal Lifecycle:** Look for "memory_log_proposal_step" events to track the progress of self-modification proposals, identified by `proposal_id` in their metadata.
    *   **Release Version:** Traces are associated with Odyssey's application version (if available), helping to correlate observations with specific code versions.
*   **Managing Data Volume (Advanced):**
    *   Odyssey currently traces most key LLM and memory operations. For very high-throughput systems, the volume of data sent to Langfuse might become a consideration.
    *   Langfuse itself offers features like sampling or you might consider customizing `LangfuseClientWrapper` or its usage points to be more selective about what gets traced if this becomes a concern (e.g., only trace errors or a percentage of successful operations). This is an advanced topic not covered by default.

### III. Vector Store (ChromaDB)

*   **Persistence & Backup:**
    *   ChromaDB is configured to persist data to disk by default (path configured by `VECTOR_STORE_PERSIST_PATH`, e.g., `var/memory/vector_store_chroma/`).
    *   **Recommendation:** Regularly back up this persistence directory as part of your overall data backup strategy.
*   **Monitoring:**
    *   **Disk Space:** Monitor the disk space used by the ChromaDB `persist_directory`, as it will grow with the number of semantic entries.
    *   **System Resources:** Embedding generation (done by Sentence Transformers models) can be CPU-intensive. Querying can also consume CPU and memory. Monitor system resources on the machine running Odyssey, especially if you have a very large vector store or high query/ingestion rates.
*   **Performance Considerations:**
    *   **Embedding Model:** The default `all-MiniLM-L6-v2` is a good balance of quality and performance. Larger models may provide better semantic understanding but will be slower and require more resources for embedding generation.
    *   **Dataset Size:** Query latency can increase with the number of items in the collection.
    *   **Metadata Filters:** Complex `where` clauses in ChromaDB queries can impact performance.
    *   **Hardware:** For large-scale deployments, consider the CPU and RAM available to Odyssey.
*   **Troubleshooting:**
    *   **Initialization Errors:** Check Odyssey's startup logs. `MemoryManager` will log errors if `ChromaVectorStore` fails to initialize (e.g., issues with the persist directory permissions, problems loading the embedding model).
    *   **"ChromaDB library not found" / "SentenceTransformers library not found":** Ensure `chromadb` and `sentence-transformers` are correctly installed in your Python environment (see `odyssey/requirements.txt`).
    *   **Data Corruption (Rare):** If you suspect data corruption in ChromaDB, the primary recovery method is to restore from a backup of the `persist_directory`. You might also try stopping Odyssey, deleting the persist directory (if you have backups or can re-index), and restarting to let ChromaDB create a fresh database.

### IV. General Production Readiness

*   **Configuration Management:** Use environment variables for all sensitive configurations (API keys, secrets) and external service URLs. Do not commit secrets to version control.
*   **Dependency Updates:** Regularly update Python dependencies (including `langfuse`, `chromadb`, `fastapi`, `celery`, etc.) to benefit from security patches and bug fixes.
*   **API Security:** Secure your Odyssey API endpoints appropriately (e.g., authentication, authorization, rate limiting) if exposing them beyond a trusted local environment.
*   **Resource Allocation:** Ensure sufficient CPU, memory, and disk resources for all components of Odyssey (FastAPI backend, Celery workers, Ollama, Langfuse, vector database).

## Semantic Memory (Vector Store)

Beyond its structured SQLite memory, Odyssey incorporates a semantic memory system powered by a vector store. This allows the agent to store textual information (like events, logs, observations, or document chunks) and retrieve it based on semantic similarity rather than exact keyword matches.

### Purpose

*   **Long-term Associative Memory:** Enables the agent to recall relevant past experiences or information even if the query uses different wording.
*   **Contextual Understanding:** Provides richer context for decision-making by finding semantically related information.
*   **Knowledge Base:** Can be used to build and query a knowledge base from various text sources.

### Current Implementation: ChromaDB

*   **Backend:** The current implementation uses [ChromaDB](https://www.trychroma.com/) as the vector database.
*   **Embeddings:** Text is converted into numerical embeddings (vectors) using a Sentence Transformer model (default: `all-MiniLM-L6-v2`). These embeddings capture the semantic meaning of the text.
*   **Persistence:** ChromaDB is configured to persist its data on disk (default path: `var/memory/vector_store_chroma/`), so semantic memories are retained across agent restarts.
*   **Interface:** A `VectorStoreInterface` (`odyssey/agent/vector_store.py`) defines the standard operations, with `ChromaVectorStore` being the concrete implementation.

### Integration with MemoryManager

The `MemoryManager` (`odyssey/agent/memory.py`) handles interactions with the vector store:

*   **Initialization:** `MemoryManager` initializes the `ChromaVectorStore` during its setup. Configuration parameters like the persistence path, collection name, and embedding model name can be adjusted in `AppSettings` (see `odyssey/agent/main.py`).
*   **Adding Semantic Data:**
    *   Use `MemoryManager.add_semantic_memory_event(text: str, metadata: dict, event_id: Optional[str] = None)`
    *   This method takes a string of text, a dictionary of metadata (e.g., `{"source": "log", "type": "error"}`), and an optional unique ID. It then adds this information to the vector store.
*   **Querying Semantic Data:**
    *   Use `MemoryManager.semantic_search(query_text: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None)`
    *   This method takes a query string, the desired number of results (`top_k`), and an optional metadata filter (e.g., `{"source": "log"}`).
    *   It returns a list of the most semantically similar documents, including their original text, metadata, ID, and distance (similarity score).

### Setup and Dependencies

1.  **Installation:** The necessary Python libraries are `chromadb` and `sentence-transformers`. These should be included in `odyssey/requirements.txt`. If you set up the project following the main instructions, these will be installed.
    ```bash
    pip install chromadb sentence-transformers
    ```
2.  **Configuration (Optional):**
    *   The default persistence path for ChromaDB is `var/memory/vector_store_chroma/`.
    *   The default embedding model is `all-MiniLM-L6-v2`.
    *   These can be changed via environment variables corresponding to `AppSettings` in `odyssey/agent/main.py`:
        *   `VECTOR_STORE_PERSIST_PATH`
        *   `VECTOR_STORE_COLLECTION_NAME`
        *   `EMBEDDING_MODEL_NAME` (Note: This is the `embedding_model_name` parameter for `MemoryManager` which is then passed to `ChromaVectorStore`).

### Example Usage (Conceptual via MemoryManager)

```python
# Assuming 'memory' is an initialized MemoryManager instance

# Add an event to semantic memory
event_text = "The agent learned a new skill: advanced data analysis."
event_meta = {"category": "skill_acquisition", "timestamp": "2023-11-15T10:00:00Z"}
event_id = memory.add_semantic_memory_event(text=event_text, metadata=event_meta)
if event_id:
    print(f"Added semantic event with ID: {event_id}")

# Perform a semantic search
query = "What new abilities did the agent gain recently?"
results = memory.semantic_search(query_text=query, top_k=3)
for res in results:
    print(f"Found: {res['text']} (Distance: {res['distance']:.4f}, Metadata: {res['metadata']})")
```

This system provides a powerful way for Odyssey to build and utilize a rich, context-aware memory.

## Observability with Langfuse

Odyssey integrates with [Langfuse](https://langfuse.com/) for comprehensive observability, tracing, and debugging of its operations, especially those involving Large Language Models (LLMs) and memory interactions.

### Purpose

Using Langfuse allows developers and operators to:
*   **Trace Complex Flows:** Understand the sequence of operations within the agent, such as an LLM call followed by memory access and then another LLM call.
*   **Debug LLM Interactions:** Inspect the exact prompts sent to LLMs, the responses received, model parameters used, and latency.
*   **Monitor Memory Operations:** Track when and what data is added to or retrieved from structured (SQLite) and semantic (vector store) memory.
*   **Analyze Self-Modification Pipeline:** Observe the lifecycle of code change proposals, from submission through validation and merging.
*   **Evaluate Performance:** Use Langfuse's scoring and analytics features to assess the quality and effectiveness of different agent behaviors or LLM prompts over time.

### Setup and Configuration

To enable Langfuse integration, you need to configure the following environment variables (e.g., in your `.env` file):

*   **`LANGFUSE_PUBLIC_KEY`**: Your Langfuse project's Public Key.
*   **`LANGFUSE_SECRET_KEY`**: Your Langfuse project's Secret Key.
*   **`LANGFUSE_HOST`**: The URL of your Langfuse server instance.
    *   For Langfuse Cloud: `https://cloud.langfuse.com`
    *   For self-hosted Langfuse (e.g., via the project's `docker-compose.yml`): `http://localhost:3000` (this is the default if not set).

If these variables are set, Odyssey's `LangfuseClientWrapper` will be activated upon startup and begin sending data to your Langfuse project. If they are not set, Langfuse integration will be disabled, and the agent will log a message indicating this.

The Odyssey agent version is also passed as the `release` to Langfuse, helping to correlate observations with specific code versions.

### Key Instrumented Operations

Odyssey is instrumented to send traces and events to Langfuse for several key operations:

*   **LLM Calls (`OllamaClient`):**
    *   Each call to `OllamaClient.ask()` (for text generation) and `OllamaClient.generate_embeddings()` creates a Langfuse trace (or a child generation if part of an existing trace).
    *   Logged data includes:
        *   Prompt (and system prompt, if used).
        *   Response/completion (or an error message).
        *   Model name requested and model actually used.
        *   Instance type used (local/remote Ollama).
        *   Timings (latency).
        *   Any options passed to Ollama (e.g., temperature).
        *   Token usage (if available from Ollama's response).

*   **Memory Operations (`MemoryManager`):**
    *   **Structured Memory:**
        *   `add_task`: Logs task ID, description.
        *   `update_task_status`: Logs task ID, new status.
        *   `add_plan`: Logs plan ID, details preview.
        *   `log_event` (DB log): Logs internal agent events written to SQLite.
    *   **Semantic Memory (Vector Store):**
        *   `add_semantic_memory_event`: Logs document ID, text snippet, metadata.
        *   `semantic_search`: Logs query snippet, `top_k`, filter, number of results, and ID of the first result.
    *   **Self-Modification Pipeline:**
        *   `log_proposal_step`: Logs proposal ID, branch, status, commit message snippet, validation output snippet, and approver for each step in a proposal's lifecycle.

### Viewing Traces in Langfuse

Once configured, you can access your Langfuse instance (Cloud or self-hosted UI) to:
*   View detailed traces of agent operations.
*   Filter and search for specific events or generations.
*   Analyze latencies and token usage.
*   Add scores and comments to traces for evaluation.

This integration provides deep insights into the agent's internal workings, aiding in development, debugging, and performance monitoring.

#### API Access for Semantic Memory

You can interact with the semantic memory via the following API endpoints:

*   **`POST /api/v1/memory/semantic/add`**
    *   **Description:** Adds a new text entry with associated metadata to the vector store.
    *   **Request Body (`SemanticAddRequest`):**
        ```json
        {
          "text": "The agent discovered a new planetary system in the Andromeda galaxy.",
          "metadata": {"source": "astronomy_log", "discovery_type": "planetary_system", "year": 2024},
          "id": "optional_unique_id_for_this_entry"
        }
        ```
        *(Note: `id` is optional; if not provided, one will be generated.)*
    *   **Response (201 Created - `SemanticAddResponse`):**
        ```json
        {
          "id": "generated_or_provided_id",
          "message": "Semantic entry added successfully."
        }
        ```
    *   **Curl Example:**
        ```bash
        curl -X POST -H "Content-Type: application/json" \
        -d '{
          "text": "Agent status nominal after system update.",
          "metadata": {"type": "system_status", "component": "core_agent"}
        }' \
        http://localhost:8000/api/v1/memory/semantic/add | jq
        ```

*   **`POST /api/v1/memory/semantic/query`**
    *   **Description:** Queries the vector store for entries semantically similar to the `query_text`.
    *   **Request Body (`SemanticQueryRequest`):**
        ```json
        {
          "query_text": "recent system anomalies or errors",
          "top_k": 3,
          "metadata_filter": {"type": "system_error"}
        }
        ```
        *(Note: `top_k` defaults to 5, `metadata_filter` is optional.)*
    *   **Response (200 OK - `SemanticQueryResponse`):**
        ```json
        {
          "results": [
            {
              "id": "error_billing_001",
              "text": "A critical error occurred in the billing module during an update.",
              "metadata": {"type": "system_error", "module": "billing", "severity": "critical"},
              "distance": 0.12345
            }
            // ... other similar results up to top_k
          ]
        }
        ```
    *   **Curl Example:**
        ```bash
        curl -X POST -H "Content-Type: application/json" \
        -d '{
          "query_text": "agent activities related to data analysis",
          "top_k": 2
        }' \
        http://localhost:8000/api/v1/memory/semantic/query | jq
        ```

*   **`POST /api/v1/memory/hybrid/query`**
    *   **Description:** Performs a hybrid query, fetching results from semantic search (vector store) based on `query_text` and optionally including structured data (tasks, DB logs, plans, self-modification proposals) based on `structured_options`.
    *   **Request Body (`HybridQueryRequestSchema`):**
        ```json
        {
          "query_text": "recent agent errors and related tasks",
          "semantic_top_k": 3,
          "semantic_metadata_filter": null, // Optional: e.g., {"type": "system_error"}
          "structured_options": { // Optional: include this whole block to fetch structured data
            "include_tasks": true,
            "task_status_filter": "pending", // Optional
            "task_limit": 2,
            "include_db_logs": true,
            "db_log_level_filter": "ERROR", // Optional
            "db_log_limit": 2,
            "include_plans": false,
            "plan_limit": 1,
            "include_proposals": true,
            "proposal_limit": 1
          }
        }
        ```
    *   **Response (200 OK - `HybridQueryResponseSchema`):**
        ```json
        {
          "query_text": "recent agent errors and related tasks",
          "results": [
            {
              "source_type": "semantic_match",
              "content": {
                "id": "error_billing_001",
                "text": "A critical error occurred in the billing module...",
                "metadata": {"type": "system_error", "...": "..."},
                "distance": 0.123
              },
              "relevance_score": 0.877, // Example: 1.0 - distance
              "timestamp": "2023-11-15T10:00:00Z" // If available in metadata
            },
            {
              "source_type": "task",
              "content": {
                "id": 105,
                "description": "Fix critical bug #123 in the UI related to billing errors",
                "status": "pending",
                "timestamp": "2023-11-14T09:00:00Z"
              },
              "relevance_score": null, // Or some future keyword-based score
              "timestamp": "2023-11-14T09:00:00Z"
            },
            {
              "source_type": "db_log",
              "content": {
                "id": 210,
                "message": "Billing module update failed: NullPointerException",
                "level": "ERROR",
                "timestamp": "2023-11-15T09:55:00Z"
              },
              "relevance_score": null,
              "timestamp": "2023-11-15T09:55:00Z"
            }
            // ... other results, sorted by timestamp descending by default
          ]
        }
        ```
    *   **Curl Example:**
        ```bash
        curl -X POST -H "Content-Type: application/json" \
        -d '{
          "query_text": "issues with billing module",
          "semantic_top_k": 2,
          "structured_options": {
            "include_db_logs": true,
            "db_log_level_filter": "ERROR",
            "db_log_limit": 3,
            "include_tasks": true,
            "task_limit": 2
          }
        }' \
        http://localhost:8000/api/v1/memory/hybrid/query | jq
        ```

*(For error responses, such as when the vector store is unavailable (503) or for bad requests (400), the API will return a JSON object like `{"error": "Error message", "detail": "Optional further details"}`.)*
