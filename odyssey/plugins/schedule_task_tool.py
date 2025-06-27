"""
ScheduleTaskTool for the Odyssey agent.
Allows scheduling a tool execution for a later time using Celery.
"""
import logging
import datetime
from typing import Dict, Any, Optional

from odyssey.agent.tool_manager import ToolInterface
from odyssey.agent.celery_app import celery_app # For Celery app type hint
# from odyssey.agent.main import AppSettings # For type hinting settings
# from odyssey.agent.tasks import execute_tool_task # Import the generic task

logger = logging.getLogger("odyssey.plugins.schedule_task_tool")

class ScheduleTaskTool(ToolInterface):
    """
    A tool to schedule another tool's execution for a later time using Celery.
    It dispatches a generic 'execute_tool_task' Celery task with an ETA.
    Requires Celery app instance and AppSettings to be injected for full functionality,
    though AppSettings isn't directly used by this tool, its presence in ToolManager's
    DI context is assumed if other tools need it.
    """
    name: str = "schedule_task_tool"
    description: str = "Schedules a specified tool to be executed at a later time with given parameters."

    def __init__(self, celery_app_instance: Optional[Any] = None, settings: Optional[Any] = None):
        """
        Initializes the ScheduleTaskTool.

        Args:
            celery_app_instance: Optional. The Celery application instance, injected by ToolManager.
            settings: Optional. AppSettings instance (not directly used here but part of DI pattern).
        """
        super().__init__()
        self.celery_app = celery_app_instance # Store the injected Celery app
        self.stub_mode = False

        if not self.celery_app:
            logger.warning(f"[{self.name}] Celery app instance not provided. Operating in STUB mode.")
            self.stub_mode = True
        else:
            logger.info(f"[{self.name}] Initialized with Celery app instance.")


    def execute(self, tool_name: str, parameters: Dict[str, Any], run_at_iso: str) -> Dict[str, Any]:
        """
        Schedules a tool for later execution.

        Args:
            tool_name (str): The name of the tool to schedule.
            parameters (Dict[str, Any]): The parameters to pass to the tool's execute method.
            run_at_iso (str): ISO 8601 datetime string indicating when the task should run (UTC).
                              Example: "2024-07-16T15:30:00Z"

        Returns:
            Dict[str, Any]: A dictionary containing the Celery task ID and status "success"
                            if scheduling was successful, or an "error" message and status "error".
        """
        log_args = f"Tool: '{tool_name}', Params: {str(parameters)[:50]}..., RunAt: '{run_at_iso}'"
        logger.info(f"[{self.name}] Attempting to schedule task. {log_args}")

        if self.stub_mode:
            log_msg = f"[{self.name} STUB] Task scheduling details: {log_args}. (Celery app not available)"
            logger.info(log_msg)
            return {"result": {"message": "Task scheduling logged (STUB MODE).", "tool_name": tool_name, "parameters": parameters, "run_at_iso": run_at_iso}, "status": "success_stub_mode"}

        try:
            run_at_datetime = datetime.datetime.fromisoformat(run_at_iso.replace("Z", "+00:00"))
            # Ensure it's timezone-aware (UTC) for Celery's ETA
            if run_at_datetime.tzinfo is None:
                run_at_datetime = run_at_datetime.replace(tzinfo=datetime.timezone.utc)

            # Ensure current time is also timezone-aware for comparison
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if run_at_datetime <= now_utc:
                err_msg = f"'run_at_iso' ({run_at_iso}) must be in the future."
                logger.warning(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}

        except ValueError:
            err_msg = "Invalid 'run_at_iso' format. Please use ISO 8601 format (e.g., YYYY-MM-DDTHH:MM:SSZ)."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        try:
            # Dynamically import the generic task executor from agent.tasks
            # This avoids circular import issues if tasks.py also imports from tool_manager indirectly
            from odyssey.agent.tasks import execute_tool_task

            # Schedule the generic execute_tool_task
            task_result = execute_tool_task.apply_async(
                args=[tool_name, parameters],
                eta=run_at_datetime
            )

            success_msg = f"Task to execute tool '{tool_name}' scheduled successfully. Celery Task ID: {task_result.id}"
            logger.info(f"[{self.name}] {success_msg}")
            return {"result": {"celery_task_id": task_result.id, "scheduled_tool": tool_name, "scheduled_at": run_at_iso}, "status": "success"}

        except ImportError:
            err_msg = "Could not import 'execute_tool_task' from odyssey.agent.tasks. Ensure it's defined."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except Exception as e:
            err_msg = f"Failed to schedule task for tool '{tool_name}': {str(e)}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The name of the tool to be scheduled for later execution."
                    },
                    "parameters": {
                        "type": "object",
                        "description": "A dictionary of parameters to pass to the scheduled tool's execute method.",
                        "additionalProperties": True
                    },
                    "run_at_iso": {
                        "type": "string",
                        "format": "date-time",
                        "description": "The future time (UTC) at which the tool should be executed, in ISO 8601 format (e.g., '2024-08-01T10:00:00Z')."
                    }
                },
                "required": ["tool_name", "parameters", "run_at_iso"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock Celery App for standalone testing
    class MockCeleryApp:
        def __init__(self):
            self.task_name_map = {}
        def task(self, *args, **kwargs): # Decorator
            def decorator(func):
                # Store task by name if provided, for mock dispatch
                task_name = kwargs.get('name', func.__name__)
                self.task_name_map[task_name] = func
                return func
            return decorator

    mock_celery = MockCeleryApp()

    # Mock the generic execute_tool_task for this test
    # In a real scenario, this would be defined in odyssey.agent.tasks
    @mock_celery.task(name="odyssey.agent.tasks.execute_tool_task") # Mocking the task registration
    def mock_execute_tool_task(tool_name: str, tool_args: Dict[str, Any]):
        logger.info(f"[MockCeleryExecuteToolTask] Called with tool_name='{tool_name}', args={tool_args}")
        return f"Mock execution of {tool_name} with {tool_args}"

    # To make the dynamic import `from odyssey.agent.tasks import execute_tool_task` work in this __main__
    # we need to temporarily add this mock to sys.modules or adjust how it's imported in the tool.
    # For simplicity of this test, we'll assume the import works or bypass it if it's too complex for __main__.
    # The actual test would be an integration test with a running Celery worker.

    # For this __main__ test, let's assume the tool directly uses the mock_execute_tool_task if celery_app is a mock.
    # This requires modifying the tool for testing, or a more complex mock setup.
    # Alternative: The tool could accept the task function as a dependency for easier testing.

    # Let's test the tool with the injected mock_celery. Tool's execute will try to import.
    # To make the import work for the test, we can patch it or ensure the structure allows it.
    # For now, this test will primarily check schema and stub mode if Celery isn't fully mocked for import.

    tool = ScheduleTaskTool(celery_app_instance=celery_app) # Pass the real celery_app for structure
                                                           # but its .delay won't run without a worker/broker.
                                                           # The tool's logic will try `from odyssey.agent.tasks import execute_tool_task`
                                                           # which should find the real one if PYTHONPATH is correct.

    print("Schema:", tool.get_schema())

    # Test in STUB mode first (if celery_app_instance was None)
    stub_tool = ScheduleTaskTool(celery_app_instance=None)
    print(f"\nTool in stub mode: {stub_tool.stub_mode}")
    res_stub = stub_tool.execute(
        tool_name="calculator",
        parameters={"num1": 10, "num2": 5, "operation": "add"},
        run_at_iso=(datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).isoformat() + "Z"
    )
    print("Stub mode execution:", res_stub)


    print("\n--- Live Mode Test (requires Celery broker & worker for actual execution) ---")
    # This call will attempt to schedule the real `execute_tool_task`
    future_time_iso = (datetime.datetime.utcnow() + datetime.timedelta(seconds=30)).isoformat() + "Z"
    res_live = tool.execute(
        tool_name="calculator",
        parameters={"num1": 100, "num2": 23, "operation": "subtract"},
        run_at_iso=future_time_iso
    )
    print("Live mode scheduling attempt:", res_live)
    if res_live.get("status") == "success":
        print(f"  Task {res_live['result']['celery_task_id']} scheduled to run tool 'calculator'.")
        print("  Run a Celery worker (`celery -A odyssey.agent.celery_app worker -l INFO`) and check its logs.")

    print("\nTest with past time (should error):")
    past_time_iso = (datetime.datetime.utcnow() - datetime.timedelta(minutes=5)).isoformat() + "Z"
    res_past = tool.execute(
        tool_name="random_string_tool",
        parameters={"length": 8},
        run_at_iso=past_time_iso
    )
    print(res_past)
    assert res_past.get("status") == "error"

    print("\nTest with invalid ISO time (should error):")
    res_invalid_time = tool.execute(
        tool_name="datetime_tool",
        parameters={},
        run_at_iso="not-a-valid-iso-date"
    )
    print(res_invalid_time)
    assert res_invalid_time.get("status") == "error"
