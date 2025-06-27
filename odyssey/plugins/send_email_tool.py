"""
SendEmailTool for the Odyssey agent.
Allows sending emails via a configured SMTP server.
Requires SMTP server details to be configured in AppSettings/environment variables.
"""
import smtplib
import logging
import os # Added import
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

from odyssey.agent.tool_manager import ToolInterface
# Assuming AppSettings is available for type hinting if passed via DI
# from odyssey.agent.main import AppSettings # For type hinting settings

logger = logging.getLogger("odyssey.plugins.send_email_tool")

class SendEmailTool(ToolInterface):
    """
    A tool to send emails using a pre-configured SMTP server.
    Requires SMTP settings (host, port, user, password, sender email) to be
    provided via AppSettings (typically loaded from environment variables).
    """
    name: str = "send_email_tool"
    description: str = "Sends an email to a specified recipient with a given subject and body using a pre-configured SMTP server."

    def __init__(self, settings: Optional[Any] = None): # settings can be AppSettings
        """
        Initializes the SendEmailTool.

        Args:
            settings: Optional. An AppSettings instance containing SMTP configuration.
                      Expected attributes: smtp_host, smtp_port, smtp_user,
                      smtp_password, smtp_use_tls, smtp_sender_email.
        """
        super().__init__()
        self.smtp_settings = None
        self.stub_mode = True

        if settings and all(hasattr(settings, attr) for attr in [
            "smtp_host", "smtp_port", "smtp_user",
            "smtp_password", "smtp_use_tls", "smtp_sender_email"
        ]):
            self.smtp_settings = {
                "host": settings.smtp_host,
                "port": settings.smtp_port,
                "user": settings.smtp_user,
                "password": settings.smtp_password, # This will be None if not set in .env
                "use_tls": settings.smtp_use_tls,
                "sender_email": settings.smtp_sender_email,
            }
            # Essential settings for real email sending
            if self.smtp_settings["host"] and self.smtp_settings["sender_email"]:
                # User/Pass might be optional for some SMTP setups, but generally needed.
                # For this tool, we'll consider it non-stub if host and sender are present.
                # Actual sending will fail later if auth is needed & not provided.
                self.stub_mode = False
                logger.info(f"[{self.name}] Initialized with SMTP settings. Sender: {self.smtp_settings['sender_email']}, Host: {self.smtp_settings['host']}:{self.smtp_settings['port']}")
            else:
                logger.warning(f"[{self.name}] Essential SMTP settings (host, sender_email) are missing. Operating in STUB mode.")
                self.stub_mode = True
        else:
            logger.warning(f"[{self.name}] SMTP settings not provided or incomplete in AppSettings. Operating in STUB mode.")
            self.stub_mode = True

    def execute(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Sends an email.

        Args:
            to (str): The recipient's email address.
            subject (str): The subject of the email.
            body (str): The plain text body of the email.

        Returns:
            Dict[str, Any]: Confirmation message on success or an error dictionary.
        """
        logger.info(f"[{self.name}] Attempting to send email. To: '{to}', Subject: '{subject}', Body snippet: '{body[:50]}...'")

        if self.stub_mode or not self.smtp_settings:
            log_msg = f"[{self.name} STUB] Email details: TO='{to}', SUBJECT='{subject}', BODY='{body[:100]}...'. (SMTP not fully configured)"
            logger.info(log_msg)
            return {"result": "Email logged instead of sent (STUB MODE - SMTP not fully configured).", "status": "success_stub_mode"}

        if not all([self.smtp_settings.get(key) for key in ["host", "sender_email"]]):
             err_msg = "SMTP host or sender email not configured. Cannot send email."
             logger.error(f"[{self.name}] {err_msg}")
             return {"error": err_msg, "status": "error"}


        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.smtp_settings["sender_email"]
        msg['To'] = to

        try:
            # Mask password in logs if it exists (it might be None)
            smtp_user_for_log = self.smtp_settings.get("user", "N/A")
            logger.debug(f"[{self.name}] Connecting to SMTP server: {self.smtp_settings['host']}:{self.smtp_settings['port']} as user {smtp_user_for_log}")

            # Choose between SMTP_SSL (port 465 typically) or SMTP with STARTTLS (port 587 typically)
            if self.smtp_settings.get("port") == 465: # Common SSL port
                 server = smtplib.SMTP_SSL(self.smtp_settings["host"], self.smtp_settings["port"])
            else:
                server = smtplib.SMTP(self.smtp_settings["host"], self.smtp_settings["port"])
                if self.smtp_settings.get("use_tls", True): # Default to TLS if port is not 465
                    server.starttls()

            # Login if username and password are provided
            if self.smtp_settings.get("user") and self.smtp_settings.get("password"):
                server.login(self.smtp_settings["user"], self.smtp_settings["password"])

            server.sendmail(self.smtp_settings["sender_email"], [to], msg.as_string())
            server.quit()

            success_msg = f"Email sent successfully to '{to}' with subject '{subject}'."
            logger.info(f"[{self.name}] {success_msg}")
            return {"result": success_msg, "status": "success"}

        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"SMTP authentication error: {e}. Check credentials or app password settings."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except smtplib.SMTPConnectError as e:
            err_msg = f"SMTP connection error: {e}. Check SMTP host/port."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except smtplib.SMTPSenderRefused as e:
            err_msg = f"SMTP sender refused: {e}. Check sender email address configuration."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except Exception as e:
            err_msg = f"Failed to send email: {str(e)}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "The recipient's email address."
                    },
                    "subject": {
                        "type": "string",
                        "description": "The subject line of the email."
                    },
                    "body": {
                        "type": "string",
                        "description": "The plain text body content of the email."
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')

    # Mock AppSettings for local testing
    class MockAppSettings:
        # To test live sending, fill these from your actual .env or directly
        smtp_host = os.environ.get("TEST_SMTP_HOST") # e.g., "smtp.gmail.com"
        smtp_port = int(os.environ.get("TEST_SMTP_PORT", 587))
        smtp_user = os.environ.get("TEST_SMTP_USER")   # Your email
        smtp_password = os.environ.get("TEST_SMTP_PASSWORD") # Your app password for Gmail, or regular password
        smtp_use_tls = os.environ.get("TEST_SMTP_USE_TLS", "true").lower() == "true"
        smtp_sender_email = os.environ.get("TEST_SMTP_SENDER_EMAIL") # Your email

    mock_settings = MockAppSettings()

    # If TEST_SMTP_HOST is not set, it will run in stub mode.
    if not mock_settings.smtp_host:
        print("WARNING: TEST_SMTP_HOST environment variable not set. Email tool will run in STUB mode for this test.")
        print("To test live email sending, set TEST_SMTP_HOST, TEST_SMTP_PORT, TEST_SMTP_USER, TEST_SMTP_PASSWORD, TEST_SMTP_SENDER_EMAIL.")
        # Force stub mode for the test if essential settings are missing for live send
        # Creating a settings object that will definitely trigger stub mode
        class StubSettings:
            smtp_host = None
            smtp_port = 0
            smtp_user = None
            smtp_password = None
            smtp_use_tls = False
            smtp_sender_email = None
        mock_settings_for_stub = StubSettings()
        tool = SendEmailTool(settings=mock_settings_for_stub)

    else:
        tool = SendEmailTool(settings=mock_settings)

    print("\nSchema:", tool.get_schema())
    print(f"Tool operating in stub mode: {tool.stub_mode}")

    print("\n--- Test Cases ---")

    recipient_email = os.environ.get("TEST_RECIPIENT_EMAIL", "test@example.com") # For live test
    if tool.stub_mode and recipient_email == "test@example.com":
        print("INFO: Using default 'test@example.com' for stub mode recipient.")

    print(f"1. Send an email to '{recipient_email}':")
    res1 = tool.execute(
        to=recipient_email,
        subject="Odyssey Agent Test Email",
        body="Hello from the SendEmailTool in Odyssey!\n\nThis is a test message."
    )
    print(res1)

    print("\n2. Attempt to send email with missing 'to' (should be caught by API schema if called via API):")
    # Direct execute call will show tool's internal handling or raise TypeError
    try:
        res2 = tool.execute(subject="Test Subject Missing To", body="Test body") # type: ignore
        print(res2) # Should ideally not reach here if execute raises TypeError
    except TypeError as te:
        print(f"Caught TypeError (expected for missing required arg): {te}")
        # In API context, FastAPI/Pydantic would return 422 before tool execution.
