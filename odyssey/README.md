# Odyssey: A Self-Rewriting AI Agent

Odyssey is an open-source AI agent that can rewrite its own code, manage tasks, and grow its own capabilities over time.
It uses Ollama-hosted LLMs, a hybrid memory system, and a plugin-based architecture for safe, observable self-improvement.

## Project Structure (Simplified)

```
odyssey/
├── agent/                  # Core agent logic (main.py, self_modifier.py, memory.py, etc.)
├── api/                    # FastAPI backend (routes.py, schemas.py)
├── frontend/               # Web interface (React/HTMX)
├── config/                 # Configuration files (settings.yaml, secrets.env)
├── scripts/                # Utility scripts (bootstrap.sh, test_runner.py)
├── plugins/                # Extendable tools for the agent
├── tests/                  # Unit and integration tests
├── .env                    # Actual environment variables (gitignored)
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md               # This file
└── LICENSE
```

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
git clone https://github.com/your-org/odyssey.git # Replace with your actual repo URL
cd odyssey
cp config/settings.yaml config/settings.yaml.example # If you have an example settings
cp config/secrets.env .env # Bootstrap script might also handle this
# Edit .env and config/settings.yaml as needed (Ollama endpoints, secrets)
```
*Ensure `config/secrets.env` serves as a template for `.env` which is gitignored.*
*The `bootstrap.sh` script from the initial setup should help create `.env`.*

### 2. Spin Up Services
To run Odyssey with all currently integrated services (Backend, Valkey, Celery Worker, and Frontend):
```sh
docker compose up --build -d
```
*The `-d` flag runs services in detached mode. The `--build` flag ensures images are rebuilt if Dockerfiles or contexts have changed.*

To view logs from all services:
```sh
docker compose logs -f
```
Or for a specific service (e.g., `backend` or `frontend` or `celery_worker`):
```sh
docker compose logs -f backend
```

### Web UI Quickstart
A minimal React-based web interface is available to interact with some of Odyssey's features.

**Accessing the UI (via Docker Compose):**
Once all services are running with `docker compose up`, the UI should be accessible at:
`http://localhost:5173` (This is Vite's default development port. If you configured it to 3000, use that.)

**Local Development (Frontend Only):**
If you want to run the frontend development server directly on your host machine (e.g., for faster iteration on UI changes):
1.  Navigate to the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    # or if you prefer yarn: yarn install
    ```
3.  Start the development server:
    ```bash
    npm run dev
    # or yarn dev
    ```
    This will typically open the UI in your browser, usually at `http://localhost:5173`.

**API URL and CORS:**
*   The frontend is configured to make API calls to the backend at `http://localhost:8000/api/v1` (this is configurable via `VITE_API_BASE_URL` in `frontend/.env` or through Docker Compose environment variables for the `frontend` service).
*   The backend (FastAPI) has CORS (Cross-Origin Resource Sharing) enabled in `agent/main.py` to allow requests from `http://localhost:5173` and `http://localhost:3000`. If you run the frontend on a different port locally, you may need to add that port to the `origins` list in `agent/main.py`.

### Quick Test: Checking Backend Endpoints
Once the `backend` service is running (either as part of `docker compose up` or `docker compose up backend`), you can test its basic endpoints:

1.  **Root Endpoint:**
    Open your browser or use `curl` to access `http://localhost:8000/`.
    You should see a JSON response like:
    ```json
    {
      "message": "Odyssey backend is running",
      "status": "ok",
      "version": "0.1.0"
    }
    ```
    *(The version might change)*

2.  **Health Check Endpoint:**
    Access `http://localhost:8000/health`.
    You should see:
    ```json
    {
      "status": "ok"
    }
    ```

These tests confirm that the FastAPI backend is running correctly within Docker and accessible from your host machine.

### Memory Quickstart (Prototype)
The agent now has a basic SQLite-based memory system for tasks, plans, and logs, accessible via API. This is a prototype and will be expanded with semantic search and other features later.

**1. Add a new task:**
```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
-H "Content-Type: application/json" \
-d '{"description": "Draft initial project proposal"}'
```
Expected response (ID and timestamp will vary):
```json
{
  "id": 1,
  "description": "Draft initial project proposal",
  "status": "pending",
  "timestamp": "2023-10-27T10:00:00.000000"
}
```

**2. Get all tasks:**
```bash
curl "http://localhost:8000/api/v1/tasks"
```
Or with a limit: `curl "http://localhost:8000/api/v1/tasks?limit=5"`

**3. Get agent logs (from memory, not application logs):**
```bash
curl "http://localhost:8000/api/v1/logs"
```
To filter by level: `curl "http://localhost:8000/api/v1/logs?level=ERROR"`

**Note:** The MemoryManager also includes stubs for `plans` which can be interacted with similarly via `/api/v1/plans` (POST to create, GET to list).

### LLM Connectivity
Odyssey can connect to Ollama-hosted language models, supporting both a local instance (e.g., for CPU-based models) and an optional remote instance (e.g., for GPU-accelerated models on your LAN).

**Configuration:**

1.  Ensure you have Ollama running (locally and/or remotely). You can pull models using `ollama pull <model_name>` (e.g., `ollama pull phi3`).
2.  In your `.env` file (create it from `config/secrets.env` if it doesn't exist), configure the URLs:
    ```env
    OLLAMA_LOCAL_URL="http://localhost:11434"
    OLLAMA_REMOTE_URL="http://your-remote-ollama-ip:11434" # Optional, leave blank if not used
    OLLAMA_DEFAULT_MODEL="phi3" # Model to use if 'auto' is specified
    ```
    Replace `your-remote-ollama-ip` with the actual IP address of your remote Ollama server. If you're only using a local instance, you can leave `OLLAMA_REMOTE_URL` blank or comment it out.

### GitHub Integration for Pull Requests
For Odyssey to automatically create Pull Requests (PRs) for its proposed code changes, you need to configure GitHub access:

1.  **Generate a GitHub Personal Access Token (PAT):**
    *   Go to your GitHub settings: [github.com/settings/tokens](https://github.com/settings/tokens).
    *   Click "Generate new token" (select Classic or Fine-grained).
        *   **Classic Token:** Give it a descriptive name (e.g., "odyssey-agent-pr"). Select the expiration that suits you. For scopes, you need:
            *   `repo` (Full control of private repositories) if your target repository is private.
            *   `public_repo` (Access public repositories) if your target repository is public and you only need to operate on public aspects. For creating PRs, `repo` is generally safer if you might work with private repos or need full capabilities.
        *   **Fine-grained Token:** Select resource owner, then choose repository access (all or select). For "Repository permissions", you will need at least:
            *   `Contents: Read and write`
            *   `Pull requests: Read and write`
    *   Click "Generate token" and **copy the token immediately**. You won't be able to see it again.

2.  **Set Environment Variables:**
    In your `.env` file, add the following (using the token you just copied):
    ```env
    GITHUB_TOKEN="your_copied_github_personal_access_token"
    GITHUB_REPO_OWNER="your_github_username_or_organization_name" # e.g., "octocat"
    GITHUB_REPO_NAME="your_repository_name" # e.g., "odyssey"
    ```
    *   `GITHUB_TOKEN`: The PAT you generated.
    *   `GITHUB_REPO_OWNER`: The username of the account or the name of the organization that owns the repository where PRs will be created.
    *   `GITHUB_REPO_NAME`: The name of the repository itself.

With these settings, `SelfModifier` will be able to use the GitHub API to create branches and open pull requests.

**API Usage (`/llm/ask`):**

You can send prompts to the LLM via the `/api/v1/llm/ask` endpoint.

*   **Basic Prompt (uses default model, prefers local instance):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/llm/ask" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Explain the concept of recursion in one sentence."}'
    ```

*   **Specify Model and Hint for Remote Instance (safe=false):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/llm/ask" \
    -H "Content-Type: application/json" \
    -d '{
          "prompt": "Write a short Python function to calculate factorial using recursion.",
          "model": "deepseek-coder:6.7b", # Example model, ensure it is available on an instance
          "safe": false, # Hint to prefer remote/GPU instance if available
          "system_prompt": "You are a coding assistant. Provide only the code."
        }'
    ```

Expected response structure:
```json
{
  "response": "The LLM's answer text will be here.",
  "model_used": "phi3:latest", // Actual model tag used
  "instance_used": "local", // 'local' or 'remote'
  "error": null // Or an error message if something went wrong
}
```

### Task Queue Quickstart (Celery & Valkey)
Odyssey uses Celery with Valkey (a Redis-compatible broker) for managing background tasks.

**Configuration:**

1.  Ensure your `.env` file has the correct Celery broker and backend URLs. For Docker Compose setups, these are typically overridden in `docker-compose.yml` to point to the `valkey` service name (e.g., `redis://valkey:6379/0`). For local development without Docker, they might point to `redis://localhost:6379/0`.
    ```env
    CELERY_BROKER_URL="redis://localhost:6379/0" # Or redis://valkey:6379/0 in Docker
    CELERY_RESULT_BACKEND_URL="redis://localhost:6379/0" # Or redis://valkey:6379/0 in Docker
    ```

**Running Services:**

1.  **Start Valkey Service:**
    If not already running as part of a broader `docker compose up`, you can start Valkey specifically:
    ```bash
    docker compose up -d valkey
    ```
    *(The `-d` runs it in detached mode.)*

2.  **Start the Celery Worker:**
    The Celery worker processes tasks from the queue.
    *   **Using Docker Compose (Recommended):**
        You can run the worker as a service defined in `docker-compose.yml`. If it's not part of your default `up` command, you can start it specifically:
        ```bash
        docker compose up -d celery_worker # Assumes 'celery_worker' is the service name
        ```
        Or, to run it attached to view logs directly (and it will stop when you Ctrl+C):
        ```bash
        docker compose run --rm --service-ports celery_worker
        ```
        *(The `--service-ports` might be needed if the worker itself exposes any, though usually not.)*

    *   **Manually (for local development outside Docker):**
        Ensure your virtual environment is activated (`source .venv/bin/activate`).
        From the project root (`odyssey/`):
        ```bash
        celery -A odyssey.agent.celery_app worker -l INFO -Q default
        ```
        *(Adjust `-Q default` if you use different queues.)*

**API Usage (Async Tasks):**

1.  **Submit an `add_numbers` task:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tasks/add_numbers" \
    -H "Content-Type: application/json" \
    -d '{"a": 25, "b": 17}'
    ```
    Expected response (task_id will vary):
    ```json
    {
      "task_id": "some-celery-task-id-string",
      "status": "PENDING",
      "message": "Add numbers task submitted successfully."
    }
    ```

2.  **Check the task status:**
    Replace `{task_id}` with the ID received from the previous step.
    ```bash
    curl "http://localhost:8000/api/v1/tasks/status/{task_id}"
    ```
    Example response (after task completion):
    ```json
    {
      "task_id": "some-celery-task-id-string",
      "status": "SUCCESS",
      "result": 42.0,
      "error": null,
      "traceback": null
    }
    ```
    If the task is still pending or running, the `status` will reflect that, and `result` might be `null`. If it failed, `status` would be `FAILURE`, and `error` and `traceback` might be populated.

**Caveats:**
*   Celery tasks are asynchronous. The API response for task submission only confirms receipt; it doesn't wait for completion.
*   You need a running Celery worker to process the tasks.
*   Task results are stored in the Celery backend (Valkey in this case) and are retrieved via the status endpoint.

### Upcoming Expansion Steps
*   Full integration of other services in `docker-compose.yml` (Chroma, Langfuse, Ollama, Frontend).
*   Full implementation of core agent logic (Planner, SelfModifier, ToolManager).
*   Implementation of semantic search and other advanced MemoryManager features.
*   Development of the frontend UI.
*   Detailed API endpoint implementations.
*   Comprehensive test suites.

### 3. Assign Tasks (Future Step)
*(This section will be relevant once the agent logic and UI are more developed.)*
Use the web UI to add coding, debugging, or assistant tasks.
View logs, commit history, memory, and status.
Approve or reject PRs, or let Odyssey auto-merge when tests pass.

### Plugins & Tools
Odyssey features a plugin system that allows for extending its capabilities with custom tools. Tools are Python classes that conform to a specific interface and are auto-discovered by the `ToolManager` at startup.

**How the Plugin System Works:**
1.  Tools are placed as `.py` files within the `odyssey/plugins/` directory.
2.  Each tool file should define one or more classes that inherit from (or conform to) `odyssey.agent.tool_manager.ToolInterface`.
3.  The `ToolInterface` requires each tool to have:
    *   `name: str`: A unique identifier for the tool (e.g., "calculator").
    *   `description: str`: A human-readable description of the tool's purpose.
    *   `execute(self, **kwargs) -> Any`: The method that performs the tool's action.
    *   `get_schema(self) -> Dict[str, Any]`: A method returning a JSON schema defining the tool's `name`, `description`, and expected `parameters` for its `execute` method. This schema is crucial for LLM interaction.
4.  On application startup, the `ToolManager` scans the `odyssey/plugins/` directory, imports valid tool classes, instantiates them, and registers them for use.

**How to Add a New Tool:**
1.  Create a new Python file in the `odyssey/plugins/` directory (e.g., `my_custom_tool.py`).
2.  Define your tool class, ensuring it meets the `ToolInterface` requirements. See `odyssey/plugins/README.md` for a detailed template and `odyssey/plugins/calculator_tool.py` for an example.

**Example: `calculator_tool.py`**
```python
# odyssey/plugins/calculator_tool.py
import logging
from typing import Union, Dict, Any
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.calculator_tool")

class CalculatorTool(ToolInterface):
    name: str = "calculator"
    description: str = "Performs basic arithmetic operations (add, subtract, multiply, divide) on two numbers."

    def execute(self, num1: Union[int, float], num2: Union[int, float], operation: str) -> Union[float, str]:
        logger.info(f"[{self.name}] Executing: {num1} {operation} {num2}")
        # ... (implementation: add, subtract, multiply, divide)
        if operation == "add": return float(num1 + num2)
        # ... (other operations and error handling) ...
        return "Error: Invalid operation"

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "num1": {"type": "number", "description": "First number"},
                    "num2": {"type": "number", "description": "Second number"},
                    "operation": {
                        "type": "string",
                        "description": "Operation to perform",
                        "enum": ["add", "subtract", "multiply", "divide"]
                    }
                },
                "required": ["num1", "num2", "operation"]
            }
        }
```

**API Usage for Tools:**

1.  **List Available Tools:**
    Get a list of all registered tools and their schemas.
    ```bash
    curl "http://localhost:8000/api/v1/tools"
    ```
    Expected partial response:
    ```json
    [
      {
        "name": "calculator",
        "description": "Performs basic arithmetic operations (add, subtract, multiply, divide) on two numbers.",
        "parameters_schema": {
          "type": "object",
          "properties": { /* ... parameters ... */ },
          "required": ["num1", "num2", "operation"]
        }
      }
      // ... other tools ...
    ]
    ```

2.  **Execute a Tool:**
    Send a POST request with the tool name in the path and arguments in the JSON body.
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/calculator" \
    -H "Content-Type: application/json" \
    -d '{
          "parameters": {
            "num1": 10,
            "num2": 5,
            "operation": "add"
          }
        }'
    ```
    Expected response:
    ```json
    {
      "tool_name": "calculator",
      "status": "success",
      "result": 15.0,
      "error_message": null
    }
    ```
    If an error occurs (e.g., invalid operation or tool not found):
    ```json
    {
      "tool_name": "calculator",
      "status": "error",
      "result": null,
      "error_message": "Error: Invalid operation 'foo'. Must be one of 'add', 'subtract', 'multiply', 'divide'."
    }
    ```

3.  **Execute DateTime Tool (Get Current Time):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/datetime_tool" \
    -H "Content-Type: application/json" \
    -d '{"parameters": {}}'
    ```
    Expected response (timestamp will be current UTC time):
    ```json
    {
      "tool_name": "datetime_tool",
      "status": "success",
      "result": "2024-07-15T12:30:45.123456Z",
      "error_message": null
    }
    ```

4.  **Execute DateTime Tool (Get Time in Future):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/datetime_tool" \
    -H "Content-Type: application/json" \
    -d '{"parameters": {"delta_seconds": 900}}'
    ```
    Expected response (timestamp will be 15 minutes from current UTC time):
    ```json
    {
      "tool_name": "datetime_tool",
      "status": "success",
      "result": "2024-07-15T12:45:45.123456Z",
      "error_message": null
    }
    ```

5.  **Execute Random String Tool:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/random_string_tool" \
    -H "Content-Type: application/json" \
    -d '{
          "parameters": {
            "length": 10,
            "charset": "hex"
          }
        }'
    ```
    Expected response (result string will be random):
    ```json
    {
      "tool_name": "random_string_tool",
      "status": "success",
      "result": "a1b2c3d4e5",
      "error_message": null
    }
    ```

**Available Example Tools (Implemented & Stubs):**
*   **`calculator`**: Performs basic arithmetic. (See `plugins/calculator_tool.py`)
*   **`datetime_tool`**: Provides current or calculated UTC date/time. (See `plugins/datetime_tool.py`)
*   **`random_string_tool`**: Generates random strings. (See `plugins/random_string_tool.py`)
*   **`read_file`**: Reads files from the agent's sandboxed directory (`var/agent_files/`). (See `plugins/read_file_tool.py`)
*   **`write_file`**: Writes to files in the sandboxed directory. (See `plugins/write_file_tool.py`)
*   **`list_files`**: Lists files in the sandboxed directory. (See `plugins/list_files_tool.py`)
*   **`fetch_url_tool`**: Fetches content from a URL (Stub, needs `requests` or `httpx`). (See `plugins/fetch_url_tool.py`)
*   **`search_web_tool` (Stub)**: Simulates web search. (See `plugins/search_web_tool.py`)
*   **`save_note_tool` (DI Example)**: Saves a note to memory using injected `MemoryManager`. (See `plugins/save_note_tool.py`)
*   **`get_notes_tool` (DI Example)**: Retrieves notes using injected `MemoryManager`. (See `plugins/get_notes_tool.py`)
*   **`execute_plan_tool` (Stub)**: Intended to execute a sequence of tool calls. (See `plugins/execute_plan_tool.py`)
*   **`schedule_task_tool` (Stub)**: Intended to schedule Celery tasks. (See `plugins/schedule_task_tool.py`)
*   **`calendar_event_tool` (Production Capable - Google Calendar)**: Adds/lists Google Calendar events. Requires setup (see tool file and "Calendar Plugin Setup" below). (See `plugins/calendar_event_tool.py`)
*   **`send_email_tool` (Production Capable - SMTP)**: Sends email via configured SMTP. Requires setup (see "Email Plugin Setup" below). (See `plugins/send_email_tool.py`)
*   **`notify_tool` (Production Capable - Ntfy.sh)**: Sends notifications via Ntfy.sh. Requires setup (see "Notification Plugin Setup" below). (See `plugins/notify_tool.py`)

Refer to `plugins/README.md` and individual tool files in the `odyssey/plugins/` directory for more details on their specific parameters, schemas, and any required setup.

#### Plugin Setup Guides

##### Calendar Plugin Setup (Google Calendar)
The `calendar_event_tool` can interact with Google Calendar. To enable this:
1.  **Google Cloud Project**:
    *   Create a Google Cloud Project (or use an existing one) at [console.cloud.google.com](https://console.cloud.google.com/).
    *   Enable the "Google Calendar API" for your project.
2.  **Service Account**:
    *   Create a Service Account within your GCP project.
    *   Grant this service account appropriate roles. For managing calendar events, "Calendar API Admin" or a custom role with `calendar.events` permissions might be needed.
    *   Download the JSON key file for this service account.
3.  **Share Calendar**:
    *   Go to your Google Calendar settings.
    *   Share the specific calendar you want the agent to access with the service account's email address (e.g., `your-service-account-name@your-project-id.iam.gserviceaccount.com`).
    *   Grant it "Make changes to events" permission (or "See all event details" if only listing is needed by that instance).
4.  **Environment Variables**:
    *   Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable in your `.env` file to the absolute path of the downloaded JSON key file.
        ```env
        GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/gcp-service-account-key.json"
        ```
    *   Optionally, set `DEFAULT_CALENDAR_ID` in your `.env` file if you want to use a calendar other than "primary".
        ```env
        DEFAULT_CALENDAR_ID="your_calendar_id@group.calendar.google.com"
        ```
If these are not configured, or if the Google client libraries are not installed, the `calendar_event_tool` will operate in a "stub mode," logging its actions but not interacting with Google Calendar.

##### Email Plugin Setup (SMTP)
The `send_email_tool` uses SMTP to send emails. Configure the following in your `.env` file:
```env
SMTP_HOST="your.smtp.server.com"
SMTP_PORT="587" # Or 465 for SSL, 25 for unencrypted
SMTP_USER="your_smtp_username_or_email"
SMTP_PASSWORD="your_smtp_password_or_app_password" # KEEP THIS SECRET
SMTP_USE_TLS="true" # true for STARTTLS (port 587), false if using SSL direct (port 465) or no encryption
SMTP_SENDER_EMAIL="your_sender_email@example.com" # 'From' address
```
If essential settings like `SMTP_HOST` or `SMTP_SENDER_EMAIL` are missing, the tool will operate in stub mode (logging email details instead of sending).

##### Notification Plugin Setup (Ntfy.sh)
The `notify_tool` sends messages to an [Ntfy.sh](https://ntfy.sh/) topic.
1.  **Choose a Topic**: Decide on a unique topic name for your notifications (e.g., `odyssey-agent-alerts-yourname`). You can subscribe to this topic using the Ntfy mobile app or web app.
2.  **Environment Variables**: Configure the following in your `.env` file:
    ```env
    NTFY_SERVER_URL="https://ntfy.sh" # Or your self-hosted Ntfy server URL
    NTFY_TOPIC="your-chosen-topic-name"
    ```
    If `NTFY_TOPIC` is not set, the `notify_tool` will operate in stub mode.

**API Usage for `notify_tool`:**
```bash
curl -X POST "http://localhost:8000/api/v1/tools/execute/notify_tool" \
-H "Content-Type: application/json" \
-d '{
      "parameters": {
        "message": "Deployment of v1.2 completed successfully!",
        "title": "Odyssey Deployment Update",
        "priority": 4,
        "tags": ["rocket", "green_circle"]
      }
    }'
```
Expected response (if successful, including stub mode):
```json
{
  "tool_name": "notify_tool",
  "status": "success",
  "result": "Notification sent successfully to Ntfy topic 'your-chosen-topic-name'.",
  "error_message": null
}
```
*(Note: if in stub mode, status will be `success_stub_mode` and result message will indicate logging instead of sending)*


#### Other Implemented Tools (Examples & Stubs)

This section provides `curl` examples for some of the other tools implemented. For full details, refer to the tool's source file in `odyssey/plugins/` or the `GET /api/v1/tools` endpoint for their schemas.

**Fetch URL Tool (`fetch_url_tool`)**
```bash
curl -X POST "http://localhost:8000/api/v1/tools/execute/fetch_url_tool" \
-H "Content-Type: application/json" \
-d '{
      "parameters": {
        "url": "https://jsonplaceholder.typicode.com/todos/1",
        "max_bytes": 200
      }
    }'
```
Expected response (content will be truncated):
```json
{
  "tool_name": "fetch_url_tool",
  "status": "success",
  "result": "{\n  \"userId\": 1,\n  \"id\": 1,\n  \"title\": \"delectus aut autem\",\n  \"completed\": false\n}", // Actual content snippet
  "error_message": null
}
```

**File I/O Tools** (`read_file_tool`, `write_file_tool`, `list_files_tool`)
These tools operate on files within a sandboxed directory on the server (`var/agent_files/`).

*   **Write File (`write_file_tool`):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/write_file_tool" \
    -H "Content-Type: application/json" \
    -d '{
          "parameters": {
            "filename": "my_test_file.txt",
            "content": "Hello from Odyssey File Tool!",
            "mode": "overwrite"
          }
        }'
    ```
    Expected: `{"tool_name": "write_file_tool", "status": "success", "result": "Successfully wrote ... bytes to 'my_test_file.txt' (mode: overwrite).", ...}`

*   **List Files (`list_files_tool`):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/list_files_tool" \
    -H "Content-Type: application/json" \
    -d '{"parameters": {}}'
    ```
    Expected: `{"tool_name": "list_files_tool", "status": "success", "result": ["my_test_file.txt", ...], ...}`

*   **Read File (`read_file_tool`):**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/tools/execute/read_file_tool" \
    -H "Content-Type: application/json" \
    -d '{"parameters": {"filename": "my_test_file.txt"}}'
    ```
    Expected: `{"tool_name": "read_file_tool", "status": "success", "result": "Hello from Odyssey File Tool!", ...}`


**Save Note Tool (`save_note_tool`)** (Uses MemoryManager via DI)
```bash
curl -X POST "http://localhost:8000/api/v1/tools/execute/save_note_tool" \
-H "Content-Type: application/json" \
-d '{
      "parameters": {
        "note": "Remember to test dependency injection thoroughly.",
        "tag": "development"
      }
    }'
```
Expected: `{"tool_name": "save_note_tool", "status": "success", "result": "Note saved successfully with ID X. (Tag: 'development')", "note_id": X, ...}`


**Get Notes Tool (`get_notes_tool`)** (Uses MemoryManager via DI)
```bash
curl -X POST "http://localhost:8000/api/v1/tools/execute/get_notes_tool" \
-H "Content-Type: application/json" \
-d '{
      "parameters": {
        "tag": "development"
      }
    }'
```
Expected: `{"tool_name": "get_notes_tool", "status": "success", "result": [ ... list of notes ... ], ...}`


**Search Web Tool (`search_web_tool`) (Stub)**
```bash
curl -X POST "http://localhost:8000/api/v1/tools/execute/search_web_tool" \
-H "Content-Type: application/json" \
-d '{
      "parameters": {
        "query": "latest advancements in AI agents",
        "num_results": 2
      }
    }'
```
Expected (dummy data):
```json
{
  "tool_name": "search_web_tool",
  "status": "success_stub_mode",
  "result": [
    {
      "title": "Dummy Search Result 1 for 'latest advancements in AI agents'",
      "url": "http://example.com/search?q=latest+advancements+in+AI+agents&result=1",
      "snippet": "This is a dummy snippet..."
    },
    {
      "title": "Dummy Search Result 2 for 'latest advancements in AI agents'",
      "url": "http://example.com/search?q=latest+advancements+in+AI+agents&result=2",
      "snippet": "This is a dummy snippet..."
    }
  ],
  "error_message": null
}
```

*Further setup instructions and API examples for other tools like `execute_plan_tool` and `schedule_task_tool` will be added as their stub implementations are fleshed out.*

### 5. Observability (Future Step)
Langfuse dashboard: `http://localhost:3001` (once Langfuse service is fully integrated in `docker-compose.yml`)
All memory and task events are traced and auditable.

## How Odyssey Modifies Itself
1.  **Propose:** Odyssey analyzes its own repo and writes code changes to a new Git branch.
2.  **Test:** Pulls the branch into a sandboxed environment, runs startup scripts and validation tests.
3.  **Merge:** If tests pass, merges the Pull Request (PR) and hot-reloads relevant modules.
4.  **Rollback:** If validation fails, reverts changes and notifies the user.

## Technology Stack
-   **Backend:** Python 3.10+ (as per Dockerfile), FastAPI, Celery
-   **LLM Interaction:** Ollama
-   **Memory:** SQLite, ChromaDB (or FAISS), JSON backups
-   **Observability:** Langfuse
-   **Frontend:** React (or HTMX/AlpineJS) - *`frontend/` directory implies this*
-   **Plugins:** Python modules (MIT/BSD/Apache-licensed only preferred for community tools)
-   **Infrastructure:** Docker Compose
-   **Message Broker/Task Backend:** Valkey (Redis-compatible)

## Extending Odyssey
-   **Add Plugins:** Create new Python modules in the `plugins/` directory.
-   **Register Tools:** Update `agent/tool_manager.py` or use the web UI (when available) to register new tools.
-   **Memory/Observability:** Implement relevant interfaces in `agent/memory.py` (or dedicated modules) to support new storage or tracing tools.
-   **Self-Modification:** Customize logic in `agent/self_modifier.py`.

## Getting Started (Detailed from initial README)

### Prerequisites

*   Python 3.10+ (aligning with Dockerfile)
*   Git
*   Docker & Docker Compose
*   An Ollama server running with desired models (e.g., `ollama pull llama3`). This can be run locally or as part of the `docker-compose.yml`.

### Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url> # Replace with your actual repo URL
    cd odyssey
    ```

2.  **Run the bootstrap script (if you haven't or for initial setup):**
    This script assists with:
    *   Creating `.env` from `config/secrets.env`. **You'll need to edit `.env` with your actual secrets.**
    *   Setting up a Python virtual environment (e.g., in `.venv/`).
    *   Installing Python dependencies from `requirements.txt`.
    *   Creating necessary directories (e.g., for logs, data based on `config/settings.yaml`).
    ```bash
    chmod +x scripts/bootstrap.sh
    ./scripts/bootstrap.sh
    ```

3.  **Activate the virtual environment (for local development outside Docker):**
    ```bash
    source .venv/bin/activate
    ```

4.  **Configure your environment:**
    *   Edit the `.env` file with your specific API keys, database paths, LLM settings, etc.
    *   Review `config/settings.yaml` for application-level configurations.

### Running the Application (Using Docker Compose - Recommended)

1.  **Ensure Docker Desktop or Docker Engine with Compose plugin is running.**
2.  **Build and start all integrated services (Backend, Frontend, Valkey, Celery Worker):**
    ```bash
    docker compose up --build -d
    ```
    *   Use `docker compose up --build` (without `-d`) to see logs from all services in your terminal.
    *   To start specific services, e.g., just backend and valkey: `docker compose up --build -d backend valkey celery_worker`

3.  **Access Services:**
    *   **Web UI (React):** `http://localhost:5173` (Vite's default dev port)
    *   **Backend API (FastAPI):** `http://localhost:8000` (Swagger UI at `/docs`).
        *   Test basic backend endpoints: `/` and `/health`.
        *   Test memory endpoints: `/api/v1/tasks`, `/api/v1/logs`.
        *   Test LLM endpoint: `/api/v1/llm/ask`.
        *   Test Celery task submission/status: `/api/v1/tasks/add_numbers`, `/api/v1/tasks/status/{task_id}`.
    *   **Valkey (Broker):** Port `6379` is exposed to the host (e.g., for debugging with `redis-cli`).
    *   **(Future) Langfuse:** `http://localhost:3001`
    *   **(Future) ChromaDB:** `http://localhost:8001`
    *   **(Future) Ollama (if run via Compose):** `http://localhost:11434`

### Running Tests

Ensure development dependencies are installed (e.g., via `scripts/bootstrap.sh` and activating `.venv`).
```bash
# Activate venv if not in Docker: source .venv/bin/activate
# Using the provided test_runner.py script:
python scripts/test_runner.py

# Or directly with pytest:
pytest tests/
```

## License

This project is licensed under the [MIT License](LICENSE).
```
