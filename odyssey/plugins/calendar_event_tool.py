"""
CalendarEventTool for the Odyssey agent.
Allows adding and listing events on a Google Calendar.
Requires Google Calendar API to be enabled and a service account with appropriate permissions.
"""
import os
import logging
import datetime
from typing import Dict, Any, Optional, List

from odyssey.agent.tool_manager import ToolInterface
# Attempt to import Google Calendar libraries
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

# AppSettings will be injected if the tool is instantiated by the enhanced ToolManager
# from odyssey.agent.main import AppSettings # For type hinting, if settings object is passed

logger = logging.getLogger("odyssey.plugins.calendar_event_tool")

class CalendarEventTool(ToolInterface):
    """
    A tool to interact with Google Calendar. Supports adding new events and
    listing existing events within a specified time range.
    Requires GOOGLE_APPLICATION_CREDENTIALS environment variable to be set
    with the path to a valid Google Cloud service account JSON key file
    that has permissions to access the target calendar.
    """
    name: str = "calendar_event_tool"
    description: str = "Manages Google Calendar events. Can add new events or list existing events for a specified calendar."

    def __init__(self, settings: Optional[Any] = None): # settings can be AppSettings instance
        """
        Initializes the CalendarEventTool.

        Args:
            settings: Optional. An object containing application settings, expected to have
                      `google_application_credentials` (path to JSON key file) and
                      `default_calendar_id`. If not provided, the tool will try to
                      read credentials path from the environment variable directly.
        """
        super().__init__()
        self.service = None
        self.stub_mode = False
        self.default_calendar_id = "primary" # Default

        creds_path = None
        if settings and hasattr(settings, 'google_application_credentials'):
            creds_path = settings.google_application_credentials
            logger.info(f"[{self.name}] Received credentials path from settings: {'********' if creds_path else 'None'}")
        if not creds_path: # Fallback to environment variable if not in settings or settings not passed
            creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            logger.info(f"[{self.name}] Using GOOGLE_APPLICATION_CREDENTIALS from env: {'********' if creds_path else 'None'}")

        if settings and hasattr(settings, 'default_calendar_id'):
            self.default_calendar_id = settings.default_calendar_id
            logger.info(f"[{self.name}] Using default calendar ID from settings: {self.default_calendar_id}")
        else: # Fallback for calendar ID if not in settings
            self.default_calendar_id = os.environ.get('DEFAULT_CALENDAR_ID', 'primary')
            logger.info(f"[{self.name}] Using DEFAULT_CALENDAR_ID from env (or 'primary' default): {self.default_calendar_id}")


        if not GOOGLE_LIBS_AVAILABLE:
            logger.warning(f"[{self.name}] Google Calendar client libraries not found. Tool will operate in stub mode.")
            self.stub_mode = True
            return

        if not creds_path:
            logger.warning(f"[{self.name}] GOOGLE_APPLICATION_CREDENTIALS not set. Tool will operate in stub mode.")
            self.stub_mode = True
            return

        if not os.path.exists(creds_path):
            logger.warning(f"[{self.name}] Credentials file not found at '{creds_path}'. Tool will operate in stub mode.")
            self.stub_mode = True
            return

        try:
            # Scopes required for reading and writing calendar events
            scopes = ['https://www.googleapis.com/auth/calendar']
            creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
            self.service = build('calendar', 'v3', credentials=creds)
            logger.info(f"[{self.name}] Google Calendar service initialized successfully for calendar ID: {self.default_calendar_id}.")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to initialize Google Calendar service: {e}", exc_info=True)
            self.stub_mode = True
            logger.warning(f"[{self.name}] Operating in stub mode due to initialization error.")


    def _add_event(self, title: str, start_time_iso: str, end_time_iso: str, description: Optional[str] = None, calendar_id: Optional[str] = None) -> Dict[str, Any]:
        if self.stub_mode or not self.service:
            logger.info(f"[{self.name} STUB] Add event: Title='{title}', Start='{start_time_iso}', End='{end_time_iso}'")
            return {"result": {"id": "stub_event_123", "summary": title, "status": "confirmed_stub"}, "status": "success_stub_mode"}

        try:
            # Validate and parse ISO strings. Google API expects datetime objects or specific string formats.
            # Example: '2024-07-16T10:00:00Z' or '2024-07-16T10:00:00-07:00'
            # For simplicity, ensure input strings are correctly formatted by the caller.
            # The API client handles timezone conversions if timezone is specified in ISO string.
            # If no timezone, it assumes calendar's default timezone or UTC depending on API.

            event_body = {
                'summary': title,
                'description': description if description else '',
                'start': {'dateTime': start_time_iso}, # Assumes ISO format with timezone or UTC (Z)
                'end': {'dateTime': end_time_iso},
            }

            target_calendar_id = calendar_id if calendar_id else self.default_calendar_id
            created_event = self.service.events().insert(calendarId=target_calendar_id, body=event_body).execute()
            logger.info(f"[{self.name}] Event created: ID '{created_event.get('id')}', Summary: '{created_event.get('summary')}' on calendar '{target_calendar_id}'")
            return {"result": {"id": created_event.get('id'), "summary": created_event.get('summary'), "link": created_event.get('htmlLink')}, "status": "success"}
        except HttpError as e:
            err_content = e.resp.reason if hasattr(e.resp, 'reason') else str(e)
            try: # Try to parse more specific error from Google
                err_details = json.loads(e.content).get('error', {}).get('message', err_content)
                err_content = err_details
            except: pass
            logger.error(f"[{self.name}] Google API error adding event: {err_content}", exc_info=True)
            return {"error": f"Google API error: {err_content}", "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error adding event: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}", "status": "error"}

    def _list_events(self, from_time_iso: Optional[str] = None, to_time_iso: Optional[str] = None, calendar_id: Optional[str] = None, max_results: int = 20) -> Dict[str, Any]:
        if self.stub_mode or not self.service:
            logger.info(f"[{self.name} STUB] List events: From='{from_time_iso}', To='{to_time_iso}'")
            return {"result": [{"id": "stub_event_A", "summary": "Stub Meeting 1", "start": {"dateTime": "..."}}, {"id": "stub_event_B", "summary": "Stub Appointment", "start": {"dateTime": "..."}}], "status": "success_stub_mode"}

        try:
            now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC
            time_min = from_time_iso if from_time_iso else now

            target_calendar_id = calendar_id if calendar_id else self.default_calendar_id

            events_result = self.service.events().list(
                calendarId=target_calendar_id,
                timeMin=time_min,
                timeMax=to_time_iso, # Optional, if None API might use a default range or list all future
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            items = events_result.get('items', [])
            processed_events = []
            for event in items:
                processed_events.append({
                    "id": event.get('id'),
                    "summary": event.get('summary'),
                    "start": event.get('start', {}).get('dateTime') or event.get('start', {}).get('date'),
                    "end": event.get('end', {}).get('dateTime') or event.get('end', {}).get('date'),
                    "description": event.get('description'),
                    "link": event.get('htmlLink')
                })
            logger.info(f"[{self.name}] Listed {len(processed_events)} events from calendar '{target_calendar_id}'.")
            return {"result": processed_events, "status": "success"}
        except HttpError as e:
            err_content = e.resp.reason if hasattr(e.resp, 'reason') else str(e)
            try:
                err_details = json.loads(e.content).get('error', {}).get('message', err_content)
                err_content = err_details
            except: pass
            logger.error(f"[{self.name}] Google API error listing events: {err_content}", exc_info=True)
            return {"error": f"Google API error: {err_content}", "status": "error"}
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error listing events: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}", "status": "error"}

    def execute(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Executes a calendar action: 'add' or 'list'.

        Args for 'add':
            title (str): Title of the event.
            start_time (str): ISO 8601 datetime string for event start.
            end_time (str): ISO 8601 datetime string for event end.
            description (Optional[str]): Description of the event.
            calendar_id (Optional[str]): Specific calendar ID to use (overrides default).

        Args for 'list':
            from_time (Optional[str]): ISO 8601 datetime string for start of range. Defaults to now.
            to_time (Optional[str]): ISO 8601 datetime string for end of range.
            calendar_id (Optional[str]): Specific calendar ID to use (overrides default).
            max_results (Optional[int]): Max number of events to return. Defaults to 20.

        Returns:
            Dict[str, Any]: Result of the action or an error dictionary.
        """
        logger.info(f"[{self.name}] execute called. Action: '{action}', Args: {kwargs}")
        action = action.lower()

        if action == "add":
            if not all(k in kwargs for k in ["title", "start_time", "end_time"]):
                return {"error": "Missing required arguments for 'add' action: title, start_time, end_time.", "status": "error"}
            return self._add_event(
                title=kwargs["title"],
                start_time_iso=kwargs["start_time"],
                end_time_iso=kwargs["end_time"],
                description=kwargs.get("description"),
                calendar_id=kwargs.get("calendar_id")
            )
        elif action == "list":
            return self._list_events(
                from_time_iso=kwargs.get("from_time"),
                to_time_iso=kwargs.get("to_time"),
                calendar_id=kwargs.get("calendar_id"),
                max_results=kwargs.get("max_results", 20)
            )
        else:
            err_msg = f"Invalid action: '{action}'. Must be 'add' or 'list'."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The action to perform: 'add' or 'list'.",
                        "enum": ["add", "list"]
                    },
                    "title": {
                        "type": "string",
                        "description": "Title of the event (for 'add' action)."
                    },
                    "start_time": {
                        "type": "string",
                        "format": "date-time",
                        "description": "ISO 8601 datetime string for event start (for 'add' action). E.g., '2024-07-16T10:00:00Z' or '2024-07-16T10:00:00-07:00'."
                    },
                    "end_time": {
                        "type": "string",
                        "format": "date-time",
                        "description": "ISO 8601 datetime string for event end (for 'add' action)."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description for the event (for 'add' action)."
                    },
                    "from_time": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Optional ISO 8601 datetime string for the start of the range to list events (for 'list' action). Defaults to current time."
                    },
                    "to_time": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Optional ISO 8601 datetime string for the end of the range to list events (for 'list' action)."
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Optional. Specific Google Calendar ID to use (e.g., 'primary', or an email address). Overrides default."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Optional. Maximum number of events to return for 'list' action.",
                        "default": 20
                    }
                },
                "required": ["action"],
                # Conditional requirements based on 'action' are complex for basic JSON schema.
                # Typically handled by validation logic within the 'execute' method or separate schemas per action.
                # For LLM use, a more detailed description field or separate tools might be better.
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # To test this locally:
    # 1. Ensure GOOGLE_LIBS_AVAILABLE is True (pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib)
    # 2. Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to the path of your service account JSON key.
    #    The service account needs permission to manage events on the target calendar.
    #    (Share the calendar with the service account's email address with "Make changes to events" permission).
    # 3. Optionally set DEFAULT_CALENDAR_ID env var or pass it via mock settings.

    class MockAppSettings: # Mock settings for local testing
        google_application_credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        default_calendar_id = os.environ.get('DEFAULT_CALENDAR_ID', 'primary')

    mock_settings = MockAppSettings()
    tool = CalendarEventTool(settings=mock_settings)

    print("Schema:", tool.get_schema())
    print(f"Tool operating in stub mode: {tool.stub_mode}")

    if tool.stub_mode:
        print("\n--- Running in STUB mode (Google API not configured or unavailable) ---")

    print("\n--- Test List Events (Last 2, default calendar) ---")
    # Get current time and time in 1 day for list range
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    tomorrow_iso = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat() + "Z"
    list_res = tool.execute(action="list", from_time=now_iso, to_time=tomorrow_iso, max_results=5)
    print(list_res)

    print("\n--- Test Add Event ---")
    # Example: Add an event for 1 hour from now, lasting 30 minutes
    start_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    end_dt = start_dt + datetime.timedelta(minutes=30)
    add_res = tool.execute(
        action="add",
        title="Odyssey Test Event via Tool",
        start_time=start_dt.isoformat() + "Z",
        end_time=end_dt.isoformat() + "Z",
        description="This event was created by the CalendarEventTool test."
    )
    print(add_res)

    if add_res.get("status") == "success" and not tool.stub_mode:
        event_id = add_res.get("result", {}).get("id")
        print(f"Event created with ID: {event_id}. Check your calendar!")
        print("Pausing for a moment to allow Google Calendar to sync if you want to verify...")
        # time.sleep(10) # Uncomment if you want to manually check calendar
        # TODO: Add a test to delete this event if an event_id was returned.
    elif tool.stub_mode and add_res.get("status") == "success_stub_mode":
        print("Add event stub executed.")
    else:
        print("Failed to add event or running in stub mode without successful stub execution.")

    print("\n--- Test List Events Again (should include new event if not stubbed) ---")
    list_res_after_add = tool.execute(action="list", from_time=now_iso, to_time=tomorrow_iso, max_results=5)
    print(list_res_after_add)

    print("\n--- Test Invalid Action ---")
    invalid_action_res = tool.execute(action="delete", event_id="some_id")
    print(invalid_action_res)
    assert invalid_action_res.get("status") == "error"

    print("\n--- Test Add Event Missing Params ---")
    missing_param_res = tool.execute(action="add", title="Incomplete Event")
    print(missing_param_res)
    assert missing_param_res.get("status") == "error"
```
