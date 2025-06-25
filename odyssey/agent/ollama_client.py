"""
Client for interacting with Ollama an LLM serving platform.
Supports connecting to local and remote Ollama instances, selecting models,
and sending prompts for text generation.
"""
import requests
import json
import logging
from typing import Optional, List, Dict, Any, Generator, Tuple

# Use a more specific logger name for this client
logger = logging.getLogger("odyssey.agent.ollama_client")

# Forward reference for LangfuseClientWrapper type hint
LangfuseClientWrapper = "LangfuseClientWrapper" # Works if LangfuseClientWrapper is in a separate file
# If in the same file or complex, from typing import ForwardRef; LangfuseClientWrapper = ForwardRef('LangfuseClientWrapper')
# However, direct import is better if possible. Let's assume it will be importable from .langfuse_client
from .langfuse_client import LangfuseClientWrapper as ActualLangfuseClientWrapper # For actual use
from datetime import datetime # For Langfuse timestamps


class OllamaClient:
    """
    A client for interacting with Ollama services.
    It can manage connections to a local and an optional remote Ollama instance,
    route requests based on model availability and safety preferences, and
    handle API communication for text generation.
    """
    def __init__(self,
                 local_url: str = "http://localhost:11434",
                 remote_url: Optional[str] = None,
                 default_model: str = "phi3",
                 request_timeout: int = 120,
                 langfuse_wrapper: Optional[ActualLangfuseClientWrapper] = None): # Added langfuse_wrapper
        """
        Initializes the OllamaClient.

        Args:
            local_url: URL for the local Ollama instance.
            remote_url: URL for a remote Ollama instance (e.g., on a LAN GPU server).
            default_model: Default model to use if 'auto' is specified in 'ask'.
            request_timeout: Timeout in seconds for requests to the Ollama API.
            langfuse_wrapper: Optional instance of LangfuseClientWrapper for observability.
        """
        if not local_url:
            raise ValueError("local_url for OllamaClient cannot be None or empty.")

        self.local_url = local_url.rstrip('/')
        self.remote_url = remote_url.rstrip('/') if remote_url else None
        self.default_model = default_model
        self.request_timeout = request_timeout
        self.langfuse_wrapper = langfuse_wrapper # Store the wrapper

        self.available_local_models: List[Dict[str, Any]] = self._get_available_models(self.local_url, "local")
        self.available_remote_models: List[Dict[str, Any]] = self._get_available_models(self.remote_url, "remote") if self.remote_url else []

        logger.info(f"OllamaClient initialized. Local URL: {self.local_url}, Remote URL: {self.remote_url or 'Not configured'}")
        logger.info(f"Available local models: {[m.get('name', 'N/A') for m in self.available_local_models]}")
        if self.remote_url:
            logger.info(f"Available remote models: {[m.get('name', 'N/A') for m in self.available_remote_models]}")

    def _get_available_models(self, base_url: Optional[str], instance_name: str) -> List[Dict[str, Any]]:
        """
        Helper to fetch available models from an Ollama instance.

        Args:
            base_url: The base URL of the Ollama instance.
            instance_name: Name of the instance ('local' or 'remote') for logging.

        Returns:
            A list of model dictionaries, or an empty list if fetching fails.
        """
        if not base_url:
            return []
        try:
            api_url = f"{base_url}/api/tags"
            logger.debug(f"Fetching available models from {instance_name} instance: {api_url}")
            response = requests.get(api_url, timeout=self.request_timeout / 4) # Shorter timeout for tags
            response.raise_for_status()
            models_data = response.json()
            if "models" not in models_data or not isinstance(models_data["models"], list):
                logger.warning(f"Unexpected format for models from {instance_name} ({base_url}). Response: {models_data}")
                return []
            return models_data["models"]
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not fetch models from {instance_name} instance ({base_url}): {e}")
            return []
        except json.JSONDecodeError:
            logger.warning(f"Could not decode JSON response for models from {instance_name} instance ({base_url}).")
            return []

    def _choose_instance_and_model(self, requested_model: str, prefer_safe_ यानी_local: bool) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Chooses which Ollama instance (local or remote) and model to use.

        Args:
            requested_model: The model name (e.g., 'llama3', 'phi3:latest', 'auto').
            prefer_safe_ यानी_local: If True, prefers the local instance for "safe" requests.

        Returns:
            A tuple (instance_url, actual_model_name_with_tag, instance_type_name)
            or (None, None, None) if no suitable model/instance found.
        """
        effective_model_name = requested_model
        if requested_model == 'auto':
            effective_model_name = self.default_model
            logger.info(f"Model 'auto' selected, using default model: '{self.default_model}' for selection logic.")

        targets = []
        # Order of preference based on 'prefer_safe_ यानी_local'
        if prefer_safe_ यानी_local:
            if self.local_url and self.available_local_models:
                targets.append({"url": self.local_url, "models": self.available_local_models, "name": "local"})
            if self.remote_url and self.available_remote_models:
                targets.append({"url": self.remote_url, "models": self.available_remote_models, "name": "remote"})
        else: # Prefer remote for non-safe (potentially complex/large) requests
            if self.remote_url and self.available_remote_models:
                targets.append({"url": self.remote_url, "models": self.available_remote_models, "name": "remote"})
            if self.local_url and self.available_local_models:
                targets.append({"url": self.local_url, "models": self.available_local_models, "name": "local"})

        # If only one type of instance is configured, it becomes the only target
        if not self.remote_url and (self.local_url and self.available_local_models):
            targets = [{"url": self.local_url, "models": self.available_local_models, "name": "local"}]
        elif not self.local_url and (self.remote_url and self.available_remote_models): # Should not happen given constructor logic
             targets = [{"url": self.remote_url, "models": self.available_remote_models, "name": "remote"}]


        if not targets:
            logger.error("No Ollama instances available or no models found on configured instances.")
            return None, None, None

        # Attempt to find the model based on preference order
        # 1. Check for exact model name (e.g., "llama3:8b-instruct-fp16")
        for target in targets:
            for model_info in target["models"]:
                if model_info.get("name") == effective_model_name:
                    logger.info(f"Found exact model '{effective_model_name}' on preferred {target['name']} instance ({target['url']}).")
                    return target["url"], effective_model_name, target["name"]

        # 2. If exact name not found, check for base model name (e.g., "llama3" from "llama3:latest")
        base_requested_model = effective_model_name.split(':')[0]
        for target in targets:
            for model_info in target["models"]:
                if model_info.get("name", "").split(':')[0] == base_requested_model:
                    actual_model_found = model_info["name"]
                    logger.info(f"Found model matching base '{base_requested_model}' (actual: '{actual_model_found}') on preferred {target['name']} instance ({target['url']}). Using this one.")
                    return target["url"], actual_model_found, target["name"]

        # 3. If 'auto' was requested and specific default model wasn't found, pick first available model on the most preferred instance
        if requested_model == 'auto' and targets[0]["models"]: # targets[0] is the most preferred based on safe flag
            first_available_on_preferred = targets[0]["models"][0].get("name")
            if first_available_on_preferred:
                logger.info(f"Model 'auto': Default model '{self.default_model}' not found as specified. Using first available model '{first_available_on_preferred}' on the most preferred instance ({targets[0]['name']}: {targets[0]['url']}).")
                return targets[0]["url"], first_available_on_preferred, targets[0]["name"]

        logger.warning(f"Model '{requested_model}' (effective: '{effective_model_name}') not found on any configured and available Ollama instance following preference rules.")
        return None, None, None

    def ask(self,
            prompt: str,
            model: str = 'auto',
            safe: bool = True, # prefer_safe_yani_local
            stream: bool = False,
            options: Optional[Dict[str, Any]] = None,
            system_prompt: Optional[str] = None,
            # Langfuse related parameters
            parent_trace_obj: Optional[Any] = None,
            trace_name: Optional[str] = None,
            trace_metadata: Optional[Dict[str, Any]] = None,
            trace_tags: Optional[List[str]] = None
            ) -> Tuple[Optional[str], Optional[str], Any]:
        """
        Sends a prompt to an Ollama API and gets a response. Integrates Langfuse tracing.
        Args:
            prompt: The user's prompt.
            model: Model name to use. 'auto' tries the default_model.
            safe: If True, prefers local instance.
            stream: Whether to stream the response.
            options: Additional Ollama options.
            system_prompt: Optional system message.
            parent_trace_obj: Optional parent Langfuse Trace object to link this generation.
            trace_name: Name for this Langfuse generation or new trace. If None, a default is used.
            trace_metadata: Additional metadata for Langfuse.
            trace_tags: Tags for Langfuse.
        Returns:
            A tuple: (instance_type_used, model_used, response_content_or_generator)
        """
        start_time = datetime.utcnow()

        # Prepare combined metadata for Langfuse
        # This metadata will be associated with the Langfuse generation or trace.
        _trace_metadata = {
            "component": "OllamaClient", "method": "ask", "requested_model": model,
            "safe_param": safe, "is_stream_request": stream,
        }
        if options: _trace_metadata["ollama_options"] = options
        if system_prompt: _trace_metadata["system_prompt_used"] = bool(system_prompt)
        if trace_metadata: _trace_metadata.update(trace_metadata) # Merge caller's metadata

        # Determine prompt structure for Langfuse logging (handles system prompts)
        langfuse_prompt_input = prompt
        if system_prompt:
            langfuse_prompt_input = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]

        instance_url, actual_model, instance_type = self._choose_instance_and_model(model, prefer_safe_yani_local=safe)

        # Update metadata with chosen instance/model
        _trace_metadata["instance_type_chosen"] = instance_type
        _trace_metadata["actual_model_chosen"] = actual_model

        response_for_langfuse = None # Actual text or "[Streaming Response]"
        error_for_langfuse = None    # Error message string for Langfuse status_message
        usage_for_langfuse = None    # For prompt_tokens, completion_tokens
        final_response_tuple: Tuple[Optional[str], Optional[str], Any] # What this 'ask' method returns

        if not instance_url or not actual_model:
            error_msg = f"Error: Could not find suitable Ollama instance/model (model='{model}', safe='{safe}')."
            logger.error(error_msg)
            error_for_langfuse = error_msg
            final_response_tuple = None, None, error_msg
        else:
            api_endpoint = f"{instance_url}/api/generate"
            payload = {"model": actual_model, "prompt": prompt, "stream": stream}
            if options: payload["options"] = options
            if system_prompt: payload["system"] = system_prompt

            log_prompt_snippet = prompt[:100] + "..." if len(prompt) > 100 else prompt
            logger.info(f"Sending prompt to Ollama '{instance_type}' ({actual_model}). Snippet: '{log_prompt_snippet}'")

            try:
                http_response = requests.post(
                    api_endpoint, data=json.dumps(payload), headers={"Content-Type": "application/json"},
                    stream=stream, timeout=self.request_timeout
                )
                http_response.raise_for_status()

                if stream:
                    logger.debug(f"Streaming response from {instance_type} ({actual_model}).")
                    response_for_langfuse = "[Streaming Response]" # Langfuse doesn't ingest generators directly for 'completion'
                    final_response_tuple = instance_type, actual_model, self._stream_response_generator(http_response)
                else: # Non-streaming
                    response_data = http_response.json()
                    full_response = response_data.get("response", "")
                    response_for_langfuse = full_response
                    # Extract usage if available from Ollama's response
                    prompt_tokens = response_data.get("prompt_eval_count")
                    completion_tokens = response_data.get("eval_count") # 'eval_count' is often the completion tokens
                    if prompt_tokens is not None and completion_tokens is not None:
                        usage_for_langfuse = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                    else: # Fallback if specific keys aren't there, Ollama's output varies
                        usage_for_langfuse = {"input_tokens": response_data.get("prompt_eval_count", 0),
                                              "output_tokens": response_data.get("eval_count", 0)}


                    logger.info(f"Received non-streamed response from {instance_type} ({actual_model}). Length: {len(full_response)}. Snippet: {full_response[:100] + '...' if len(full_response) > 100 else full_response}")
                    final_response_tuple = instance_type, actual_model, full_response

            except requests.exceptions.Timeout:
                error_msg = f"Timeout connecting to Ollama ({instance_type} at {api_endpoint}) after {self.request_timeout}s."
                logger.error(error_msg)
                error_for_langfuse = error_msg
                final_response_tuple = instance_type, actual_model, error_msg
            except requests.exceptions.RequestException as e_req:
                error_msg = f"Request error connecting to Ollama ({instance_type} at {api_endpoint}): {e_req}"
                logger.error(error_msg)
                error_for_langfuse = error_msg
                final_response_tuple = instance_type, actual_model, error_msg
            except json.JSONDecodeError:
                error_msg = f"Could not decode JSON response from Ollama ({instance_type} at {api_endpoint})."
                logger.error(error_msg)
                error_for_langfuse = error_msg
                final_response_tuple = instance_type, actual_model, error_msg
            except Exception as e_unexpected:
                error_msg = f"An unexpected error occurred ({instance_type} at {api_endpoint}): {e_unexpected}"
                logger.error(error_msg, exc_info=True)
                error_for_langfuse = error_msg
                final_response_tuple = instance_type, actual_model, error_msg

        end_time = datetime.utcnow()

        if self.langfuse_wrapper and self.langfuse_wrapper.active:
            effective_trace_name = trace_name or "OllamaClient.ask.DefaultGeneration"

            # If a parent trace object is provided, log this generation as its child
            if parent_trace_obj and hasattr(parent_trace_obj, 'generation'):
                parent_trace_obj.generation(
                    name=effective_trace_name,
                    prompt=langfuse_prompt_input,
                    completion=response_for_langfuse if not error_for_langfuse else None,
                    model=actual_model or model, # Best guess
                    usage=usage_for_langfuse,
                    metadata=_trace_metadata,
                    start_time=start_time,
                    end_time=end_time,
                    level="ERROR" if error_for_langfuse else "DEFAULT",
                    status_message=error_for_langfuse
                )
            else: # No parent_trace_obj, create a new trace for this generation
                # Use trace_name for the trace itself, and a generic name for the generation step
                trace = self.langfuse_wrapper.client.trace(
                    name=trace_name or "OllamaClient.ask.StandaloneTrace",
                    metadata=_trace_metadata, # Attach all metadata to the trace
                    tags=trace_tags or ["llm_call", "ollama_ask"]
                )
                trace.generation(
                    name="generation", # Name of the step within this trace
                    prompt=langfuse_prompt_input,
                    completion=response_for_langfuse if not error_for_langfuse else None,
                    model=actual_model or model,
                    usage=usage_for_langfuse,
                    # metadata is already on the trace, can add more specific to generation if needed
                    start_time=start_time,
                    end_time=end_time,
                    level="ERROR" if error_for_langfuse else "DEFAULT",
                    status_message=error_for_langfuse
                )
                if error_for_langfuse: # Update the trace status if an error occurred
                    trace.update(status_message=f"Failed: {error_for_langfuse[:200]}", level="ERROR")

        return final_response_tuple

    def _stream_response_generator(self, response: requests.Response) -> Generator[str, None, None]:
        """
        Private helper to generate chunks from a streaming HTTP response.
        """
        try:
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        if "response" in chunk:
                            yield chunk["response"]
                        if chunk.get("done"):
                            logger.info("Stream ended by Ollama 'done' signal.")
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode JSON stream chunk: {line}")
                        continue
        finally:
            response.close() # Ensure connection is closed

    def generate_embeddings(self,
                            text: str,
                            model: str = 'auto',
                            prefer_safe_yani_local: bool = True,
                            # Langfuse related parameters
                            parent_trace_obj: Optional[Any] = None,
                            trace_name: Optional[str] = None,
                            trace_metadata: Optional[Dict[str, Any]] = None,
                            trace_tags: Optional[List[str]] = None
                           ) -> Optional[List[float]]:
        """
        Generates embeddings for a given text using a specified Ollama model. Integrates Langfuse tracing.

        Args:
            text: The text to generate embeddings for.
            model: Model name to use. 'auto' tries the default_model or a known embedding model.
            prefer_safe_yani_local: If True, prefers local instance. If False, prefers remote.

        Returns:
            A list of floats representing the embedding, or None if an error occurs.
        """
        # Note: Ollama's /api/embeddings usually uses the model's primary modality.
        # Some models might be better suited for embeddings than others.
        # If 'auto' is used, we might want to prioritize models known for good embeddings if default_model isn't one.
        # For now, it uses the same model selection logic as ask().
        start_time = datetime.utcnow()

        _trace_metadata = {
            "component": "OllamaClient", "method": "generate_embeddings", "requested_model": model,
            "prefer_safe_yani_local": prefer_safe_yani_local, "text_length": len(text)
        }
        if trace_metadata: _trace_metadata.update(trace_metadata)

        instance_url, actual_model, instance_type = self._choose_instance_and_model(
            model, prefer_safe_yani_local=prefer_safe_yani_local
        )
        _trace_metadata["instance_type_chosen"] = instance_type
        _trace_metadata["actual_model_chosen"] = actual_model

        embedding_result_for_langfuse = None
        error_for_langfuse = None
        final_embedding_output: Optional[List[float]] = None


        if not instance_url or not actual_model:
            error_msg = f"Error: Could not find suitable Ollama instance/model for embedding (model='{model}', safe='{prefer_safe_yani_local}')."
            logger.error(error_msg)
            error_for_langfuse = error_msg
            final_embedding_output = None
        else:
            api_endpoint = f"{instance_url}/api/embeddings"
            payload = { "model": actual_model, "prompt": text }
            logger.info(f"Generating embeddings via Ollama '{instance_type}' ({actual_model}). Text snippet: '{text[:100]}...'")

            try:
                response = requests.post(
                api_endpoint,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=self.request_timeout
            )
            response.raise_for_status()
            response_data = response.json()
            embedding_data = response_data.get("embedding")

            if isinstance(embedding_data, list) and all(isinstance(x, (float, int)) for x in embedding_data):
                logger.info(f"Successfully generated embedding from {instance_type} ({actual_model}). Embedding dim: {len(embedding_data)}")
                final_embedding_output = [float(x) for x in embedding_data]
                embedding_result_for_langfuse = {"dimension": len(final_embedding_output), "first_3_values": final_embedding_output[:3]}
            else:
                error_msg = f"Unexpected embedding format from Ollama ({instance_type}, {actual_model}). Response: {response_data}"
                logger.error(error_msg)
                error_for_langfuse = error_msg
                final_embedding_output = None

        except requests.exceptions.Timeout:
            error_msg = f"Timeout for embeddings ({instance_type} at {api_endpoint}) after {self.request_timeout}s."
            logger.error(error_msg)
            error_for_langfuse = error_msg
            final_embedding_output = None
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error for embeddings ({instance_type} at {api_endpoint}): {e}"
            logger.error(error_msg)
            error_for_langfuse = error_msg
            final_embedding_output = None
        except json.JSONDecodeError:
            error_msg = f"Could not decode JSON for embeddings ({instance_type} at {api_endpoint})."
            logger.error(error_msg)
            error_for_langfuse = error_msg
            final_embedding_output = None
        except Exception as e:
            error_msg = f"Unexpected error generating embeddings ({instance_type} at {api_endpoint}): {e}"
            logger.error(error_msg, exc_info=True)
            error_for_langfuse = error_msg
            final_embedding_output = None

        end_time = datetime.utcnow()
        if self.langfuse_wrapper and self.langfuse_wrapper.active:
            effective_trace_name = trace_name or "OllamaClient.generate_embeddings.DefaultGeneration"
            effective_standalone_trace_name = trace_name or "OllamaClient.generate_embeddings.StandaloneTrace"

            # Langfuse SDK's `generation` typically takes `prompt` and `completion`.
            # For embeddings, we can use `input` for the text and `output` for the embedding (or its summary).
            # Or, log it as an "event" if "generation" feels semantically off.
            # Let's use "generation" but adapt fields. Input = text, Output = embedding summary/status.

            if parent_trace_obj and hasattr(parent_trace_obj, 'generation'):
                parent_trace_obj.generation(
                    name=effective_trace_name,
                    input=text[:1000], # Log a snippet of input text
                    output=embedding_result_for_langfuse if not error_for_langfuse else None,
                    model=actual_model or model,
                    metadata=_trace_metadata,
                    start_time=start_time,
                    end_time=end_time,
                    level="ERROR" if error_for_langfuse else "DEFAULT",
                    status_message=error_for_langfuse
                )
            else:
                new_trace = self.langfuse_wrapper.client.trace(
                    name=effective_standalone_trace_name,
                    metadata=_trace_metadata,
                    tags=trace_tags or ["embedding_generation", "ollama_embeddings"]
                )
                if new_trace:
                    new_trace.generation( # Using generation here to group model, input, output, metadata
                        name="embedding_step",
                        input=text[:1000], # Log a snippet
                        output=embedding_result_for_langfuse if not error_for_langfuse else None,
                        model=actual_model or model,
                        metadata={"is_embedding": True}, # Specific metadata for this step
                        start_time=start_time,
                        end_time=end_time,
                        level="ERROR" if error_for_langfuse else "DEFAULT",
                        status_message=error_for_langfuse
                    )
                    if error_for_langfuse:
                       new_trace.update(status_message=f"Embedding Failed: {error_for_langfuse[:200]}", level="ERROR")

        return final_embedding_output


if __name__ == '__main__':
    # Setup basic logging for the example
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Configuration for Example ---
    # Ensure you have an Ollama server running.
    # local_ollama_url = "http://localhost:11434" # Your local Ollama
    # remote_ollama_url = None # Example: "http://your-lan-gpu-server:11434"

    # For Dockerized setup from new docker-compose.yml, 'ollama-local' service:
    # This client, if run from the 'backend' container, would use:
    # local_ollama_url_in_docker = "http://ollama-local:11434"
    # If this script is run on the HOST, it uses localhost:11434 (if ollama-local port is mapped)

    # Assuming this __main__ block is run on the HOST machine where Docker is running
    # and ollama-local service has port 11434 mapped to host's 11434.

    # Example with only local Ollama
    client_local_only = OllamaClient(local_url="http://localhost:11434", default_model="phi3")

    # Example with local and a (mocked) remote - replace remote_url with a real one for actual testing
    # client_dual = OllamaClient(local_url="http://localhost:11434", remote_url="http://192.168.1.100:11434", default_model="phi3")

    # Using local_only client for tests.
    # Ensure you have 'phi3' model pulled: `ollama pull phi3`
    client_to_test = client_local_only

    if not client_to_test.available_local_models and (not client_to_test.remote_url or not client_to_test.available_remote_models) :
        logger.error("No Ollama models found. Make sure Ollama is running and you have pulled models (e.g., 'ollama pull phi3').")
        logger.error("If running Ollama in Docker (e.g. 'ollama-local' service), ensure it's up: 'docker ps'")
    else:
        logger.info("\n--- Test 1: Simple non-streaming call (safe=True, should prefer local) ---")
        # Model 'auto' will use default_model ('phi3') for selection logic.
        # `safe=True` prefers local.
        instance1, model_used1, response1 = client_to_test.ask("Briefly, what is Python?", model='auto', safe=True)
        logger.info(f"Test 1: Instance='{instance1}', Model='{model_used1}'. Response snippet: {str(response1)[:100]}...")
        if "Error:" in str(response1): logger.error(f"Test 1 failed: {response1}")


        logger.info("\n--- Test 2: Streaming call (safe=False, would prefer remote if configured & model available there) ---")
        # `safe=False` prefers remote. If remote is not configured or doesn't have phi3, it will fall back to local.
        instance2, model_used2, response_gen2 = client_to_test.ask("Tell me a short story about a robot.", model='phi3', safe=False, stream=True)
        logger.info(f"Test 2: Instance='{instance2}', Model='{model_used2}'. Streaming response:")
        if isinstance(response_gen2, str) and "Error:" in response_gen2: # Error occurred
            logger.error(f"Test 2 failed: {response_gen2}")
        elif response_gen2 is not None and not isinstance(response_gen2, str): # Is a generator
            try:
                full_streamed_response = "".join(chunk for chunk in response_gen2)
                logger.info(f"Full streamed response snippet: {full_streamed_response[:100]}...")
            except Exception as e:
                logger.error(f"Error consuming stream for Test 2: {e}")
        else:
            logger.warning(f"Test 2 did not return a valid generator or error string: {response_gen2}")


        logger.info("\n--- Test 3: System Prompt Example ---")
        instance3, model_used3, response3 = client_to_test.ask(
            "What is your favorite treasure?",
            model='phi3',
            system_prompt="You are a friendly pirate captain. Respond as such, matey!"
        )
        logger.info(f"Test 3: Instance='{instance3}', Model='{model_used3}'. Response snippet: {str(response3)[:100]}...")
        if "Error:" in str(response3): logger.error(f"Test 3 failed: {response3}")


        logger.info("\n--- Test 4: Requesting a non-existent model ---")
        instance4, model_used4, response4 = client_to_test.ask("This should fail gracefully.", model='nonexistentmodel123xyz')
        logger.info(f"Test 4: Instance='{instance4}', Model='{model_used4}'. Response: {response4}")
        if not ("Error:" in str(response4) and instance4 is None and model_used4 is None): # Expecting specific error tuple
             logger.error(f"Test 4 did not fail as expected or returned unexpected instance/model: {instance4}, {model_used4}")


        logger.info("\n--- Test 5: Using Ollama options (e.g., temperature) ---")
        instance5, model_used5, response5 = client_to_test.ask(
            "Write a very short, imaginative poem about a star.",
            model='phi3',
            options={"temperature": 0.95, "num_predict": 60} # Higher temp, limit response length
        )
        logger.info(f"Test 5: Instance='{instance5}', Model='{model_used5}'. Response snippet: {str(response5)[:100]}...")
        if "Error:" in str(response5): logger.error(f"Test 5 failed: {response5}")

        logger.info("\n--- Test 6: Generating embeddings ---")
        # Ensure the model used (e.g., phi3) supports embedding generation.
        # Some very small models might not, or might produce low-quality embeddings.
        # Ollama's default behavior for /api/embeddings is to use the specified model.
        text_to_embed = "This is a test sentence for generating embeddings."
        embedding = client_to_test.generate_embeddings(text_to_embed, model='phi3', prefer_safe_yani_local=True)

        if embedding:
            logger.info(f"Test 6: Embedding generated. Type: {type(embedding)}, Dim: {len(embedding)}, First 5 values: {embedding[:5]}")
        else:
            logger.error(f"Test 6: Embedding generation failed.")

    logger.info("OllamaClient example finished.")
