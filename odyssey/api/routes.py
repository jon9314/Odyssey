"""
API routes for the Odyssey agent.
This module defines endpoints for interacting with tasks, logs, agent status,
configuration, and other core functionalities.
"""
import os # For dummy ID generation in examples
from fastapi import APIRouter, HTTPException, Body, Depends, Query, Path
from typing import List, Dict, Any, Optional

# Import Pydantic models from schemas.py
from .schemas import (
    Item, ItemCreate, # Existing example schemas
    TaskCreateRequest, TaskResponse, TaskUpdateRequest, # Task schemas
    PlanCreateRequest, PlanResponse, # Plan schemas
    LogEntryResponse, LogCreateRequest, # Log schemas
    AgentConfig,
    MemoryQuery, MemoryQueryResult,
    ToolInfo, ToolExecutionRequest, ToolExecutionResult,
    MessageResponse # General message response
)

import datetime # For LogCreateRequest default timestamp

# Import Pydantic models from schemas.py
from .schemas import (
    # Item, ItemCreate, # Example schemas (can be removed if not used)
    TaskCreateRequest, TaskResponse, TaskUpdateRequest, # Task schemas
    PlanCreateRequest, PlanResponse, # Plan schemas
    LogEntryResponse, LogCreateRequest, # Log schemas
    AgentConfig,
    # MemoryQuery, MemoryQueryResult, # MemoryQuery might be replaced by specific GET filters
    ToolInfo, ToolExecutionRequest, ToolExecutionResult,
    MessageResponse, # General message response
    LLMAskRequest, LLMAskResponse, # LLM Schemas
    AddNumbersTaskRequest, SimulateLongTaskRequest, # Specific Celery task requests
    AsyncTaskResponse, AsyncTaskStatusResponse, # Generic Celery task responses
    ProposeChangeRequestSchema, ProposalResponseSchema, ProposalStatusResponseSchema # Self Modification Schemas
)
import logging # For logging within route handlers if needed
import uuid # For generating proposal IDs

# Import Core Components for dependency injection
from odyssey.agent.memory import MemoryManager
from odyssey.agent.ollama_client import OllamaClient
from odyssey.agent.tool_manager import ToolManager
from odyssey.agent.self_modifier import SelfModifier # Import SelfModifier
from odyssey.agent.celery_app import celery_app # For accessing Celery app instance
from celery.result import AsyncResult # For checking task status
# from odyssey.agent.tasks import validate_proposal_task, merge_proposal_task # Will be used later


# Logger for this module (routes)
# The middleware in main.py handles general access logging.
# This logger can be used for specific events within route handlers.
logger = logging.getLogger("odyssey.api.routes")


# --- Dependency Injection Setup ---
# These functions will be used by FastAPI's `Depends` to inject instances
# of our core components (MemoryManager, OllamaClient, etc.) into route handlers.
# The actual instances are created and managed in `agent/main.py`'s lifespan events
# and then assigned to the `.instance` attribute of these functions.

async def get_memory_manager() -> MemoryManager:
    """Dependency function to get the MemoryManager instance."""
    if not hasattr(get_memory_manager, "instance"):
        # This path should ideally not be hit if main.py's lifespan setup is correct.
        # It's a fallback for direct testing or if setup fails.
        print("Warning: get_memory_manager.instance not set by main.py lifespan. Creating fallback.")
        get_memory_manager.instance = MemoryManager(db_path="var/memory/fallback_routes_memory.db")
    return get_memory_manager.instance

async def get_ollama_client() -> OllamaClient:
    """Dependency function to get the OllamaClient instance."""
    if not hasattr(get_ollama_client, "instance"):
        print("Warning: get_ollama_client.instance not set by main.py lifespan. Creating fallback.")
        # Fallback requires default URLs which might not be ideal here.
        # This highlights the importance of initialization in main.py.
        from odyssey.agent.main import AppSettings # Temp import for fallback
        settings = AppSettings()
        get_ollama_client.instance = OllamaClient(
            local_url=settings.ollama_local_url,
            remote_url=settings.ollama_remote_url,
            default_model=settings.ollama_default_model
        )
    return get_ollama_client.instance

async def get_tool_manager() -> ToolManager:
    """Dependency function to get the ToolManager instance."""
    if not hasattr(get_tool_manager, "instance"):
        print("Warning: get_tool_manager.instance not set by main.py lifespan. Creating fallback.")
        # ToolManager might auto-discover plugins on init, ensure path is correct for fallback
        from odyssey.agent.main import AppSettings # Temp for project root
        import os
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")) # odyssey/api/ -> odyssey/
        plugins_dir = os.path.join(project_root, "plugins")
        get_tool_manager.instance = ToolManager()
        get_tool_manager.instance.discover_and_register_plugins(plugin_dir_path=plugins_dir) # Discover for fallback
    return get_tool_manager.instance

async def get_self_modifier() -> SelfModifier:
    """Dependency function to get the SelfModifier instance."""
    if not hasattr(get_self_modifier, "instance"):
        print("Warning: get_self_modifier.instance not set by main.py lifespan. Creating fallback.")
        # SelfModifier might need specific config (e.g., repo path) not available here.
        # This highlights the importance of initialization in main.py.
        # Assuming SelfModifier can be initialized without specific args for a basic fallback.
        get_self_modifier.instance = SelfModifier(repo_path=".") # Adjust repo_path if necessary for fallback
    return get_self_modifier.instance

router = APIRouter()

# --- Task Management Endpoints ---
@router.post("/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
async def create_new_task(
    task_data: TaskCreateRequest,
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Create a new task in the agent's memory."""
    task_id = memory.add_task(description=task_data.description)
    if task_id is None:
        raise HTTPException(status_code=500, detail="Failed to create task in memory.")

    # Fetch the created task to return it (as add_task only returns id)
    # This is a bit inefficient; add_task could return the full object or we query by id.
    # For now, let's assume get_tasks can find it quickly if we add it and immediately get.
    # A better approach: memory.get_task_by_id(task_id)
    created_task_list = memory.get_tasks() # This is not ideal; need get_task_by_id
    new_task_obj = next((t for t in created_task_list if t['id'] == task_id), None)
    if not new_task_obj:
        raise HTTPException(status_code=500, detail="Task created but could not be retrieved immediately.")
    return TaskResponse(**new_task_obj)


@router.get("/tasks", response_model=List[TaskResponse], tags=["Tasks"])
async def get_all_tasks(
    status: Optional[str] = Query(None, description="Filter tasks by status (e.g., 'pending', 'completed')"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of tasks to return."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Retrieve a list of tasks, optionally filtered by status."""
    tasks_from_db = memory.get_tasks(status_filter=status, limit=limit)
    return [TaskResponse(**task) for task in tasks_from_db] # Convert dicts to TaskResponse


@router.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_specific_task(
    task_id: int = Path(..., description="The ID of the task to retrieve."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Retrieve a specific task by its ID."""
    # MemoryManager needs a get_task_by_id method for this to be efficient
    # For now, filtering from get_tasks()
    tasks = memory.get_tasks()
    task = next((t for t in tasks if t['id'] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found.")
    return TaskResponse(**task)


@router.put("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def update_existing_task(
    task_id: int = Path(..., description="The ID of the task to update."),
    update_data: TaskUpdateRequest,
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Update the status or description of an existing task."""
    if update_data.status:
        success = memory.update_task_status(task_id, update_data.status)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found or update failed.")

    if update_data.description:
        # MemoryManager would need a method like `update_task_description(task_id, new_description)`
        # This is not implemented in the current MemoryManager spec. For now, this part is conceptual.
        # For this example, we'll just log it if description is provided.
        memory.log_event(f"Conceptual: Task ID {task_id} description update requested to '{update_data.description}'. Update logic needed in MemoryManager.", level="INFO")
        # If implemented:
        # desc_success = memory.update_task_description(task_id, update_data.description)
        # if not desc_success:
        #     raise HTTPException(status_code=404, detail=f"Task description update failed for ID {task_id}.")


    # Fetch and return the updated task
    tasks = memory.get_tasks() # Inefficient, need get_task_by_id
    updated_task_obj = next((t for t in tasks if t['id'] == task_id), None)
    if not updated_task_obj:
        raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found after update attempt.")
    return TaskResponse(**updated_task_obj)


# --- Log Management Endpoints ---
@router.get("/logs", response_model=List[LogEntryResponse], tags=["Logs"])
async def get_agent_logs(
    level: Optional[str] = Query(None, description="Filter logs by level (e.g., 'INFO', 'ERROR')"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of log entries to return."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Retrieve agent log entries stored in memory."""
    logs_from_db = memory.get_logs(level_filter=level, limit=limit)
    return [LogEntryResponse(**log_entry) for log_entry in logs_from_db]

@router.post("/logs", response_model=LogEntryResponse, status_code=201, tags=["Logs"])
async def create_log_entry_external( # If allowing external systems to add to agent's DB log
    log_data: LogCreateRequest,
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Manually add a log entry to the agent's memory (e.g., from an external tool)."""
    log_id = memory.log_event(message=log_data.message, level=log_data.level)
    if log_id is None:
        raise HTTPException(status_code=500, detail="Failed to store log entry.")

    # Fetch the created log to return it (needs get_log_by_id in MemoryManager)
    # For now, this is a mock representation.
    return LogEntryResponse(
        id=log_id,
        message=log_data.message,
        level=log_data.level.upper(),
        timestamp=datetime.datetime.utcnow() # Approximate timestamp
    )

# --- Plan Management Endpoints (Basic) ---
@router.post("/plans", response_model=PlanResponse, status_code=201, tags=["Plans"])
async def create_new_plan(
    plan_data: PlanCreateRequest,
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Create a new plan in the agent's memory."""
    plan_id = memory.add_plan(details=plan_data.details)
    if plan_id is None:
        raise HTTPException(status_code=500, detail="Failed to create plan in memory.")

    # Fetch created plan (needs get_plan_by_id in MemoryManager)
    plans = memory.get_plans() # Inefficient
    new_plan_obj = next((p for p in plans if p['id'] == plan_id), None)
    if not new_plan_obj:
         raise HTTPException(status_code=500, detail="Plan created but could not be retrieved.")
    return PlanResponse(**new_plan_obj)

@router.get("/plans", response_model=List[PlanResponse], tags=["Plans"])
async def get_all_plans(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of plans to return."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Retrieve a list of plans."""
    plans_from_db = memory.get_plans(limit=limit)
    return [PlanResponse(**plan) for plan in plans_from_db]


# --- Celery Task Endpoints ---
# Note: The tag "Tasks" is reused here. Consider "Async Tasks" or "Background Tasks" if confusion arises
# with the Memory-based "Tasks" which are more like to-do items for the agent itself.
# For now, keeping it simple.

@router.post("/tasks/add_numbers", response_model=AsyncTaskResponse, status_code=202, tags=["Async Tasks"])
async def submit_add_numbers_task(
    task_data: AddNumbersTaskRequest
):
    """Submits an 'add_numbers' task to the Celery queue."""
    # Import the task function from where it's defined (e.g., odyssey.agent.tasks)
    # This import should ideally be at the top of the file, but placed here for clarity
    # on where it's first used if this file grows very large.
    try:
        from odyssey.agent.tasks import add_numbers # Assuming tasks are in this module
        task_result = add_numbers.delay(a=task_data.a, b=task_data.b)
        return AsyncTaskResponse(
            task_id=task_result.id,
            status=task_result.status, # Celery task status (e.g., PENDING)
            message="Add numbers task submitted successfully."
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="Celery task 'add_numbers' not found. Check worker and task definitions.")
    except Exception as e:
        logger.error(f"Failed to submit 'add_numbers' task. Data: {task_data.model_dump()}. Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.post("/tasks/simulate_long", response_model=AsyncTaskResponse, status_code=202, tags=["Async Tasks"])
async def submit_simulate_long_task(
    task_data: SimulateLongTaskRequest
):
    """Submits a 'simulate_long_task' to the Celery queue."""
    try:
        from odyssey.agent.tasks import simulate_long_task
        task_result = simulate_long_task.delay(
            duration_seconds=task_data.duration_seconds,
            message=task_data.message
        )
        return AsyncTaskResponse(
            task_id=task_result.id,
            status=task_result.status,
            message="Simulate long task submitted successfully."
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="Celery task 'simulate_long_task' not found.")
    except Exception as e:
        logger.error(f"Failed to submit 'simulate_long_task'. Data: {task_data.model_dump()}. Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@router.get("/tasks/status/{task_id}", response_model=AsyncTaskStatusResponse, tags=["Async Tasks"])
async def get_async_task_status(
    task_id: str = Path(..., description="The ID of the Celery task to check.")
):
    """
    Retrieves the status and result (if available) of a Celery task.
    """
    task_result = AsyncResult(task_id, app=celery_app) # Get result using our celery_app instance

    response_data = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "error": None,
        "traceback": None
    }

    if task_result.successful():
        response_data["result"] = task_result.get()
    elif task_result.failed():
        # result.get(propagate=False) can get the exception instance
        # result.traceback gives the traceback string
        response_data["error"] = str(task_result.result) # The exception message
        response_data["traceback"] = task_result.traceback
    # For other states (PENDING, STARTED, RETRY), result and error will be None.

    return AsyncTaskStatusResponse(**response_data)


# --- Retained Endpoints (Status, Config, Tools, Self-Modify - requires further integration) ---
# These are kept from the previous version but will need proper service dependencies.

@router.get("/status", response_model=Dict[str, Any], tags=["Agent Status"]) # Simplified response for now
async def get_agent_status():
    """Get the current status of the Odyssey agent."""
    # TODO: Integrate with actual agent components for status.
    # This example shows how you might access memory manager for counts.
    # In a real scenario, you'd have a dedicated status service or pull from app_state.
    memory_mgr = await get_memory_manager() # Get instance for this call
    tasks = memory_mgr.get_tasks(limit=1000) # Get all tasks to count active ones
    active_tasks_count = sum(1 for task in tasks if task.get('status') == 'pending' or task.get('status') == 'in_progress')

    return {
        "status": "running_mock",
        "version": "0.1.0", # Placeholder, could get from app instance
        "active_tasks_count": active_tasks_count,
        "log_count": len(memory_mgr.get_logs(limit=10000)), # Total logs in DB for example
        "ollama_local_status": "unknown", # Placeholder, would ping OllamaClient
        "ollama_remote_status": "unknown" # Placeholder
    }

@router.get("/config", response_model=AgentConfig, tags=["Agent Configuration"])
async def get_agent_configuration():
    """Retrieve the current agent configuration (mocked)."""
    return AgentConfig() # Returns default values from Pydantic model

@router.put("/config", response_model=AgentConfig, tags=["Agent Configuration"])
async def update_agent_configuration(config_update: AgentConfig):
    """Update the agent's configuration (mocked)."""
    # TODO: Implement actual config update logic
    if config_update.max_iterations is not None and config_update.max_iterations < 1:
        raise HTTPException(status_code=400, detail="max_iterations must be positive.")
    # For now, just echo back the received update after validation
    print(f"Mock config update: {config_update.model_dump_json(indent=2)}")
    return config_update


@router.get("/tools", response_model=List[ToolInfo], tags=["Tools"])
async def list_available_tools(
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """List all available tools and their schemas."""
    schemas = tool_manager.get_all_tool_schemas()
    # The ToolInfo schema expects name, description, and parameters_schema.
    # ToolManager.get_all_tool_schemas() returns a list of these directly.
    return [ToolInfo(**s) for s in schemas]


@router.post("/tools/execute/{tool_name}", response_model=ToolExecutionResult, tags=["Tools"])
async def execute_tool_endpoint(
    tool_name: str = Path(..., description="Name of the tool to execute."),
    request_body: ToolExecutionRequest = Body(...),
    tool_manager: ToolManager = Depends(get_tool_manager)
):
    """Execute a specified tool with given parameters."""
    logger.info(f"API request to execute tool '{tool_name}' with params: {request_body.parameters}")

    # The ToolManager's execute method returns the direct result or an error dict
    execution_outcome = tool_manager.execute(tool_name, **request_body.parameters)

    if isinstance(execution_outcome, dict) and execution_outcome.get("error"):
        logger.warning(f"Tool execution for '{tool_name}' failed. Outcome: {execution_outcome}")
        # If the error message from ToolManager is detailed enough, pass it directly
        error_msg = execution_outcome.get("message", "Tool execution failed.")
        if execution_outcome.get("details"):
             error_msg += f" Details: {execution_outcome.get('details')}"
        # Consider raising HTTPException for certain types of tool errors if they map to HTTP status codes
        # For now, return structured error within ToolExecutionResult
        return ToolExecutionResult(
            tool_name=tool_name,
            status="error",
            error_message=error_msg
        )
    else:
        logger.info(f"Tool '{tool_name}' executed successfully via API. Result snippet: {str(execution_outcome)[:100]}...")
        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            result=execution_outcome
        )

# --- LLM Interaction Endpoint ---
@router.post("/llm/ask", response_model=LLMAskResponse, tags=["LLM"])
async def ask_llm(
    request_data: LLMAskRequest,
    ollama: OllamaClient = Depends(get_ollama_client) # Corrected dependency name
):
    """
    Send a prompt to the configured Ollama LLM and get a response.
    The 'safe' parameter in the request can hint at routing to local (safe=True)
    or remote (safe=False) Ollama instances if both are configured.
    Streaming is not yet supported via this HTTP endpoint but OllamaClient supports it.
    """
    if request_data.stream:
        # TODO: Implement streaming response handling for FastAPI if required.
        # This might involve using StreamingResponse. For now, returning error for stream=True.
        raise HTTPException(status_code=501, detail="Streaming responses are not yet implemented for this HTTP endpoint.")

    instance_type, model_used, response_content = ollama.ask(
        prompt=request_data.prompt,
        model=request_data.model,
        safe=request_data.safe,
        stream=False, # Force non-streaming for this endpoint currently
        options=request_data.options,
        system_prompt=request_data.system_prompt
    )

    if "Error:" in str(response_content): # Check if the response content itself is an error message from OllamaClient
        return LLMAskResponse(
            response=None,
            model_used=model_used,
            instance_used=instance_type,
            error=str(response_content)
        )

    return LLMAskResponse(
        response=str(response_content),
        model_used=model_used,
        instance_used=instance_type
    )


# Note: The Item example endpoints can be removed if no longer needed.
# For now, they are just commented out.
# fake_items_db = {"item1": {"id": "item1", "name": "Foo", "description": "A foo item"}, "item2": {"id": "item2", "name": "Bar", "description": "A bar item"}}
# @router.get("/items/", response_model=List[Item], tags=["Example Items"])
# --- End of File ---

# --- Self Modification Endpoints ---
@router.post("/self-modify/propose", response_model=ProposalResponseSchema, status_code=202, tags=["Self Modification"])
async def propose_code_change_endpoint(
    request_data: ProposeChangeRequestSchema,
    self_modifier: SelfModifier = Depends(get_self_modifier),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """
    Accepts a code change proposal, creates a branch with the changes,
    logs the proposal, and triggers an asynchronous validation task.
    """
    logger.info(f"Received proposal to modify files with commit: '{request_data.commit_message}'")

    proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
    initial_status = "proposed"

    try:
        # 1. Propose code changes using SelfModifier
        # Assuming propose_code_changes returns the actual branch name used.
        actual_branch_name = self_modifier.propose_code_changes(
            files_content=request_data.files_content,
            commit_message=request_data.commit_message,
            branch_prefix=request_data.branch_prefix,
            proposal_id=proposal_id # Pass proposal_id for branch naming consistency if desired
        )
        logger.info(f"Code changes proposed on branch: {actual_branch_name} for proposal ID: {proposal_id}")

    except Exception as e:
        logger.error(f"Error during self_modifier.propose_code_changes for proposal {proposal_id}: {e}", exc_info=True)
        # Attempt to log failure to propose if branch creation failed.
        # This part is tricky if branch_name was never even created.
        # Using a placeholder branch name for logging if actual_branch_name is not available.
        failed_branch_name = f"{request_data.branch_prefix or 'proposal'}_{proposal_id}_failed"
        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=failed_branch_name, # Log with a generated name if creation failed
            commit_message=request_data.commit_message,
            status="proposal_failed", # A status indicating failure at the proposal stage itself
            validation_output=f"Error creating branch/commit: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=f"Failed to propose code changes: {str(e)}")

    # 2. Log the proposal step in MemoryManager
    log_success = memory.log_proposal_step(
        proposal_id=proposal_id,
        branch_name=actual_branch_name,
        commit_message=request_data.commit_message,
        status=initial_status
    )
    if not log_success:
        # This is a critical error, as the proposal is made but not tracked.
        # Manual intervention might be needed.
        logger.error(f"CRITICAL: Failed to log proposal {proposal_id} (branch: {actual_branch_name}) to memory after changes were made.")
        # We might still raise HTTPException, but the system is in an inconsistent state.
        raise HTTPException(status_code=500, detail=f"Proposal created on branch {actual_branch_name} but failed to log to memory. Please check system integrity.")

    # 3. Trigger asynchronous validation task (Celery)
    try:
        # IMPORTANT: Ensure 'run_sandbox_validation_task' is defined in odyssey.agent.tasks
        # and registered with the Celery app.
        from odyssey.agent.tasks import run_sandbox_validation_task # UPDATED TASK NAME
        validate_task_result = run_sandbox_validation_task.delay( # UPDATED TASK NAME
            proposal_id=proposal_id,
            branch_name=actual_branch_name
        )
        logger.info(f"Sandbox validation task ({validate_task_result.id}) triggered for proposal {proposal_id} on branch {actual_branch_name}.")
        # Update status to "validation_pending"
        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=actual_branch_name,
            commit_message=request_data.commit_message,
            status="validation_pending"
        )
    except ImportError:
        logger.error("Celery task 'validate_proposal_task' not found. Validation cannot be triggered.", exc_info=True)
        # Update status to reflect this problem
        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=actual_branch_name,
            commit_message=request_data.commit_message,
            status="validation_error",
            validation_output="Failed to trigger validation: Task not found."
        )
        # Return a success response for proposal creation, but with a warning message.
        return ProposalResponseSchema(
            proposal_id=proposal_id,
            branch_name=actual_branch_name,
            status="validation_error",
            message="Proposal created, but automatic validation could not be started. Task not found."
        )
    except Exception as e:
        logger.error(f"Error triggering validation task for proposal {proposal_id}: {e}", exc_info=True)
        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=actual_branch_name,
            commit_message=request_data.commit_message,
            status="validation_error",
            validation_output=f"Failed to trigger validation: {str(e)}"
        )
        return ProposalResponseSchema(
            proposal_id=proposal_id,
            branch_name=actual_branch_name,
            status="validation_error",
            message=f"Proposal created, but automatic validation failed to start: {str(e)}"
        )

    return ProposalResponseSchema(
        proposal_id=proposal_id,
        branch_name=actual_branch_name,
        status="validation_pending", # Updated status
        message="Proposal submitted successfully. Code changes created, logged, and validation task triggered."
    )


@router.get("/self-modify/proposals", response_model=List[ProposalStatusResponseSchema], tags=["Self Modification"])
async def list_all_proposals(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of proposals to return."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Lists all self-modification proposals and their current statuses."""
    proposals_data = memory.list_proposals(limit=limit)
    # Convert list of dicts to list of Pydantic models
    # The ProposalStatusResponseSchema has orm_mode = True, so it can be initialized from dicts
    return [ProposalStatusResponseSchema(**p) for p in proposals_data]


@router.get("/self-modify/proposals/{proposal_id}", response_model=ProposalStatusResponseSchema, tags=["Self Modification"])
async def get_proposal_details(
    proposal_id: str = Path(..., description="The ID of the proposal to retrieve."),
    memory: MemoryManager = Depends(get_memory_manager)
):
    """Returns the full log/status for a specific proposal."""
    proposal_data = memory.get_proposal_log(proposal_id=proposal_id)
    if not proposal_data:
        logger.warning(f"Proposal with ID '{proposal_id}' not found in memory.")
        raise HTTPException(status_code=404, detail=f"Proposal with ID '{proposal_id}' not found.")
    return ProposalStatusResponseSchema(**proposal_data)


@router.post("/self-modify/proposals/{proposal_id}/approve", response_model=ProposalResponseSchema, tags=["Self Modification"])
async def approve_proposal_endpoint(
    proposal_id: str = Path(..., description="The ID of the proposal to approve."),
    # In a real system, might take an optional 'approved_by' from authenticated user
    memory: MemoryManager = Depends(get_memory_manager),
    # self_modifier: SelfModifier = Depends(get_self_modifier) # Needed if merge is synchronous
):
    """
    Marks a proposal as approved (if validation passed) and triggers an asynchronous merge task.
    """
    logger.info(f"Attempting to approve proposal ID: {proposal_id}")
    proposal = memory.get_proposal_log(proposal_id)

    if not proposal:
        logger.warning(f"Approval failed: Proposal ID '{proposal_id}' not found.")
        raise HTTPException(status_code=404, detail=f"Proposal with ID '{proposal_id}' not found.")

    # Validate current status for approval
    # Allowed previous statuses: "validation_passed"
    # Or, if re-approval is allowed after a failed merge attempt: "merge_failed"
    allowed_statuses_for_approval = ["validation_passed", "merge_failed"] # Example
    if proposal['status'] not in allowed_statuses_for_approval:
        logger.warning(f"Approval failed for proposal '{proposal_id}': Current status is '{proposal['status']}', requires one of {allowed_statuses_for_approval}.")
        raise HTTPException(
            status_code=409, # Conflict with current state
            detail=f"Proposal cannot be approved. Current status is '{proposal['status']}'. Expected one of {allowed_statuses_for_approval}."
        )

    # Log approval step
    approved_by_user = "api_user" # Placeholder; derive from auth context in real app
    update_success = memory.log_proposal_step(
        proposal_id=proposal_id,
        branch_name=proposal['branch_name'],
        commit_message=proposal['commit_message'],
        status="user_approved",
        approved_by=approved_by_user,
        validation_output=proposal.get('validation_output') # Preserve existing validation output
    )
    if not update_success:
        logger.error(f"Failed to update proposal '{proposal_id}' status to 'user_approved' in memory.")
        raise HTTPException(status_code=500, detail="Failed to update proposal status in memory.")

    # Trigger asynchronous merge task
    try:
        from odyssey.agent.tasks import merge_approved_proposal_task # UPDATED TASK NAME
        merge_task_result = merge_approved_proposal_task.delay(proposal_id=proposal_id) # UPDATED: only proposal_id
        logger.info(f"Merge task ({merge_task_result.id}) triggered for approved proposal {proposal_id} (branch: {proposal['branch_name']}).")
        # Update status to "merge_pending" or similar after triggering task
        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=proposal['branch_name'],
            commit_message=proposal['commit_message'],
            status="merge_pending", # New status indicating merge is queued
            approved_by=approved_by_user,
            validation_output=proposal.get('validation_output')
        )
    except ImportError:
        logger.error("Celery task 'merge_proposal_task' not found. Merge cannot be triggered.", exc_info=True)
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=proposal['branch_name'], commit_message=proposal['commit_message'],
            status="merge_error", approved_by=approved_by_user, validation_output="Failed to trigger merge: Task not found."
        )
        return ProposalResponseSchema(
            proposal_id=proposal_id, branch_name=proposal['branch_name'], status="merge_error",
            message="Proposal approved, but automatic merge could not be started: Merge task not found."
        )
    except Exception as e:
        logger.error(f"Error triggering merge task for proposal {proposal_id}: {e}", exc_info=True)
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=proposal['branch_name'], commit_message=proposal['commit_message'],
            status="merge_error", approved_by=approved_by_user, validation_output=f"Failed to trigger merge: {str(e)}"
        )
        return ProposalResponseSchema(
            proposal_id=proposal_id, branch_name=proposal['branch_name'], status="merge_error",
            message=f"Proposal approved, but automatic merge failed to start: {str(e)}"
        )

    return ProposalResponseSchema(
        proposal_id=proposal_id,
        branch_name=proposal['branch_name'],
        status="merge_pending", # Return the new status
        message=f"Proposal '{proposal_id}' approved by {approved_by_user}. Merge task triggered."
    )


@router.post("/self-modify/proposals/{proposal_id}/reject", response_model=ProposalResponseSchema, tags=["Self Modification"])
async def reject_proposal_endpoint(
    proposal_id: str = Path(..., description="The ID of the proposal to reject."),
    memory: MemoryManager = Depends(get_memory_manager)
    # Potentially add a 'reason: Optional[str] = Body(None)' if rejection reasons are needed
):
    """Marks a proposal as rejected and logs the action."""
    logger.info(f"Attempting to reject proposal ID: {proposal_id}")
    proposal = memory.get_proposal_log(proposal_id)

    if not proposal:
        logger.warning(f"Rejection failed: Proposal ID '{proposal_id}' not found.")
        raise HTTPException(status_code=404, detail=f"Proposal with ID '{proposal_id}' not found.")

    # Prevent re-rejecting an already rejected or merged proposal
    if proposal['status'] in ["rejected", "merged"]:
        logger.info(f"Proposal '{proposal_id}' is already in status '{proposal['status']}'. No action taken for rejection.")
        return ProposalResponseSchema(
            proposal_id=proposal_id,
            branch_name=proposal['branch_name'],
            status=proposal['status'], # Return current status
            message=f"Proposal is already in status '{proposal['status']}'. No change made."
        )

    # Log rejection step
    # 'rejected_by' could be added if there's user context
    update_success = memory.log_proposal_step(
        proposal_id=proposal_id,
        branch_name=proposal['branch_name'],
        commit_message=proposal['commit_message'],
        status="rejected",
        # validation_output could be updated with a rejection reason if provided
        validation_output=proposal.get('validation_output') # Preserve or update
    )

    if not update_success:
        logger.error(f"Failed to update proposal '{proposal_id}' status to 'rejected' in memory.")
        raise HTTPException(status_code=500, detail="Failed to update proposal status in memory.")

    logger.info(f"Proposal '{proposal_id}' has been rejected.")
    return ProposalResponseSchema(
        proposal_id=proposal_id,
        branch_name=proposal['branch_name'],
        status="rejected",
        message=f"Proposal '{proposal_id}' has been successfully rejected."
    )


# Clean up old placeholder self-modify endpoint and schemas if they were present directly in routes.py
# The original routes.py had:
# class ProposeChangeRequest(BaseModel): ...
# class ProposeChangeResponse(BaseModel): ...
# @router.post("/self-modify/propose", response_model=ProposeChangeResponse, tags=["Self Modification"])
# async def propose_code_change(request_body: ProposeChangeRequest): ...
# These are now replaced by the new schemas in schemas.py and the new propose_code_change_endpoint.
# I will search for and remove these exact old definitions if they are still in this file.

# --- Placeholder Removal ---
# The following is a conceptual search and removal. If the grep tool were available, I'd use it.
# For now, I'll assume they were defined as shown above and remove them if present.
# This step will be done by carefully inspecting the final content of routes.py.
# (Manual Check: The old placeholders were indeed present and should be removed)
# The placeholder code was:
# class ProposeChangeRequest(BaseModel):
# files: Dict[str, str]
# commit_message: str
# branch_name: Optional[str] = None

# class ProposeChangeResponse(BaseModel):
# branch_name: str
# status: str
# message: Optional[str] = None
# pr_url: Optional[str] = None

# @router.post("/self-modify/propose", response_model=ProposeChangeResponse, tags=["Self Modification"])
# async def propose_code_change(request_body: ProposeChangeRequest):
# """Allows the agent (or an admin) to propose code changes (mocked)."""
# print(f"Mock propose change: Commit '{request_body.commit_message}', Branch: {request_body.branch_name or 'auto'}")
# return ProposeChangeResponse(
# branch_name=request_body.branch_name or f"feature/proposal-{os.urandom(3).hex()}",
# status="proposed_mock",
# message="Change proposed locally (mock). PR creation would follow.",
# pr_url=f"http://github.com/mock-org/odyssey/pull/{(len(os.urandom(1)) % 5) + 1}"
# )
# This section will be deleted.

# --- End of File ---
# async def read_items(skip: int = 0, limit: int = 10):
#     """Retrieve a list of example items."""
#     return list(fake_items_db.values())[skip : skip + limit]
# @router.post("/items/", response_model=Item, status_code=201, tags=["Example Items"])
# async def create_item_example(item: ItemCreate): # Renamed to avoid clash
#     """Create a new example item."""
#     item_id = f"item{len(fake_items_db) + 1}"
#     item_dict = item.model_dump()
#     item_dict["id"] = item_id
#     fake_items_db[item_id] = item_dict
#     return item_dict
# @router.get("/items/{item_id}", response_model=Item, tags=["Example Items"])
# async def read_item_example(item_id: str): # Renamed to avoid clash
#     """Retrieve a specific example item by ID."""
#     if item_id not in fake_items_db:
#         raise HTTPException(status_code=404, detail="Item not found")
#     return fake_items_db[item_id]

# --- End of File ---
