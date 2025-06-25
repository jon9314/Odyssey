"""
FetchUrlTool for the Odyssey agent.
Fetches content from a given URL.
"""
import requests
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from odyssey.agent.tool_manager import ToolInterface
# from odyssey.agent.main import AppSettings # For type hinting settings, if passed

logger = logging.getLogger("odyssey.plugins.fetch_url_tool")

class FetchUrlTool(ToolInterface):
    """
    A tool to fetch the content of a given URL.
    It validates the URL, handles potential network errors, and can limit
    the amount of content returned.
    """
    name: str = "fetch_url_tool"
    description: str = "Fetches the HTML/text content of a given URL. Supports limiting the number of bytes returned."

    def __init__(self, settings: Optional[Any] = None): # settings can be AppSettings
        """
        Initializes the FetchUrlTool.

        Args:
            settings: Optional. AppSettings instance. Can be used for global request timeout,
                      though this tool also has a per-call timeout.
        """
        super().__init__()
        self.global_request_timeout = 30 # Default global timeout if not from settings
        if settings and hasattr(settings, 'ollama_request_timeout'): # Reusing for general http timeout
             self.global_request_timeout = settings.ollama_request_timeout
        logger.info(f"[{self.name}] Initialized. Global request timeout (fallback): {self.global_request_timeout}s.")


    def _is_valid_url(self, url: str) -> bool:
        """Checks if the URL is valid and uses http or https scheme."""
        try:
            result = urlparse(url)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except ValueError:
            return False

    def execute(self, url: str, max_bytes: Optional[int] = 8192, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetches content from the specified URL.

        Args:
            url (str): The URL to fetch content from. Must be http or https.
            max_bytes (Optional[int]): Maximum number of bytes of content to return.
                                       Defaults to 8192. If 0 or None, attempts to fetch all.
            timeout (Optional[int]): Specific timeout for this request in seconds.
                                     Defaults to global_request_timeout.

        Returns:
            Dict[str, Any]: A dictionary with "result" (fetched content as string)
                            and "status": "success", or "error" message and "status": "error".
        """
        effective_timeout = timeout if timeout is not None and timeout > 0 else self.global_request_timeout
        logger.info(f"[{self.name}] Attempting to fetch URL: '{url}', max_bytes: {max_bytes}, timeout: {effective_timeout}s")

        if not self._is_valid_url(url):
            err_msg = f"Invalid URL: '{url}'. Must be a valid HTTP/HTTPS URL."
            logger.warning(f"[{self.name}] {err_msg}")
            return {"error": err_msg, "status": "error"}

        try:
            headers = {
                'User-Agent': 'OdysseyAgent/0.1 (+http://example.com/odyssey)' # Basic User-Agent
            }
            # Use stream=True to handle max_bytes efficiently
            with requests.get(url, headers=headers, timeout=effective_timeout, stream=True, allow_redirects=True) as response:
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                content_type = response.headers.get('content-type', '').lower()
                if not ('text/' in content_type or 'application/json' in content_type or 'application/xml' in content_type or 'application/javascript' in content_type):
                    # Heuristic to avoid downloading large binary files by default if not text-like
                    # This can be refined. For now, we primarily want text.
                    logger.warning(f"[{self.name}] URL '{url}' returned non-text-like content-type: '{content_type}'. Fetching may be partial or fail encoding.")

                content = ""
                bytes_read = 0
                # Read in chunks to respect max_bytes
                for chunk in response.iter_content(chunk_size=1024): # Read 1KB at a time
                    if max_bytes and max_bytes > 0 and (bytes_read + len(chunk)) > max_bytes:
                        remaining_bytes = max_bytes - bytes_read
                        try:
                            content += chunk[:remaining_bytes].decode(response.encoding or 'utf-8', errors='replace')
                        except UnicodeDecodeError: # If even partial chunk fails
                             content += chunk[:remaining_bytes].decode('latin-1', errors='replace') # Fallback
                        bytes_read += remaining_bytes
                        logger.info(f"[{self.name}] Content from '{url}' truncated to {max_bytes} bytes.")
                        break
                    try:
                        content += chunk.decode(response.encoding or 'utf-8', errors='replace')
                    except UnicodeDecodeError:
                         content += chunk.decode('latin-1', errors='replace') # Fallback encoding
                    bytes_read += len(chunk)
                    if max_bytes and max_bytes > 0 and bytes_read >= max_bytes: # Should be caught by inner if, but safety.
                        logger.info(f"[{self.name}] Content from '{url}' reached max_bytes limit of {max_bytes}.")
                        break

                if not max_bytes or max_bytes <= 0: # If no limit, content is already full
                     logger.info(f"[{self.name}] Fetched {len(content.encode('utf-8'))} bytes (unlimited) from '{url}'.")


            logger.info(f"[{self.name}] Successfully fetched content from '{url}'. Length: {len(content)} chars.")
            return {"result": content, "status": "success"}

        except requests.exceptions.Timeout:
            err_msg = f"Timeout fetching URL '{url}' after {effective_timeout}s."
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except requests.exceptions.HTTPError as e:
            err_msg = f"HTTP error fetching URL '{url}': {e.response.status_code} {e.response.reason}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except requests.exceptions.RequestException as e:
            err_msg = f"Error fetching URL '{url}': {e}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}
        except Exception as e:
            err_msg = f"An unexpected error occurred while fetching URL '{url}': {str(e)}"
            logger.error(f"[{self.name}] {err_msg}", exc_info=True)
            return {"error": err_msg, "status": "error"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The HTTP or HTTPS URL to fetch content from."
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Optional. Maximum number of bytes of the response content to return. Defaults to 8192. Set to 0 or negative for no limit (fetches entire content, use with caution for large files).",
                        "default": 8192
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Optional. Specific timeout for this request in seconds. Defaults to a global setting (currently {self.global_request_timeout}s).",
                        "default": self.global_request_timeout # Show default in schema
                    }
                },
                "required": ["url"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')
    tool = FetchUrlTool() # Uses default timeout

    print("Schema:", tool.get_schema())

    print("\n--- Test Cases ---")
    test_url_success = "https://jsonplaceholder.typicode.com/todos/1" # Simple JSON API
    test_url_large_page = "https://www.google.com" # A larger HTML page
    test_url_nonexistent = "http://thishostshouldnotexist123abc.com"
    test_url_invalid_scheme = "ftp://example.com/somefile.txt"
    test_url_404 = "http://example.com/nonexistentpage"


    print(f"\n1. Fetch small JSON content from '{test_url_success}':")
    res1 = tool.execute(url=test_url_success)
    print(res1)
    if res1.get("status") == "success": print(f"  Content snippet: {res1.get('result', '')[:100]}...")

    print(f"\n2. Fetch from '{test_url_large_page}' with max_bytes=500:")
    res2 = tool.execute(url=test_url_large_page, max_bytes=500)
    print(res2)
    if res2.get("status") == "success": print(f"  Content length: {len(res2.get('result',''))} (should be around 500 or less)")

    print(f"\n3. Fetch from '{test_url_large_page}' with no byte limit (max_bytes=0):")
    res3 = tool.execute(url=test_url_large_page, max_bytes=0) # Test no limit
    print(f"  Status: {res3.get('status')}")
    if res3.get("status") == "success": print(f"  Content length: {len(res3.get('result',''))} (full page, could be large)")


    print(f"\n4. Attempt to fetch non-existent domain '{test_url_nonexistent}':")
    res4 = tool.execute(url=test_url_nonexistent, timeout=5) # Short timeout for this test
    print(res4)
    assert res4.get("status") == "error"

    print(f"\n5. Attempt to fetch URL with invalid scheme '{test_url_invalid_scheme}':")
    res5 = tool.execute(url=test_url_invalid_scheme)
    print(res5)
    assert res5.get("status") == "error"

    print(f"\n6. Attempt to fetch a 404 page '{test_url_404}':")
    res6 = tool.execute(url=test_url_404)
    print(res6)
    assert res6.get("status") == "error" # Should be HTTPError

    # Test with a binary file URL (image) - expecting non-text warning and partial binary data or encoding errors
    # test_url_image = "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
    # print(f"\n7. Fetch an image URL '{test_url_image}' (expecting non-text handling):")
    # res7 = tool.execute(url=test_url_image, max_bytes=100) # Small max_bytes
    # print(res7)
    # # The result might be garbled if it tries to decode binary as utf-8/latin-1.
    # # This test is more about observing the warning and behavior.
```
