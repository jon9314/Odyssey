"""
Main entrypoint for the Odyssey Agent backend.
This script initializes and starts the FastAPI application, including setting up
necessary resources like the MemoryManager during the application's lifespan.
"""
import logging
import uvicorn
import time # For request timing
from fastapi import FastAPI, APIRouter, HTTPException, Request
from contextlib import asynccontextmanager
from typing import Callable # For middleware type hint

import os # For loading environment variables
from pydantic_settings import BaseSettings # For loading .env and typed settings
from typing import Optional # For AppState type hints

# Import core components
from odyssey.agent.memory import MemoryManager
from odyssey.agent.ollama_client import OllamaClient
from odyssey.agent.tool_manager import ToolManager
from odyssey.agent.self_modifier import SelfModifier # Import SelfModifier
from odyssey.agent.celery_app import celery_app # Import celery_app for DI

# Import API routers
from odyssey.api.routes import (
    router as api_main_router,
    get_memory_manager as get_memory_manager_dependency,
    get_ollama_client as get_ollama_client_dependency,
    get_tool_manager as get_tool_manager_dependency,
    get_self_modifier as get_self_modifier_dependency, # Import SelfModifier dependency
    memory_router # Import the new memory_router
)
# Configure basic logging
# This will be the root logger configuration. Specific module loggers can be retrieved via `logging.getLogger(__name__)`.
# The format now includes the module name for better source identification.
LOG_FORMAT = '%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("odyssey.agent.main") # More specific logger name


# --- Settings Model using Pydantic-Settings ---
class AppSettings(BaseSettings):
    # .env variables will automatically be loaded if python-dotenv is installed
    # and pydantic-settings will read them.
    # These correspond to entries in config/settings.yaml which can also reference these env vars.
    ollama_local_url: str = "http://localhost:11434"
    ollama_remote_url: Optional[str] = None
    ollama_default_model: str = "phi3"
    ollama_request_timeout: int = 120

    # Memory settings (example, could be expanded)
    memory_db_path: str = "var/memory/main_agent_memory.db"

    # Celery settings (already in secrets.env, but good to have typed versions)
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend_url: str = "redis://localhost:6379/0"

    # Plugin specific settings - Calendar Tool Example
    google_application_credentials: Optional[str] = None # Path to service account JSON
    default_calendar_id: str = "primary"

    # Plugin specific settings - Email Tool
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_sender_email: Optional[str] = None

    # Plugin specific settings - Notification Tool (Ntfy example)
    ntfy_server_url: str = "https://ntfy.sh"
    ntfy_topic: Optional[str] = None

    # SelfModifier settings
    repo_path: str = "." # Default to current directory, can be overridden by env
    SELF_MOD_APPROVAL_MODE: str = "manual" # Options: 'manual' (default), 'auto'

    # Sandbox settings
    SANDBOX_HEALTH_CHECK_ENDPOINT: str = "/health"
    SANDBOX_APP_PORT_IN_CONTAINER: int = 8000
    SANDBOX_HOST_PORT_FOR_HEALTH_CHECK: int = 18765 # Should be unique if multiple tests run in parallel
    SANDBOX_DEFAULT_TEST_COMMAND: str = "python -m unittest discover -s ./tests" # Store as string, parse in task
    SANDBOX_DOCKER_MEMORY_LIMIT: str = "1g" # e.g., "512m", "1g"
    SANDBOX_DOCKER_CPU_LIMIT: Optional[str] = None # e.g., "0.5", "1" (number of CPUs)
    SANDBOX_DOCKER_NETWORK: str = "bridge" # Default Docker network. Use "none" for no network.
    SANDBOX_DOCKER_NO_NEW_PRIVILEGES: bool = True

    # For .env file loading by Pydantic-Settings
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore" # Allow other env variables not defined in settings


# Application state to hold initialized components
# Define Any for celery_app_instance if Celery app type is complex or not easily imported here
from typing import Any
class AppState:
    settings: AppSettings
    memory_manager: MemoryManager
    ollama_client: OllamaClient
    tool_manager: ToolManager
    self_modifier: SelfModifier # Add SelfModifier to AppState
    celery_app_instance: Optional[Any] = None # To hold the celery app for DI
    # ... other components

app_state = AppState() # Global app_state instance


@asynccontextmanager
async def lifespan(app_instance: FastAPI): # Renamed app to app_instance to avoid conflict with global 'app'
    # Code to run on startup
    logger.info("Odyssey Agent Backend starting up...")

    # --- Load Configuration ---
    app_state.settings = AppSettings()
    logger.info("Application settings loaded.")
    logger.debug(f"Loaded settings: {app_state.settings.model_dump_json(indent=2)}")


    # --- Initialize Core Components ---
    # MemoryManager
    app_state.memory_manager = MemoryManager(db_path=app_state.settings.memory_db_path)
    logger.info(f"MemoryManager initialized with DB: {app_state.memory_manager.db_path}")
    get_memory_manager_dependency.instance = app_state.memory_manager

    # OllamaClient
    app_state.ollama_client = OllamaClient(
        local_url=app_state.settings.ollama_local_url,
        remote_url=app_state.settings.ollama_remote_url,
        default_model=app_state.settings.ollama_default_model,
        request_timeout=app_state.settings.ollama_request_timeout
    )
    logger.info("OllamaClient initialized.")
    get_ollama_client_dependency.instance = app_state.ollama_client # Make available for API routes

    # ToolManager and Plugin Auto-Discovery
    # Pass available core services to ToolManager for potential injection into plugins
    app_state.celery_app_instance = celery_app # Store celery_app in app_state

    # ToolManager and Plugin Auto-Discovery
    # Pass available core services to ToolManager for potential injection into plugins
    app_state.celery_app_instance = celery_app # Store celery_app in app_state

    # Instantiate ToolManager with all injectable dependencies
    app_state.tool_manager = ToolManager(
        memory_manager=app_state.memory_manager,
        ollama_client=app_state.ollama_client,
        celery_app_instance=app_state.celery_app_instance,
        app_settings=app_state.settings # Pass the AppSettings object
        # The ToolManager's __init__ makes itself available under 'tool_manager' key
    )
    logger.info("ToolManager initialized with core service references (including AppSettings) for DI.")

    # Discover and register plugins. The ToolManager will use its internal dependencies for injection.
    # The plugin_dir_name="plugins" will be resolved by ToolManager relative to odyssey package root.
    app_state.tool_manager.discover_and_register_plugins(plugin_dir_name="plugins")
    get_tool_manager_dependency.instance = app_state.tool_manager

    # logger.info("Placeholder: Initialize SelfModifier")
    # app_state.self_modifier = SelfModifier()
    get_tool_manager_dependency.instance = app_state.tool_manager

    # SelfModifier
    app_state.self_modifier = SelfModifier(repo_path=app_state.settings.repo_path)
    logger.info(f"SelfModifier initialized for repo path: {app_state.settings.repo_path}")
    get_self_modifier_dependency.instance = app_state.self_modifier

    # logger.info("Placeholder: Initialize Planner")
    # app_state.planner = Planner(llm_client=app_state.ollama_client, ...)

    logger.info("Core components initialized (MemoryManager, OllamaClient, ToolManager, SelfModifier, CeleryApp ref active; Planner placeholder).")

    yield # Application runs after this point

    # Code to run on shutdown
    logger.info("Odyssey Agent Backend shutting down...")
    if hasattr(app_state, 'memory_manager') and app_state.memory_manager:
        app_state.memory_manager.close()
        logger.info("MemoryManager connection closed.")
    # No specific close/cleanup needed for OllamaClient or ToolManager as implemented
    logger.info("Shutdown complete.")


# Initialize FastAPI app with the lifespan context manager
app = FastAPI(
    title="Odyssey Agent API",
    description="API for interacting with the Odyssey Self-Rewriting AI Agent.",
    version="0.1.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
# This must be added before any routes are defined if it's to apply globally.
from fastapi.middleware.cors import CORSMiddleware

# Define allowed origins. For development, this often includes localhost ports
# for the frontend dev server. In production, restrict this to your actual frontend domain.
# The VITE_FRONTEND_URL env var can be used by Vite dev server, usually http://localhost:5173
# For React CRA, it's often http://localhost:3000
# We'll allow both for flexibility during development.
origins = [
    "http://localhost:3000",  # Common React CRA dev port
    "http://localhost:5173",  # Common Vite dev port
    # Add your production frontend URL here when deployed
    # "https://your-odyssey-frontend.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # List of origins that are allowed to make requests
    allow_credentials=True, # Allow cookies to be included in requests
    allow_methods=["*"],    # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allow all headers
)
logger.info(f"CORS middleware configured for origins: {origins}")


# --- Middleware for logging requests ---
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next: Callable):
    """
    Middleware to log incoming requests and their processing time.
    """
    # Using a more specific logger name for API request logs
    api_logger = logging.getLogger("odyssey.api.access")

    # Construct a unique request ID if not present (useful for tracing)
    request_id = request.headers.get("X-Request-ID", os.urandom(8).hex())

    api_logger.info(f"[Request:{request_id}] Started: {request.method} {request.url.path} from {request.client.host}")
    start_time = time.time()

    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000  # milliseconds
        api_logger.info(
            f"[Request:{request_id}] Completed: {request.method} {request.url.path} "
            f"Status: {response.status_code} Duration: {process_time:.2f}ms"
        )
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"[Request:{request_id}] Failed: {request.method} {request.url.path} "
            f"Duration: {process_time:.2f}ms Error: {e}",
            exc_info=True # Include traceback for unhandled exceptions at middleware level
        )
        # Re-raise the exception to let FastAPI handle it and return appropriate HTTP error
        raise
    return response

# --- Root endpoint (/) ---
@app.get("/", tags=["Root"])
async def read_root_endpoint(request: Request): # Added Request for logging client
    """Returns a welcome message indicating the backend is running."""
    # logger.debug("Root endpoint / was hit.") # Covered by middleware now
    return {
        "message": "Odyssey backend is running", # Updated message as per new goal
        "status": "ok",
        "version": app.version
    }

# --- Health Check Endpoint (/health) ---
@app.get("/health", tags=["Health Check"])
async def health_check_endpoint(request: Request): # Added Request for logging client
    """Returns a simple health status, indicating the service is operational."""
    # logger.debug("Health check endpoint /health was hit.") # Covered by middleware now
    return {"status": "ok"}


# --- Mount API Routers (for more complex APIs) ---
# This should come after root and health typically, or ensure paths don't clash.
# Main application/utility API router (from existing structure)
app.include_router(api_main_router, prefix="/api/v1", tags=["Core Agent & Task Endpoints"]) # Renamed tag for clarity
app.include_router(memory_router, prefix="/api/v1", tags=["Memory Management"]) # Added memory_router

# Agent-specific API router (if you create one, e.g., for tasks, agent control)
# app.include_router(agent_api_router, prefix="/api/v1/agent", tags=["Agent Management"])


# This `main_cli` function is for direct execution (e.g., `python odyssey/agent/main.py`)
# The `docker-compose.yml` or `uvicorn` command will typically target `odyssey.agent.main:app`.
def main_cli(): # Renamed to avoid conflict with module name if imported elsewhere
    logger.info("Starting Uvicorn server for Odyssey Agent Backend...")

    # Configuration for Uvicorn can be loaded from settings or passed here
    # Example: host=global_settings.api.host, port=global_settings.api.port
    uvicorn.run(
        "odyssey.agent.main:app", # Path to the FastAPI app instance
        host="0.0.0.0",           # Listen on all available IPs
        port=8000,                # Standard port for the API
        reload=True,              # Enable auto-reload for development (disable in production)
        log_level="info"          # Uvicorn's own log level
    )

if __name__ == "__main__":
    main_cli()

# Note on Web Interface:
# This `main.py` primarily starts the backend (FastAPI).
# The web interface (React/HTMX) is a separate frontend application.
# - If it's a React app, it's typically served by its own Node.js server (e.g., `npm start` or `serve -s build`).
# - If it's HTMX served directly by FastAPI, then FastAPI would also serve HTML templates and static files.
# The `docker-compose.yml` handles running both backend and frontend as separate services.
# This `main.py` doesn't directly "start" the web interface in the sense of serving its files,
# unless FastAPI is configured to do so (which is not the default setup implied by the separate frontend service).
# The comment "Starts the Odyssey backend and web interface" in the original description might mean
# it's the entry point for the *project's backend services*, which the web interface then consumes.
```
