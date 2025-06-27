"""
SearchWebTool (Stub) for the Odyssey agent.
Simulates web search functionality.
"""
import logging
from typing import Dict, Any, Optional
import json # For pretty printing dummy data in logs if needed

from odyssey.agent.tool_manager import ToolInterface
# from odyssey.agent.main import AppSettings # For type hinting settings, if passed

logger = logging.getLogger("odyssey.plugins.search_web_tool")

class SearchWebTool(ToolInterface):
    """
    A STUB tool to simulate web search functionality.
    In a real implementation, this would connect to a search API (e.g., Google, Bing, DuckDuckGo, Serper).
    For now, it returns dummy data.
    """
    name: str = "search_web_tool"
    description: str = "Performs a web search for a given query and returns a list of top results (titles and URLs). Currently a STUB."

    def __init__(self, settings: Optional[Any] = None): # settings can be AppSettings
        """
        Initializes the SearchWebTool.

        Args:
            settings: Optional. AppSettings instance. Could be used for API keys in a real implementation.
        """
        super().__init__()
        # In a real tool, API keys or clients would be initialized here from settings.
        # Example: self.search_api_key = settings.SEARCH_API_KEY if settings else os.environ.get('SEARCH_API_KEY')
        self.is_stub = True # Clearly indicate it's a stub
        logger.info(f"[{self.name}] Initialized. Operating in STUB mode.")

    def execute(self, query: str, num_results: Optional[int] = 3) -> Dict[str, Any]:
        """
        Simulates performing a web search and returns dummy results.

        Args:
            query (str): The search query.
            num_results (Optional[int]): The desired number of search results. Defaults to 3.

        Returns:
            Dict[str, Any]: A dictionary with "result" (a list of dummy search result dicts)
                            and "status": "success_stub_mode", or an error dictionary if input is invalid.
        """
        logger.info(f"[{self.name} STUB] Attempting web search. Query: '{query}', Num Results: {num_results}")

        if not query or not isinstance(query, str) or not query.strip():
            err_msg = "Search query cannot be empty."
            logger.warning(f"[{self.name} STUB] {err_msg}")
            return {"error": err_msg, "status": "error"}

        if not isinstance(num_results, int) or num_results <= 0:
            num_results = 3 # Default to 3 if invalid
            logger.warning(f"[{self.name} STUB] Invalid 'num_results' ({num_results}), defaulting to 3.")

        # Generate dummy search results
        dummy_results = []
        for i in range(1, num_results + 1):
            dummy_results.append({
                "title": f"Dummy Search Result {i} for '{query}'",
                "url": f"http://example.com/search?q={query.replace(' ', '+')}&result={i}",
                "snippet": f"This is a dummy snippet for search result {i} related to '{query}'. It simulates found text."
            })

        logger.info(f"[{self.name} STUB] Returning {len(dummy_results)} dummy search results for query '{query}'.")
        return {"result": dummy_results, "status": "success_stub_mode"}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string."
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Optional. The desired number of search results to return.",
                        "default": 3,
                        "minimum": 1
                    }
                },
                "required": ["query"]
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(module)s - %(levelname)s - %(message)s')
    tool = SearchWebTool()

    print("Schema:", tool.get_schema())

    print("\n--- Test Cases ---")

    print("\n1. Search with default number of results:")
    res1 = tool.execute(query="What is Odyssey Agent?")
    print(json.dumps(res1, indent=2))
    if res1.get("status") == "success_stub_mode" and isinstance(res1.get("result"), list):
        assert len(res1["result"]) == 3

    print("\n2. Search with specified number of results (e.g., 2):")
    res2 = tool.execute(query="Latest AI news", num_results=2)
    print(json.dumps(res2, indent=2))
    if res2.get("status") == "success_stub_mode" and isinstance(res2.get("result"), list):
        assert len(res2["result"]) == 2

    print("\n3. Search with empty query (should return error):")
    res3 = tool.execute(query=" ")
    print(json.dumps(res3, indent=2))
    assert res3.get("status") == "error"

    print("\n4. Search with invalid num_results (e.g., 0):")
    res4 = tool.execute(query="Test query", num_results=0) # Should default to 3
    print(json.dumps(res4, indent=2))
    if res4.get("status") == "success_stub_mode" and isinstance(res4.get("result"), list):
        assert len(res4["result"]) == 3

    print("\n5. Search with invalid num_results (e.g., negative):")
    res5 = tool.execute(query="Another test", num_results=-2) # Should default to 3
    print(json.dumps(res5, indent=2))
    if res5.get("status") == "success_stub_mode" and isinstance(res5.get("result"), list):
        assert len(res5["result"]) == 3
