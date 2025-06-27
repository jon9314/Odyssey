"""
ExecutePlanTool for the Odyssey agent.
Executes a sequence of tool calls as defined in a plan.
"""
import logging
from typing import Dict, Any, List, Optional

from odyssey.agent.tool_manager import ToolInterface, ToolManager # Import ToolManager for DI
# from odyssey.agent.main import AppSettings # For type hinting settings, if passed

logger = logging.getLogger("odyssey.plugins.execute_plan_tool")

class ExecutePlanTool(ToolInterface):
    """
    A tool to execute a predefined plan consisting of a sequence of tool calls.
    Each step in the plan specifies a tool name and its parameters.
    This tool requires the ToolManager to be injected to execute other tools.
    """
    name: str = "execute_plan_tool"
    description: str = "Executes a list of tool calls in sequence. Each step defines a tool_name and its parameters."

    def __init__(self, tool_manager: ToolManager, settings: Optional[Any] = None):
        """
        Initializes the ExecutePlanTool with a ToolManager instance.

        Args:
            tool_manager: An instance of the ToolManager for executing individual plan steps.
            settings: Optional. AppSettings instance (not directly used by this tool but part of DI pattern).
        """
        super().__init__()
        if not tool_manager:
            # This should ideally not happen if DI is working correctly.
            # ToolManager's discovery would skip this tool if the dependency isn't met.
            logger.error(f"[{self.name}] Critical: ToolManager instance not provided during initialization!")
            raise ValueError("ToolManager instance is required for ExecutePlanTool.")
        self.tool_manager = tool_manager
        logger.info(f"[{self.name}] Initialized with ToolManager instance.")

    def execute(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes a list of tool calls (steps) in sequence.

        Args:
            steps (List[Dict[str, Any]]): A list of steps to execute.
                Each step is a dictionary with:
                - "tool_name": str (the name of the tool to execute)
                - "parameters": Dict[str, Any] (the parameters for that tool)
                Example:
                [
                    {"tool_name": "calculator", "parameters": {"operation": "add", "a": 2, "b": 2}},
                    {"tool_name": "random_string_tool", "parameters": {"length": 6}}
                ]

        Returns:
            Dict[str, Any]: A dictionary containing:
                            - "result": A list of results from each step. Each item in the list
                                        will be the dictionary returned by the individual tool's
                                        execute method (containing its own "result"/"status" or "error").
                            - "status": "success" if all steps attempted (even if some failed internally),
                                        or "error" if the input 'steps' format is invalid.
        """
        logger.info(f"[{self.name}] Attempting to execute plan with {len(steps)} steps.")

        if not isinstance(steps, list):
            err_msg = "Invalid 'steps' format: Must be a list of step dictionaries."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        all_step_results = []
        overall_success = True # Tracks if all steps could be *attempted*

        for i, step in enumerate(steps):
            logger.info(f"[{self.name}] Executing step {i+1}/{len(steps)}: {step.get('tool_name')}")
            if not isinstance(step, dict) or "tool_name" not in step or "parameters" not in step:
                err_msg = f"Invalid format for step {i+1}. Each step must be a dict with 'tool_name' and 'parameters'."
                logger.warning(f"[{self.name}] {err_msg} - Step data: {step}")
                all_step_results.append({
                    "step": i + 1,
                    "tool_name": step.get("tool_name", "unknown"),
                    "status": "error",
                    "error": err_msg
                })
                overall_success = False # Mark plan execution as partially failed due to format
                continue # Move to next step if possible, or decide to halt plan

            tool_name = step["tool_name"]
            parameters = step.get("parameters", {}) # Default to empty dict if missing, though schema implies it's there

            if not isinstance(parameters, dict):
                err_msg = f"Invalid 'parameters' format for step {i+1} ('{tool_name}'). Must be a dictionary."
                logger.warning(f"[{self.name}] {err_msg} - Parameters data: {parameters}")
                all_step_results.append({
                    "step": i + 1,
                    "tool_name": tool_name,
                    "status": "error",
                    "error": err_msg
                })
                overall_success = False
                continue

            step_outcome = self.tool_manager.execute(tool_name, **parameters)

            # The outcome from tool_manager.execute is already a dict with "result"/"status" or "error"
            all_step_results.append({
                "step": i + 1,
                "tool_name": tool_name,
                **step_outcome # Unpack the result from the individual tool call
            })

            # Log individual step outcome
            if isinstance(step_outcome, dict) and step_outcome.get("error"):
                logger.warning(f"[{self.name}] Step {i+1} ('{tool_name}') failed: {step_outcome.get('message')} - Details: {step_outcome.get('details')}")
                # Decide if plan execution should halt on first error, or continue.
                # For now, it continues and collects all results.
            else:
                logger.info(f"[{self.name}] Step {i+1} ('{tool_name}') executed. Result snippet: {str(step_outcome.get('result', 'N/A'))[:50]}...")

        final_status = "success" if overall_success else "partial_failure" # Or "completed_with_errors"
        logger.info(f"[{self.name}] Plan execution finished. Overall status: {final_status}. Results collected for {len(all_step_results)} steps.")
        return {"result": all_step_results, "status": final_status}


    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "A list of steps to execute in sequence.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": "The name of the tool to execute for this step."
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "A dictionary of parameters to pass to the tool's execute method.",
                                    "additionalProperties": True # Allows any parameters
                                }
                            },
                            "required": ["tool_name", "parameters"]
                        }
                    }
                },
                "required": ["steps"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock ToolManager and other tools for standalone testing
    class MockTool(ToolInterface):
        def __init__(self, name, description="A mock tool"):
            self.name = name
            self.description = description
            super().__init__()

        def execute(self, **kwargs):
            logger.info(f"[MockTool:{self.name}] Executing with {kwargs}")
            if self.name == "error_tool":
                return {"error": True, "message": "This tool intentionally failed", "status": "error"}
            return {"result": f"{self.name} executed with {kwargs}", "status": "success"}

        def get_schema(self):
            return {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}}}

    mock_tm = ToolManager() # ToolManager itself does not need DI for its own __init__
    mock_tm.register(MockTool(name="tool_A"))
    mock_tm.register(MockTool(name="tool_B"))
    mock_tm.register(MockTool(name="error_tool"))


    plan_executor_tool = ExecutePlanTool(tool_manager=mock_tm)
    print("Schema:", plan_executor_tool.get_schema())

    print("\n--- Test Cases ---")

    valid_plan = {
        "steps": [
            {"tool_name": "tool_A", "parameters": {"param1": "value1"}},
            {"tool_name": "tool_B", "parameters": {"x": 10, "y": True}},
            {"tool_name": "error_tool", "parameters": {}}, # This step should fail
            {"tool_name": "tool_A", "parameters": {"paramZ": "final step"}}
        ]
    }
    print("\n1. Execute a valid plan with one failing step:")
    res1 = plan_executor_tool.execute(**valid_plan)
    import json
    print(json.dumps(res1, indent=2))
    # Expected: status "success" (plan itself executed), result is a list, one item in list has status "error"

    invalid_step_plan = {
        "steps": [
            {"tool_name": "tool_A", "parameters": {"p": 1}},
            {"tool_X_name": "tool_typo", "parameters": {}} # Invalid step structure
        ]
    }
    print("\n2. Execute a plan with an invalid step structure:")
    res2 = plan_executor_tool.execute(**invalid_step_plan)
    print(json.dumps(res2, indent=2))
    # Expected: status "partial_failure", one step result shows error from plan executor

    non_existent_tool_plan = {
        "steps": [
            {"tool_name": "tool_A", "parameters": {}},
            {"tool_name": "non_existent_tool", "parameters": {}}
        ]
    }
    print("\n3. Execute a plan with a non-existent tool:")
    res3 = plan_executor_tool.execute(**non_existent_tool_plan)
    print(json.dumps(res3, indent=2))
    # Expected: status "success", but the result for the non-existent tool step shows an error from ToolManager

    empty_plan = {"steps": []}
    print("\n4. Execute an empty plan:")
    res4 = plan_executor_tool.execute(**empty_plan)
    print(json.dumps(res4, indent=2))
    # Expected: status "success", result is an empty list

    invalid_input_format = {"steps": "not a list"}
    print("\n5. Execute with invalid 'steps' format:")
    res5 = plan_executor_tool.execute(**invalid_input_format) # type: ignore
    print(json.dumps(res5, indent=2))
    # Expected: status "error" from plan executor itself
