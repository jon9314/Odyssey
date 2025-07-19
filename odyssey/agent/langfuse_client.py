"""
Wrapper for the Langfuse Python SDK to provide a centralized client
for observability and tracing within the Odyssey agent.
"""
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime

try:
    import langfuse
    from langfuse.model import CreateTrace, CreateGeneration, CreateEvent, CreateScore, UpdateGeneration
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Define dummy classes if langfuse is not available, so type hints and calls don't break.
    class CreateTrace: pass
    class CreateGeneration: pass
    class CreateEvent: pass
    class CreateScore: pass
    class UpdateGeneration: pass
    logging.warning("Langfuse library not found. LangfuseClientWrapper will operate in no-op mode.")

logger = logging.getLogger(__name__)

class LangfuseClientWrapper:
    def __init__(self,
                 public_key: Optional[str] = None,
                 secret_key: Optional[str] = None,
                 host: Optional[str] = None,
                 release: Optional[str] = None, # Optional: for versioning traces
                 debug: bool = False):
        """
        Initializes the LangfuseClientWrapper.

        :param public_key: Langfuse public key.
        :param secret_key: Langfuse secret key.
        :param host: Langfuse host URL (e.g., "https://cloud.langfuse.com" or "http://localhost:3000").
        :param release: Optional release version for associating traces.
        :param debug: Enable Langfuse debug mode.
        """
        self.active = False
        self.client = None
        self.release = release

        if not LANGFUSE_AVAILABLE:
            logger.warning("Langfuse SDK not installed. Observability features will be disabled.")
            return

        if public_key and secret_key and host:
            try:
                self.client = langfuse.Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=host,
                    release=self.release,
                    debug=debug
                )
                self.active = True
                logger.info(f"Langfuse client initialized successfully. Host: {host}, Release: {self.release or 'N/A'}")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse client: {e}", exc_info=True)
                self.client = None # Ensure client is None on failure
        else:
            logger.info("Langfuse not configured (public_key, secret_key, or host missing). Observability features disabled.")

    def get_trace(self,
                  name: Optional[str] = None,
                  user_id: Optional[str] = None,
                  session_id: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None,
                  tags: Optional[List[str]] = None,
                  trace_id: Optional[str] = None # Existing trace ID to continue or create if not exists
                  ) -> Optional[Any]: # langfuse.Trace causes circular import if langfuse is mocked
        """
        Creates or gets a Langfuse trace.
        If trace_id is provided and exists, it might be used to link (depends on SDK behavior for get_trace).
        Langfuse SDK's `trace()` is a context manager or can create a trace object directly.
        This method provides a way to get a trace object.

        :return: A Langfuse Trace object or None if Langfuse is not active.
        """
        if not self.active or not self.client:
            return None
        try:
            # If trace_id is given, it implies we want to ensure this trace exists or continue it.
            # The SDK's `trace()` method creates a new trace if one isn't active in context.
            # For creating a specific trace or continuing one, we use CreateTrace.
            trace_params = {"name": name}
            if trace_id: trace_params["id"] = trace_id
            if user_id: trace_params["user_id"] = user_id
            if session_id: trace_params["session_id"] = session_id
            if metadata: trace_params["metadata"] = metadata
            if tags: trace_params["tags"] = tags
            if self.release: trace_params["release"] = self.release

            # The SDK's Trace object is usually obtained via `langfuse.trace()`
            # This method is more for creating a trace explicitly.
            # If you need a context manager, use `with self.client.trace(...)` elsewhere.
            # This method returns a handle to a trace.
            trace = self.client.trace(**{k:v for k,v in trace_params.items() if v is not None})
            logger.debug(f"Langfuse trace obtained/created: ID={trace.id}, Name={name or 'Default'}")
            return trace
        except Exception as e:
            logger.error(f"Failed to create/get Langfuse trace: {e}", exc_info=True)
            return None

    def log_generation(self,
                       trace_id: Any, # Can be a Trace object or string ID
                       name: str,
                       prompt: Any,
                       response: Any,
                       model: str,
                       usage: Optional[Dict[str, int]] = None, # e.g., {"promptTokens": N, "completionTokens": M}
                       metadata: Optional[Dict[str, Any]] = None,
                       start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None,
                       level: str = "DEFAULT", # Langfuse LogLevel: DEBUG, INFO, WARNING, ERROR, DEFAULT
                       status_message: Optional[str] = None
                       ) -> Optional[Any]: # langfuse.Generation
        """
        Logs an LLM generation event to Langfuse. Can be part of an existing trace.

        :param trace_id: The Langfuse Trace object or string ID to associate with this generation.
        :param name: Name for this generation step (e.g., "ollama-completion", "summary-generation").
        :param prompt: The prompt sent to the LLM (can be string, list of messages, etc.).
        :param response: The response received from the LLM.
        :param model: The name of the model used.
        :param usage: Optional dictionary with token usage information.
        :param metadata: Optional dictionary for additional metadata.
        :param start_time: Optional start time of the generation.
        :param end_time: Optional end time of the generation.
        :param level: Langfuse LogLevel (DEBUG, INFO, WARNING, ERROR, DEFAULT).
        :param status_message: Optional status message for the generation (e.g., error details).
        :return: Langfuse Generation object or None.
        """
        if not self.active or not self.client:
            return None

        actual_trace = trace_id
        if isinstance(trace_id, str) and hasattr(self.client, 'trace'): # Check if client has trace method
             # This is a simplified way to get a handle if only ID is passed.
             # Ideally, the Trace object itself is passed.
             actual_trace = self.client.trace(id=trace_id, name=name or "Generation Trace")


        if not hasattr(actual_trace, 'generation'):
            logger.error("Invalid trace object provided for logging generation. Cannot find 'generation' method.")
            # Fallback: Create a new trace for this generation if trace_id was just a string
            if isinstance(trace_id, str):
                logger.warning(f"No valid Trace object for trace_id '{trace_id}'. Creating new trace for this generation.")
                actual_trace = self.client.trace(name=name or "Generation Trace", id=trace_id if trace_id else None)
            else: # trace_id was None or some other invalid type
                 logger.warning(f"No valid Trace object or ID. Creating new trace for this generation.")
                 actual_trace = self.client.trace(name=name or "Generation Trace")


        try:
            generation_params = {
                "name": name,
                "prompt": prompt,
                "completion": response, # Langfuse uses 'completion' for the response
                "model": model,
                "usage": usage,
                "metadata": metadata,
                "start_time": start_time,
                "end_time": end_time,
                "level": level,
                "status_message": status_message
            }
            # Filter out None values to use Langfuse SDK defaults
            generation_params = {k: v for k, v in generation_params.items() if v is not None}

            gen = actual_trace.generation(**generation_params)
            logger.debug(f"Langfuse generation logged: Name='{name}', Model='{model}' to trace ID '{actual_trace.id}'")
            return gen
        except Exception as e:
            logger.error(f"Failed to log Langfuse generation: {e}", exc_info=True)
            return None

    def log_event(self,
                  trace_id: Any, # Can be a Trace object or string ID
                  name: str,
                  metadata: Optional[Dict[str, Any]] = None,
                  input: Optional[Any] = None,
                  output: Optional[Any] = None,
                  level: str = "DEFAULT", # Langfuse LogLevel
                  start_time: Optional[datetime] = None,
                  status_message: Optional[str] = None
                  ) -> Optional[Any]: # langfuse.Event
        """
        Logs a generic event to Langfuse, associated with a trace.
        :return: Langfuse Event object or None.
        """
        if not self.active or not self.client:
            return None

        actual_trace = trace_id
        if isinstance(trace_id, str) and hasattr(self.client, 'trace'):
             actual_trace = self.client.trace(id=trace_id, name=name or "Event Trace")

        if not hasattr(actual_trace, 'event'):
            logger.error("Invalid trace object provided for logging event. Cannot find 'event' method.")
            if isinstance(trace_id, str):
                logger.warning(f"No valid Trace object for trace_id '{trace_id}'. Creating new trace for this event.")
                actual_trace = self.client.trace(name=name or "Event Trace", id=trace_id if trace_id else None)
            else:
                 logger.warning(f"No valid Trace object or ID. Creating new trace for this event.")
                 actual_trace = self.client.trace(name=name or "Event Trace")

        try:
            event_params = {
                "name": name,
                "metadata": metadata,
                "input": input,
                "output": output,
                "level": level,
                "start_time": start_time,
                "status_message": status_message,
            }
            event_params = {k: v for k, v in event_params.items() if v is not None}

            evt = actual_trace.event(**event_params)
            logger.debug(f"Langfuse event logged: Name='{name}' to trace ID '{actual_trace.id}'")
            return evt
        except Exception as e:
            logger.error(f"Failed to log Langfuse event: {e}", exc_info=True)
            return None

    def score_trace(self,
                    trace_id: str,
                    name: str,
                    value: float,
                    comment: Optional[str] = None
                    ) -> Optional[Any]: # langfuse.Score
        """
        Adds a score to a Langfuse trace.
        :return: Langfuse Score object or None.
        """
        if not self.active or not self.client:
            return None
        try:
            score_params = {"trace_id": trace_id, "name": name, "value": value}
            if comment: score_params["comment"] = comment

            score_obj = self.client.score(**score_params)
            logger.info(f"Langfuse score added: TraceID='{trace_id}', Name='{name}', Value='{value}'")
            return score_obj
        except Exception as e:
            logger.error(f"Failed to add Langfuse score: {e}", exc_info=True)
            return None

    def shutdown(self):
        """
        Shuts down the Langfuse client, ensuring all buffered data is sent.
        """
        if self.active and self.client:
            try:
                logger.info("Shutting down Langfuse client...")
                self.client.flush() # Flush before shutdown
                self.client.shutdown()
                logger.info("Langfuse client shut down successfully.")
            except Exception as e:
                logger.error(f"Error during Langfuse client shutdown: {e}", exc_info=True)
            finally:
                self.active = False
                self.client = None

# Example usage (for direct testing of this module)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Replace with your actual keys and host for testing
    # These would typically come from environment variables
    TEST_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY_TEST")
    TEST_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY_TEST")
    TEST_HOST = os.environ.get("LANGFUSE_HOST_TEST", "http://localhost:3000") # Default to local if not set

    if not (TEST_PUBLIC_KEY and TEST_SECRET_KEY):
        logger.warning("LANGFUSE_PUBLIC_KEY_TEST and LANGFUSE_SECRET_KEY_TEST environment variables not set. Skipping live Langfuse test.")
    else:
        logger.info(f"Attempting to connect to Langfuse at {TEST_HOST} for example usage.")
        lf_wrapper = LangfuseClientWrapper(
            public_key=TEST_PUBLIC_KEY,
            secret_key=TEST_SECRET_KEY,
            host=TEST_HOST,
            release="odyssey-dev-0.1",
            debug=True
        )

        if lf_wrapper.active:
            # 1. Create a trace
            main_trace = lf_wrapper.get_trace(name="ExampleMainTrace", user_id="user-123", metadata={"environment": "test"})

            if main_trace:
                logger.info(f"Created main trace with ID: {main_trace.id}")

                # 2. Log a generation within this trace
                generation_start_time = datetime.now()
                # Simulate some delay
                import time
                time.sleep(0.1)
                generation_end_time = datetime.now()

                lf_wrapper.log_generation(
                    trace_id=main_trace, # Pass the Trace object
                    name="example-llm-call",
                    prompt={"user_query": "What is Langfuse?"},
                    response={"answer": "Langfuse is an open source LLM engineering platform."},
                    model="gpt-3.5-turbo-test",
                    usage={"promptTokens": 10, "completionTokens": 20},
                    metadata={"complexity": "simple"},
                    start_time=generation_start_time,
                    end_time=generation_end_time
                )

                # 3. Log an event within this trace
                lf_wrapper.log_event(
                    trace_id=main_trace.id, # Can also pass trace ID string
                    name="data-processing-step",
                    input={"data_size": 1024},
                    output={"status": "completed", "items_processed": 500},
                    metadata={"module": "parser"},
                    level="INFO"
                )

                # 4. Score the trace
                lf_wrapper.score_trace(
                    trace_id=main_trace.id,
                    name="user-satisfaction",
                    value=0.9,
                    comment="User reported high satisfaction with the outcome."
                )

                # Example of logging a generation without an explicit parent trace (will create one)
                lf_wrapper.log_generation(
                    trace_id=None, # No explicit parent trace
                    name="standalone-generation",
                    prompt="Another prompt",
                    response="Another response",
                    model="phi3-test"
                )

            else:
                logger.error("Failed to create main_trace for example.")

            # Shutdown Langfuse client
            lf_wrapper.shutdown()
        else:
            logger.warning("Langfuse client not active. Example operations were skipped.")

    logger.info("LangfuseClientWrapper example finished.")
