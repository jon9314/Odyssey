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
import subprocess
import tempfile
import shutil
import os
import shlex # For parsing command strings safely

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


@celery_app.task(bind=True, name="odyssey.agent.tasks.run_sandbox_validation_task")
def run_sandbox_validation_task(self, proposal_id: str, branch_name: str) -> Dict[str, Any]:
    """
    Performs sandbox validation for a given proposal branch.
    - Clones the repository to a temporary directory.
    - Checks out the specified branch.
    - Runs build steps and tests (simulated for now, with Docker as preferred method).
    - Updates the proposal status in MemoryManager.
    """
    task_id = self.request.id
    log_prefix = f"[CeleryTask:{task_id}:run_sandbox_validation_task -> {proposal_id} ({branch_name})]"
    logger.info(f"{log_prefix} Started.")

    from odyssey.agent.main import AppSettings
    from odyssey.agent.memory import MemoryManager
    from odyssey.agent.self_modifier import SelfModifier
    from odyssey.agent.sandbox import Sandbox

    settings: Optional[AppSettings] = None
    memory: Optional[MemoryManager] = None
    temp_repo_dir: Optional[str] = None
    original_commit_message: str = "N/A"

    try:
        settings = AppSettings()
        memory = MemoryManager(db_path=settings.memory_db_path)

        # Fetch original commit message early
        proposal_data = memory.get_proposal_log(proposal_id)
        if proposal_data and proposal_data.get('commit_message'):
            original_commit_message = proposal_data['commit_message']
        else:
            logger.warning(f"{log_prefix} Could not retrieve original commit message for proposal {proposal_id}.")


        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status="validation_in_progress",
            commit_message=original_commit_message
        )

        # 1. Create a temporary directory for the clone
        temp_repo_dir = tempfile.mkdtemp(prefix=f"odyssey_validation_{proposal_id}_")
        logger.info(f"{log_prefix} Created temporary directory for validation: {temp_repo_dir}")

        # 2. Initialize SelfModifier for the temporary directory (or use main repo path for clone source)
        # We need the main repo path to clone from, and then operate within temp_repo_dir.
        # SelfModifier needs to be able to clone settings.repo_path into temp_repo_dir.
        # Let's assume SelfModifier's _run_git_command can take a `cwd` argument,
        # or we use subprocess directly for clone.

        # Cloning the main repository (settings.repo_path) into temp_repo_dir
        # Using subprocess directly for more control over clone destination
        clone_process = subprocess.run(
            ["git", "clone", settings.repo_path, temp_repo_dir],
            capture_output=True, text=True, check=False
        )
        if clone_process.returncode != 0:
            error_msg = f"Failed to clone repository from '{settings.repo_path}' to '{temp_repo_dir}'. Error: {clone_process.stderr}"
            logger.error(f"{log_prefix} {error_msg}")
            raise Exception(error_msg)
        logger.info(f"{log_prefix} Successfully cloned repository into {temp_repo_dir}")

        # Now, SelfModifier operates on this temporary clone
        # We can re-initialize a SelfModifier instance for this path, or add cwd to _run_git_command
        # For simplicity, let's assume _run_git_command in SelfModifier can be adapted or we use it carefully.
        # A simpler approach for this task: initialize a new SelfModifier for the temp path.
        local_self_modifier = SelfModifier(repo_path=temp_repo_dir)

        # 3. Fetch and checkout the specific proposal branch
        logger.info(f"{log_prefix} Fetching and checking out branch '{branch_name}' in temporary clone.")

        # Initialize SelfModifier with the path to the temporary clone.
        # Also pass the sandbox_manager instance to this SelfModifier, configured from AppSettings.

        # Parse the test command string from settings into a list
        # Using shlex.split for safer parsing of command strings that might include quotes or spaces.
        test_command_list = shlex.split(settings.SANDBOX_DEFAULT_TEST_COMMAND)

        sandbox_manager_instance = Sandbox(
            health_check_endpoint=settings.SANDBOX_HEALTH_CHECK_ENDPOINT,
            app_port_in_container=settings.SANDBOX_APP_PORT_IN_CONTAINER,
            host_port_for_health_check=settings.SANDBOX_HOST_PORT_FOR_HEALTH_CHECK,
            test_command=test_command_list
        )
        local_self_modifier = SelfModifier(repo_path=temp_repo_dir, sandbox_manager=sandbox_manager_instance)

        # Checkout the branch in the temporary directory.
        # The `propose_code_changes` should have pushed it, so it should be available via fetch/pull.
        # First, ensure remote 'origin' is set up correctly in the clone if it's a simple file path clone.
        # A full clone already has 'origin'.
        # Fetch from origin to get all branches including the new one.
        fetch_stdout, fetch_stderr, fetch_ret = local_self_modifier._run_git_command(["fetch", "origin"], raise_on_error=False)
        if fetch_ret != 0:
            logger.warning(f"{log_prefix} 'git fetch origin' in temp clone failed. Stderr: {fetch_stderr}. Stdout: {fetch_stdout}. Branch '{branch_name}' might not be found if purely local to original repo and not pushed.")
            # This might not be critical if the branch was created from an existing remote branch or if it was pushed.

        if not local_self_modifier.checkout_branch(branch_name):
            # If checkout fails, it might be because the branch is not fetched or doesn't exist.
            # The `checkout_branch` method itself logs errors.
            error_msg = f"Failed to checkout branch '{branch_name}' in temporary clone."
            logger.error(f"{log_prefix} {error_msg}")
            # Attempt to provide more context if fetch failed significantly
            if fetch_ret !=0 :
                 error_msg += f" Previous fetch also had issues: {fetch_stderr}"
            raise Exception(error_msg)
        logger.info(f"{log_prefix} Successfully checked out branch '{branch_name}' in temporary clone.")

        # 4. Run Validation using SelfModifier's sandbox_test (which uses Sandbox.run_validation_in_docker)
        logger.info(f"{log_prefix} Handing off to SelfModifier.sandbox_test for Docker validation.")

        # `sandbox_test` now takes `repo_clone_path` and `proposal_id`.
        # `local_self_modifier` is already initialized with `repo_path=temp_repo_dir`.
        # So, we pass `temp_repo_dir` as the path and `proposal_id`.
        validation_success, validation_output_log = local_self_modifier.sandbox_test(
            repo_clone_path=temp_repo_dir, # Pass the path it should operate on
            proposal_id=proposal_id
        )

        validation_status = "validation_passed" if validation_success else "validation_failed"
        logger.info(f"{log_prefix} Docker validation completed. Status: {validation_status}.")
        # The full log is in validation_output_log

        # 5. Update MemoryManager
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status=validation_status,
            commit_message=original_commit_message, validation_output=validation_output_log # Use the full log
        )

        # Step 6: Check approval mode and conditionally trigger merge if validation passed
        if validation_status == "validation_passed":
            logger.info(f"{log_prefix} Validation passed. Checking approval mode: {settings.SELF_MOD_APPROVAL_MODE}")
            if settings.SELF_MOD_APPROVAL_MODE.lower() == "auto":
                logger.info(f"{log_prefix} Auto-approval mode enabled. Proceeding with auto-approval and triggering merge.")

                auto_approved_by = "system_auto_approval"
                # Log "auto_approved" status
                memory.log_proposal_step(
                    proposal_id=proposal_id, branch_name=branch_name, status="auto_approved",
                    commit_message=original_commit_message, approved_by=auto_approved_by,
                    validation_output=validation_output_log
                )
                logger.info(f"{log_prefix} Proposal status updated to 'auto_approved'.")

                # Trigger merge task
                try:
                    from odyssey.agent.tasks import merge_approved_proposal_task # Ensure it's imported if not at top
                    merge_task_result = merge_approved_proposal_task.delay(proposal_id=proposal_id)
                    logger.info(f"{log_prefix} Merge task ({merge_task_result.id}) triggered for auto-approved proposal {proposal_id}.")

                    # Log "merge_pending" status
                    memory.log_proposal_step(
                        proposal_id=proposal_id, branch_name=branch_name, status="merge_pending",
                        commit_message=original_commit_message, approved_by=auto_approved_by,
                        validation_output=validation_output_log
                    )
                    logger.info(f"{log_prefix} Proposal status updated to 'merge_pending'.")

                except Exception as e_merge_trigger:
                    logger.error(f"{log_prefix} Failed to trigger merge task for auto-approved proposal: {e_merge_trigger}", exc_info=True)
                    # Log this failure back to the proposal
                    memory.log_proposal_step(
                        proposal_id=proposal_id, branch_name=branch_name, status="merge_trigger_failed", # New status
                        commit_message=original_commit_message, approved_by=auto_approved_by,
                        validation_output=validation_output_log + f"\nERROR: Auto-merge trigger failed: {str(e_merge_trigger)}"
                    )
            else: # Manual mode
                logger.info(f"{log_prefix} Manual approval mode. Proposal '{proposal_id}' awaiting manual approval via API.")

        return {"proposal_id": proposal_id, "status": validation_status, "output": validation_output_log}

    except Exception as e:
        logger.error(f"{log_prefix} Task critically failed. Error: {e}", exc_info=True)
        if memory:  # Attempt to log failure if possible
            try:
                memory.log_proposal_step(
                    proposal_id=proposal_id, branch_name=branch_name, status="validation_error",
                    commit_message=original_commit_message, validation_output=f"Task error: {str(e)}"
                )
            except Exception as log_e:
                logger.error(f"{log_prefix} Failed to log validation_error status to memory: {log_e}", exc_info=True)
        raise
    finally:
        if memory:
            memory.close()
            logger.debug(f"{log_prefix} MemoryManager closed.")
        if temp_repo_dir and os.path.exists(temp_repo_dir):
            try:
                shutil.rmtree(temp_repo_dir)
                logger.info(f"{log_prefix} Successfully removed temporary directory: {temp_repo_dir}")
            except Exception as e_clean:
                logger.error(f"{log_prefix} Failed to remove temporary directory '{temp_repo_dir}': {e_clean}", exc_info=True)


@celery_app.task(bind=True, name="odyssey.agent.tasks.merge_approved_proposal_task")
def merge_approved_proposal_task(self, proposal_id: str) -> Dict[str, Any]: # Removed branch_name as it's in proposal log
    """
    Merges an approved code proposal into the main development branch.
    - Fetches proposal details from MemoryManager.
    - Uses SelfModifier to perform the merge operation.
    - Updates the proposal status in MemoryManager.
    """
    task_id = self.request.id
    # Branch name will be fetched from proposal log
    log_prefix = f"[CeleryTask:{task_id}:merge_approved_proposal_task -> {proposal_id}]"
    logger.info(f"{log_prefix} Started.")

    from odyssey.agent.main import AppSettings
    from odyssey.agent.memory import MemoryManager
    from odyssey.agent.self_modifier import SelfModifier

    settings: Optional[AppSettings] = None
    memory: Optional[MemoryManager] = None
    self_modifier: Optional[SelfModifier] = None

    # Fields to preserve from original proposal log
    branch_name: Optional[str] = None
    commit_message: str = "N/A"
    approved_by: Optional[str] = None
    validation_output_original: Optional[str] = None


    try:
        settings = AppSettings()
        memory = MemoryManager(db_path=settings.memory_db_path)
        self_modifier = SelfModifier(repo_path=settings.repo_path) # Operates on the main repo

        proposal_data = memory.get_proposal_log(proposal_id)
        if not proposal_data:
            logger.error(f"{log_prefix} Proposal {proposal_id} not found in memory. Cannot proceed.")
            # This task shouldn't be called if proposal doesn't exist, but good to check.
            raise ValueError(f"Proposal {proposal_id} not found for merge.")

        branch_name = proposal_data['branch_name']
        commit_message = proposal_data['commit_message']
        approved_by = proposal_data.get('approved_by')
        validation_output_original = proposal_data.get('validation_output')

        log_prefix = f"[CeleryTask:{task_id}:merge_approved_proposal_task -> {proposal_id} ({branch_name})]" # Update log_prefix with branch_name

        if proposal_data['status'] not in ["user_approved", "merge_pending"]: # merge_pending if retrying
            logger.warning(f"{log_prefix} Proposal status is '{proposal_data['status']}', not 'user_approved' or 'merge_pending'. Merge will not proceed.")
            # Update status to reflect this, perhaps "merge_skipped_status" or just log and return.
            # For now, we'll let it try to proceed but SelfModifier might also have checks.
            # Better to fail early if status is not right.
            raise Exception(f"Proposal status is '{proposal_data['status']}'. Merge requires 'user_approved' or 'merge_pending'.")


        logger.info(f"{log_prefix} Attempting to merge branch '{branch_name}'.")
        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status="merge_in_progress",
            commit_message=commit_message, approved_by=approved_by,
            validation_output=validation_output_original
        )

        # Perform the merge using SelfModifier
        # Assuming 'main' is the target branch, this could be configurable via AppSettings
        target_main_branch = settings.get("main_branch_name", "main") # Example: get from settings or default

        merge_success, merge_message = self_modifier.merge_branch(
            branch_to_merge=branch_name,
            target_branch=target_main_branch,
            delete_branch_after_merge=True # Typically true for feature branches
        )

        final_status = "merged" if merge_success else "merge_failed"
        final_validation_output = f"{validation_output_original or ''} | Merge attempt: {merge_message}"

        if merge_success:
            logger.info(f"{log_prefix} Merge successful for branch '{branch_name}' into '{target_main_branch}'. Message: {merge_message}")
        else:
            logger.error(f"{log_prefix} Merge failed for branch '{branch_name}'. Message: {merge_message}")

        memory.log_proposal_step(
            proposal_id=proposal_id, branch_name=branch_name, status=final_status,
            commit_message=commit_message, approved_by=approved_by,
            validation_output=final_validation_output.strip(" | ")
        )

        return {"proposal_id": proposal_id, "status": final_status, "message": merge_message}

    except Exception as e:
        logger.error(f"{log_prefix} Task critically failed. Error: {e}", exc_info=True)
        if memory: # Attempt to log failure status
            try:
                # Ensure branch_name is available if error happened early
                if not branch_name and proposal_id: # Try to fetch if not already set
                    prop_data_for_error = memory.get_proposal_log(proposal_id)
                    if prop_data_for_error:
                        branch_name = prop_data_for_error.get('branch_name', 'unknown_branch_on_error')
                        commit_message = prop_data_for_error.get('commit_message', commit_message)
                        approved_by = prop_data_for_error.get('approved_by', approved_by)
                        validation_output_original = prop_data_for_error.get('validation_output', validation_output_original)


                current_vo = validation_output_original or ""
                error_update_vo = f"{current_vo} | Merge task error: {str(e)}".strip(" | ")

                memory.log_proposal_step(
                    proposal_id=proposal_id,
                    branch_name=branch_name or "unknown_branch", # Ensure branch_name is not None
                    status="merge_error",
                    commit_message=commit_message,
                    approved_by=approved_by,
                    validation_output=error_update_vo
                )
            except Exception as log_e:
                logger.error(f"{log_prefix} Failed to log merge_error status to memory: {log_e}", exc_info=True)
        raise
    finally:
        if memory:
            memory.close()
            logger.debug(f"{log_prefix} MemoryManager closed.")
