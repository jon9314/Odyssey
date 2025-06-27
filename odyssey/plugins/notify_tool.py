"""
NotifyTool for the Odyssey agent.
Sends notifications, currently implemented for Ntfy.sh.
Requires Ntfy server URL and topic to be configured.
"""
import requests
import logging
import os # Added import
from typing import Dict, Any, Optional, List

from odyssey.agent.tool_manager import ToolInterface
# Assuming AppSettings is available for type hinting if passed via DI
# from odyssey.agent.main import AppSettings

logger = logging.getLogger("odyssey.plugins.notify_tool")

class NotifyTool(ToolInterface):
    """
    A tool to send notifications via a configured service (currently Ntfy.sh).
    Requires Ntfy settings (server_url, topic) to be provided via AppSettings.
    """
    name: str = "notify_tool"
    description: str = "Sends a notification message. Currently supports Ntfy.sh."

    def __init__(self, settings: Optional[Any] = None): # settings can be AppSettings
        """
        Initializes the NotifyTool.

        Args:
            settings: Optional. An AppSettings instance containing notification configuration.
                      Expected attributes for Ntfy: ntfy_server_url, ntfy_topic.
        """
        super().__init__()
        self.ntfy_server_url: Optional[str] = None
        self.ntfy_topic: Optional[str] = None
        self.stub_mode: bool = True

        if settings and hasattr(settings, 'ntfy_server_url') and hasattr(settings, 'ntfy_topic'):
            self.ntfy_server_url = settings.ntfy_server_url
            self.ntfy_topic = settings.ntfy_topic

            if self.ntfy_server_url and self.ntfy_topic:
                self.stub_mode = False
                logger.info(f"[{self.name}] Initialized for Ntfy. Server: {self.ntfy_server_url}, Topic: {self.ntfy_topic}")
            else:
                logger.warning(f"[{self.name}] Ntfy server URL or topic not configured. Operating in STUB mode.")
                self.stub_mode = True
        else:
            logger.warning(f"[{self.name}] Ntfy settings not provided or incomplete in AppSettings. Operating in STUB mode.")
            self.stub_mode = True

    def execute(self, message: str, title: Optional[str] = None, priority: Optional[int] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Sends a notification message.

        Args:
            message (str): The main content of the notification.
            title (Optional[str]): An optional title for the notification.
            priority (Optional[int]): Optional Ntfy message priority (1-5, 5 is highest).
            tags (Optional[List[str]]): Optional list of Ntfy tags (emojis or strings).

        Returns:
            Dict[str, Any]: Confirmation message on success or an error dictionary.
        """
        log_message_args = f"Message: '{message[:50]}...', Title: '{title}', Prio: {priority}, Tags: {tags}"
        logger.info(f"[{self.name}] Attempting to send notification. {log_message_args}")

        if self.stub_mode or not self.ntfy_server_url or not self.ntfy_topic:
            log_msg = f"[{self.name} STUB] Notification details: {log_message_args}. (Ntfy not fully configured)"
            logger.info(log_msg)
            # Per spec, "always succeed for now" in stub mode
            return {"result": "Notification logged instead of sent (STUB MODE - Ntfy not fully configured).", "status": "success_stub_mode"}

        headers = {}
        if title:
            headers['Title'] = title
        if priority is not None:
            if 1 <= priority <= 5:
                headers['Priority'] = str(priority)
            else:
                logger.warning(f"[{self.name}] Invalid Ntfy priority '{priority}', using default.")
        if tags and isinstance(tags, list):
            headers['Tags'] = ",".join(tags)

        # Ntfy endpoint is server_url/topic
        url = f"{self.ntfy_server_url.rstrip('/')}/{self.ntfy_topic.lstrip('/')}"

        try:
            response = requests.post(
                url,
                data=message.encode('utf-8'), # Ntfy expects message as request body
                headers=headers,
                timeout=10 # Short timeout for notifications
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            success_msg = f"Notification sent successfully to Ntfy topic '{self.ntfy_topic}'."
            logger.info(f"[{self.name}] {success_msg} Response status: {response.status_code}")
            return {"result": success_msg, "status": "success"}

        except requests.exceptions.Timeout:
            err_msg = f"Timeout sending notification to Ntfy server {url}."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except requests.exceptions.RequestException as e:
            err_msg = f"Error sending notification to Ntfy: {e}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except Exception as e:
            err_msg = f"An unexpected error occurred while sending notification: {str(e)}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The main content of the notification message."
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional. A title for the notification."
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Optional. Ntfy message priority (1-5, where 1 is min, 3 default, 5 is max/urgent).",
                        "enum": [1, 2, 3, 4, 5]
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional. A list of Ntfy tags (emojis or short strings) for the notification."
                    }
                },
                "required": ["message"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock AppSettings for local testing
    class MockAppSettings:
        ntfy_server_url = os.environ.get("TEST_NTFY_SERVER_URL", "https://ntfy.sh")
        ntfy_topic = os.environ.get("TEST_NTFY_TOPIC") # Needs to be set for live test

    mock_settings = MockAppSettings()

    if not mock_settings.ntfy_topic:
        print("WARNING: TEST_NTFY_TOPIC environment variable not set. Notify tool will run in STUB mode for this test.")
        print("To test live notifications, set TEST_NTFY_TOPIC (e.g., 'odyssey_agent_test_alerts').")
        # Force stub mode for the test if topic is missing
        class StubSettings:
            ntfy_server_url = "https://ntfy.sh"
            ntfy_topic = None
        mock_settings_for_stub = StubSettings()
        tool = NotifyTool(settings=mock_settings_for_stub)
    else:
        tool = NotifyTool(settings=mock_settings)

    print("\nSchema:", tool.get_schema())
    print(f"Tool operating in stub mode: {tool.stub_mode}")

    print("\n--- Test Cases ---")

    print("1. Send a simple notification:")
    res1 = tool.execute(message="Hello from Odyssey NotifyTool!")
    print(res1)

    print("\n2. Send a notification with title and priority:")
    res2 = tool.execute(
        message="This is an important alert from Odyssey.",
        title="Odyssey Alert!",
        priority=5, # Max priority for Ntfy
        tags=["warning", "rocket"]
    )
    print(res2)

    print("\n3. Attempt to send with missing message (should be caught by API schema):")
    try:
        res3 = tool.execute(title="Test Title Only") # type: ignore
        print(res3)
    except TypeError as te:
        print(f"Caught TypeError (expected for missing required arg 'message'): {te}")

    if not tool.stub_mode and mock_settings.ntfy_topic:
        print(f"\nCheck your Ntfy topic '{mock_settings.ntfy_topic}' at {mock_settings.ntfy_server_url}/{mock_settings.ntfy_topic} for messages.")
