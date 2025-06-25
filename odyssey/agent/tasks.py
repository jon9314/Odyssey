"""
Celery tasks for the Odyssey agent.

This module defines background tasks that can be executed asynchronously by Celery workers.
These tasks are automatically discovered by the Celery application instance defined
in `odyssey.agent.celery_app` due to the `include` configuration.

Each task should ideally:
- Be decorated with `@celery_app.task`.
- Use `bind=True` if it needs access to the task instance itself (e.g., for `self.request.id`).
- Log its start, arguments, completion (with result), or errors using Python's `logging`.
  Include the task ID in log messages for better traceability.
"""
import time
import logging
from typing import Any, Dict, Optional

from .celery_app import celery_app # Import the Celery app instance

# Use a more specific logger name for Celery tasks
logger = logging.getLogger("odyssey.agent.tasks")

@celery_app.task(bind=True)
def add_numbers(self, a: float, b: float) -> float:
    """
    A simple Celery task that adds two numbers.
    Logs its execution steps.

    Args:
        a: The first number.
        b: The second number.

    Returns:
        The sum of a and b.
    """
    task_id = self.request.id
    logger.info(f"[CeleryTask:{task_id}] Task 'add_numbers' started. Arguments: a={a}, b={b}")
    try:
        result = a + b
        logger.info(f"[CeleryTask:{task_id}] Task 'add_numbers' completed successfully. Result: {result}")
        return result
    except Exception as e:
        logger.error(f"[CeleryTask:{task_id}] Task 'add_numbers' failed. Error: {e}", exc_info=True)
        raise # Re-raise the exception so Celery knows the task failed

@celery_app.task(bind=True)
def simulate_long_task(self, duration_seconds: int, message: str = "Simulating work") -> str:
    """
    A Celery task that simulates a long-running operation by sleeping for a specified duration.
    Logs its progress.

    Args:
        duration_seconds: The number of seconds to sleep.
        message: A message to include in log output.

    Returns:
        A string indicating successful completion and the duration.
    """
    task_id = self.request.id
    logger.info(f"[CeleryTask:{task_id}] Task 'simulate_long_task' started. Duration: {duration_seconds}s, Message: '{message}'")

    try:
        for i in range(duration_seconds):
            time.sleep(1)
            logger.debug(f"[CeleryTask:{task_id}] 'simulate_long_task' progress: {i+1}/{duration_seconds} seconds elapsed.")

        result_message = f"Simulated task '{message}' completed after {duration_seconds} seconds."
        logger.info(f"[CeleryTask:{task_id}] Task 'simulate_long_task' completed successfully. {result_message}")
        return result_message
    except Exception as e:
        logger.error(f"[CeleryTask:{task_id}] Task 'simulate_long_task' failed. Error: {e}", exc_info=True)
        raise

@celery_app.task(bind=True)
def potentially_failing_task(self, succeed: bool = True):
    """
    A task that can be made to succeed or fail based on an argument.
    Used for testing error handling and logging.
    """
    task_id = self.request.id
    logger.info(f"[CeleryTask:{task_id}] Task 'potentially_failing_task' started. Will succeed: {succeed}")
    if succeed:
        result = "Task succeeded as intended."
        logger.info(f"[CeleryTask:{task_id}] {result}")
        return result
    else:
        error_message = "Task failed intentionally for testing."
        logger.error(f"[CeleryTask:{task_id}] {error_message}")
        raise ValueError(error_message)

@celery_app.task(bind=True, name="odyssey.agent.tasks.execute_tool_task", acks_late=True, reject_on_worker_lost=True)
def execute_tool_task(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
    """
    A generic Celery task to execute a specified tool from the ToolManager.
    This task will initialize its own instances of AppSettings, MemoryManager,
    OllamaClient, and ToolManager within the Celery worker context for isolation.

    Args:
        tool_name (str): The name of the tool to execute.
        tool_args (Dict[str, Any]): A dictionary of arguments to pass to the tool's execute method.

    Returns:
        Any: The result of the tool's execution. If the tool returns an error dictionary
             that indicates a tool-level failure, this task will re-raise an exception
             to mark the Celery task as FAILED. Successful tool execution results are returned directly.

    Raises:
        ValueError: If the specified tool is not found by the ToolManager.
        Exception: If the tool execution itself results in an error dictionary,
                   or if any other unexpected error occurs during setup or execution.
    """
    task_id = self.request.id
    log_prefix = f"[CeleryTask:{task_id}:execute_tool_task -> {tool_name}]"
    logger.info(f"{log_prefix} Started. Args (snippet): {str(tool_args)[:100]}...")

    from odyssey.agent.main import AppSettings
    from odyssey.agent.memory import MemoryManager
    from odyssey.agent.ollama_client import OllamaClient
    from odyssey.agent.tool_manager import ToolManager

    current_settings: Optional[AppSettings] = None
    current_memory_manager: Optional[MemoryManager] = None
    # OllamaClient and ToolManager are initialized within the try block

    try:
        logger.debug(f"{log_prefix} Initializing components in worker.")
        current_settings = AppSettings()

        current_memory_manager = MemoryManager(db_path=current_settings.memory_db_path)
        logger.debug(f"{log_prefix} MemoryManager initialized.")

        current_ollama_client = OllamaClient(
            local_url=current_settings.ollama_local_url,
            remote_url=current_settings.ollama_remote_url,
            default_model=current_settings.ollama_default_model,
            request_timeout=current_settings.ollama_request_timeout
        )
        logger.debug(f"{log_prefix} OllamaClient initialized.")

        current_tool_manager = ToolManager(
            memory_manager=current_memory_manager,
            ollama_client=current_ollama_client,
            celery_app_instance=celery_app,
            app_settings=current_settings
        )
        current_tool_manager.discover_and_register_plugins(plugin_dir_name="plugins")
        logger.info(f"{log_prefix} ToolManager initialized with {len(current_tool_manager.list_tools())} tools.")

        if tool_name not in current_tool_manager.list_tools():
            err_msg = f"Tool '{tool_name}' not found by ToolManager. Available: {current_tool_manager.list_tools()}"
            logger.error(f"{log_prefix} {err_msg}")
            raise ValueError(err_msg)

        logger.info(f"{log_prefix} Executing tool '{tool_name}'.")
        result = current_tool_manager.execute(tool_name, **tool_args)

        if isinstance(result, dict) and result.get("error"):
            tool_error_message = result.get('message', 'Tool execution failed.')
            tool_error_details = result.get('details', '')
            full_tool_error = f"Tool '{tool_name}' error: {tool_error_message} Details: {tool_error_details}"
            logger.error(f"{log_prefix} {full_tool_error}")
            raise Exception(full_tool_error)

        logger.info(f"{log_prefix} Tool '{tool_name}' execution finished successfully. Result snippet: {str(result)[:100]}...")
        return result

    except Exception as e:
        logger.error(f"{log_prefix} Task critically failed. Error: {e}", exc_info=True)
        # Re-raise with Celery's method to ensure proper failure state and traceback storage
        # self.reraise was not working as expected, direct raise is more common.
        raise
    finally:
        if current_memory_manager:
            try:
                current_memory_manager.close()
                logger.debug(f"{log_prefix} MemoryManager closed.")
            except Exception as e_close:
                logger.error(f"{log_prefix} Error closing MemoryManager: {e_close}", exc_info=True)


@celery_app.task(bind=True, name="odyssey.agent.tasks.validate_proposal_task")
def validate_proposal_task(self, proposal_id: str, branch_name: str) -> Dict[str, Any]:
    """
    (STUB) Simulates validation of a code proposal.
    In a real scenario, this would involve:
    1. Checking out the specified branch.
    2. Running linters, tests, and other quality checks.
    3. Reporting results.
    Updates the proposal status in MemoryManager.
    """
    task_id = self.request.id
    log_prefix = f"[CeleryTask:{task_id}:validate_proposal_task -> {proposal_id} ({branch_name})]"
    logger.info(f"{log_prefix} Started.")

    # Dependency imports inside the task for worker context
    from odyssey.agent.main import AppSettings
    from odyssey.agent.memory import MemoryManager
    # from odyssey.agent.self_modifier import SelfModifier # If needed for checkout

    settings: Optional[AppSettings] = None
    memory: Optional[MemoryManager] = None
    # self_modifier_instance: Optional[SelfModifier] = None

    try:
        settings = AppSettings()
        memory = MemoryManager(db_path=settings.memory_db_path)
        # self_modifier_instance = SelfModifier(repo_path=settings.repo_path) # Assuming repo_path is in settings

        logger.info(f"{log_prefix} Simulating proposal validation...")
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status="validation_in_progress",
            commit_message=memory.get_proposal_log(proposal_id)['commit_message'] # Get existing commit message
        )

        # Simulate validation work (e.g., running tests)
        time.sleep(5) # Simulate some work

        # Simulate a validation outcome (e.g., randomly pass or fail for stub)
        import random
        validation_passed = random.choice([True, True, False]) # Higher chance of passing for testing flow
        validation_output = ""

        if validation_passed:
            validation_status = "validation_passed"
            validation_output = "All checks passed. Code quality is good. Tests are green."
            logger.info(f"{log_prefix} Validation simulation: PASSED. Output: {validation_output}")
        else:
            validation_status = "validation_failed"
            validation_output = "Validation failed: Linter errors found. Unit test 'test_critical_feature' failed."
            logger.warning(f"{log_prefix} Validation simulation: FAILED. Output: {validation_output}")

        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=branch_name,
            commit_message=memory.get_proposal_log(proposal_id)['commit_message'], # Re-fetch in case it changed
            status=validation_status,
            validation_output=validation_output
        )
        return {"proposal_id": proposal_id, "status": validation_status, "output": validation_output}

    except Exception as e:
        logger.error(f"{log_prefix} Task critically failed. Error: {e}", exc_info=True)
        if memory and proposal_id and branch_name: # Attempt to log failure if possible
            try:
                cm = memory.get_proposal_log(proposal_id)['commit_message']
                memory.log_proposal_step(proposal_id=proposal_id, branch_name=branch_name, status="validation_error",
                                         commit_message=cm, validation_output=f"Task error: {str(e)}")
            except Exception as log_e:
                logger.error(f"{log_prefix} Failed to log validation_error status to memory: {log_e}", exc_info=True)
        raise
    finally:
        if memory:
            memory.close()
            logger.debug(f"{log_prefix} MemoryManager closed.")


@celery_app.task(bind=True, name="odyssey.agent.tasks.merge_proposal_task")
def merge_proposal_task(self, proposal_id: str, branch_name: str) -> Dict[str, Any]:
    """
    (STUB) Simulates merging an approved code proposal.
    In a real scenario, this would involve:
    1. Checking out the target branch (e.g., main/master).
    2. Merging the feature branch (`branch_name`) into it.
    3. Handling merge conflicts (or failing if not resolvable automatically).
    4. Pushing the changes.
    Updates the proposal status in MemoryManager.
    """
    task_id = self.request.id
    log_prefix = f"[CeleryTask:{task_id}:merge_proposal_task -> {proposal_id} ({branch_name})]"
    logger.info(f"{log_prefix} Started.")

    from odyssey.agent.main import AppSettings
    from odyssey.agent.memory import MemoryManager
    # from odyssey.agent.self_modifier import SelfModifier

    settings: Optional[AppSettings] = None
    memory: Optional[MemoryManager] = None
    # self_modifier_instance: Optional[SelfModifier] = None

    try:
        settings = AppSettings()
        memory = MemoryManager(db_path=settings.memory_db_path)
        # self_modifier_instance = SelfModifier(repo_path=settings.repo_path)

        original_proposal = memory.get_proposal_log(proposal_id)
        if not original_proposal:
            logger.error(f"{log_prefix} Proposal {proposal_id} not found in memory. Cannot proceed with merge.")
            raise ValueError(f"Proposal {proposal_id} not found for merge.")

        current_commit_message = original_proposal['commit_message']
        current_approved_by = original_proposal.get('approved_by')


        logger.info(f"{log_prefix} Simulating proposal merge...")
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status="merge_in_progress",
            commit_message=current_commit_message, approved_by=current_approved_by,
            validation_output=original_proposal.get('validation_output')
        )

        # Simulate merge work
        time.sleep(3) # Simulate git operations

        # Simulate a merge outcome
        import random
        merge_succeeded = random.choice([True, False]) # Simple random for stub

        if merge_succeeded:
            merge_status = "merged"
            logger.info(f"{log_prefix} Merge simulation: SUCCEEDED for branch '{branch_name}'.")
            # In a real scenario, SelfModifier would do the merge and push.
            # self_modifier_instance.merge_and_push(branch_name, target_branch="main")
        else:
            merge_status = "merge_failed"
            logger.warning(f"{log_prefix} Merge simulation: FAILED for branch '{branch_name}'. Possible conflicts or push errors.")
            # Additional details about failure could be logged by SelfModifier.

        memory.log_proposal_step(
            proposal_id=proposal_id,
            branch_name=branch_name,
            commit_message=current_commit_message,
            status=merge_status,
            approved_by=current_approved_by,
            validation_output=original_proposal.get('validation_output') # Preserve validation, or add merge output
        )
        return {"proposal_id": proposal_id, "status": merge_status, "branch": branch_name}

    except Exception as e:
        logger.error(f"{log_prefix} Task critically failed. Error: {e}", exc_info=True)
        if memory and proposal_id and branch_name:
            try:
                original_prop_data = memory.get_proposal_log(proposal_id)
                cm = original_prop_data['commit_message'] if original_prop_data else "N/A"
                ab = original_prop_data.get('approved_by') if original_prop_data else None
                vo = original_prop_data.get('validation_output') if original_prop_data else None
                memory.log_proposal_step(proposal_id=proposal_id, branch_name=branch_name, status="merge_error",
                                         commit_message=cm, approved_by=ab, validation_output=vo + f" | Merge task error: {str(e)}")
            except Exception as log_e:
                logger.error(f"{log_prefix} Failed to log merge_error status to memory: {log_e}", exc_info=True)
        raise
    finally:
        if memory:
            memory.close()
            logger.debug(f"{log_prefix} MemoryManager closed.")
```
