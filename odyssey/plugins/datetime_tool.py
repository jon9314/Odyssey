"""
Datetime tool for the Odyssey agent.
Provides current date/time and simple time calculations.
"""
import datetime
import logging
from typing import Dict, Any, Optional
from odyssey.agent.tool_manager import ToolInterface

logger = logging.getLogger("odyssey.plugins.datetime_tool")

class DateTimeTool(ToolInterface):
    """
    A tool to get the current date and time or calculate a future/past time
    based on a delta in seconds.
    """
    name: str = "datetime_tool"
    description: str = "Provides current date/time in ISO format or calculates a new date/time by adding/subtracting seconds."

    def __init__(self):
        super().__init__() # Ensures name and description are checked if defined in base

    def execute(self, delta_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Returns the current ISO formatted date/time, or a future/past date/time
        if delta_seconds is provided.

        Args:
            delta_seconds (Optional[int]): Number of seconds to add to the current time.
                                           Can be negative for past time. Defaults to None.

        Returns:
            Dict[str, Any]: A dictionary containing either the result (ISO timestamp string)
                            and status "success", or an error message and status "error".
        """
        current_time = datetime.datetime.utcnow()
        target_time = current_time

        log_message = f"[{self.name}] execute called."
        if delta_seconds is not None:
            log_message += f" delta_seconds={delta_seconds}"
            try:
                # Ensure delta_seconds is an integer
                delta = datetime.timedelta(seconds=int(delta_seconds))
                target_time = current_time + delta
            except ValueError:
                err_msg = "Invalid 'delta_seconds' value. Must be an integer."
                logger.warning(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}
            except OverflowError:
                err_msg = "'delta_seconds' resulted in a date out of range."
                logger.warning(f"[{self.name}] {err_msg}")
                return {"error": err_msg, "status": "error"}

        logger.info(log_message)
        iso_timestamp = target_time.isoformat() + "Z" # Add Z for UTC indication

        logger.info(f"[{self.name}] Returning timestamp: {iso_timestamp}")
        return {"result": iso_timestamp, "status": "success"}

    def get_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON schema for the DateTimeTool.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "delta_seconds": {
                        "type": "integer",
                        "description": "Number of seconds to add to the current UTC time. "
                                       "Can be positive (future) or negative (past). "
                                       "If not provided, current UTC time is returned."
                    }
                },
                "required": [] # No parameters are strictly required
            }
        }

if __name__ == '__main__':
    # Example usage for direct testing of the tool
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    dt_tool = DateTimeTool()

    print("Schema:", dt_tool.get_schema())

    print("\nCurrent Time:")
    print(dt_tool.execute())

    print("\nTime in 1 hour (3600 seconds):")
    print(dt_tool.execute(delta_seconds=3600))

    print("\nTime 30 minutes ago (-1800 seconds):")
    print(dt_tool.execute(delta_seconds=-1800))

    print("\nInvalid delta_seconds:")
    print(dt_tool.execute(delta_seconds="not-an-int"))

    # Test with a very large number that might overflow (platform dependent)
    # print("\nOverflow test (very large delta):")
    # print(dt_tool.execute(delta_seconds=10**18))
