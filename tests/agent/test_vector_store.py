import unittest
import os
import shutil
import tempfile
from typing import List, Dict, Any, Optional

# Mock chromadb and embedding_functions if not installed or for isolated testing
# This allows tests to run even if the full environment isn't set up.
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    # Create dummy classes/mocks if chromadb is not available
    class MockChromaCollection:
        def __init__(self, name="mock_collection"):
            self.name = name
            self._data = {} # id: {text, metadata}
            self._embeddings = {} # id: [float]
            self.ef = lambda texts: [[0.1 * len(t)] * 10 for t in texts] # Dummy embedding function

        def add(self, documents: List[str], metadatas: List[Dict], ids: List[str]):
            for i, doc_id in enumerate(ids):
                self._data[doc_id] = {"text": documents[i], "metadata": metadatas[i]}
                # Simulate embedding generation if it were external
                # self._embeddings[doc_id] = self.ef([documents[i]])[0]

        def query(self, query_texts: List[str], n_results: int, where: Optional[Dict] = None, include: Optional[List[str]] = None):
            # Simplified mock query: returns a few stored items if they match metadata or all if no filter
            # Does not simulate actual similarity.
            all_ids = list(self._data.keys())
            results_ids = []
            results_docs = []
            results_metas = []
            results_dists = []

            for doc_id in all_ids:
                if len(results_ids) >= n_results:
                    break
                match = True
                if where:
                    for k, v in where.items():
                        if self._data[doc_id]["metadata"].get(k) != v:
                            match = False
                            break
                if match:
                    results_ids.append(doc_id)
                    results_docs.append(self._data[doc_id]["text"])
                    results_metas.append(self._data[doc_id]["metadata"])
                    results_dists.append(0.5) # Dummy distance

            return {"ids": [results_ids], "documents": [results_docs], "metadatas": [results_metas], "distances": [results_dists]}

        def delete(self, ids: Optional[List[str]] = None, where: Optional[Dict] = None):
            if ids:
                for doc_id in ids:
                    if doc_id in self._data: del self._data[doc_id]
                    if doc_id in self._embeddings: del self._embeddings[doc_id]
            elif where:
                to_delete = []
                for doc_id, data in self._data.items():
                    match = True
                    for k, v in where.items():
                        if data["metadata"].get(k) != v:
                            match = False; break
                    if match: to_delete.append(doc_id)
                for doc_id in to_delete:
                    if doc_id in self._data: del self._data[doc_id]
                    if doc_id in self._embeddings: del self._embeddings[doc_id]


        def count(self):
            return len(self._data)

    class MockChromaClient:
        def __init__(self, path=None): self.path = path
        def get_or_create_collection(self, name, embedding_function):
            return MockChromaCollection(name=name)

    chromadb = MagicMock() # Overall module mock
    chromadb.PersistentClient = MockChromaClient
    chromadb.Client = MockChromaClient # For in-memory

    # Mock for embedding_functions.SentenceTransformerEmbeddingFunction
    class MockSentenceTransformerEmbeddingFunction:
        def __init__(self, model_name): self.model_name = model_name
        def __call__(self, texts: List[str]) -> List[List[float]]:
            # Return dummy embeddings of a fixed dimension, e.g., 10
            return [[0.1 * len(text)] * 10 for text in texts]

    if embedding_functions is None: # If chromadb.utils failed to import
        embedding_functions = MagicMock()
    embedding_functions.SentenceTransformerEmbeddingFunction = MockSentenceTransformerEmbeddingFunction


from odyssey.agent.vector_store import ChromaVectorStore, VectorStoreInterface


@unittest.skipIf(not CHROMA_AVAILABLE, "ChromaDB library not installed, skipping ChromaVectorStore tests.")
class TestChromaVectorStore(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for ChromaDB persistence for each test
        self.test_dir = tempfile.mkdtemp(prefix="test_chroma_")
        self.collection_name = "test_collection"
        # Use a known small SentenceTransformer model for faster tests if real Chroma is used
        self.embedding_model = "all-MiniLM-L6-v2"

        self.vector_store: VectorStoreInterface = ChromaVectorStore(
            collection_name=self.collection_name,
            persist_directory=self.test_dir,
            embedding_model_name=self.embedding_model
        )

    def tearDown(self):
        # Clean up the temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_add_and_query_documents(self):
        docs = [
            {"text": "The cat sat on the mat.", "metadata": {"source": "nursery_rhyme"}, "id": "doc1"},
            {"text": "A dog barked in the park.", "metadata": {"source": "observation"}, "id": "doc2"},
        ]
        added_ids = self.vector_store.add_documents(docs)
        self.assertEqual(len(added_ids), 2)
        self.assertIn("doc1", added_ids)
        self.assertEqual(self.vector_store.get_collection_count(), 2)

        results = self.vector_store.query_similar_documents("feline seating", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "doc1")
        self.assertIn("text", results[0])
        self.assertIn("metadata", results[0])
        self.assertIn("distance", results[0])
        self.assertEqual(results[0]["metadata"]["source"], "nursery_rhyme")

    def test_add_documents_autogenerate_ids(self):
        docs = [
            {"text": "Document without explicit ID.", "metadata": {"source": "auto_id_test"}},
        ]
        added_ids = self.vector_store.add_documents(docs)
        self.assertEqual(len(added_ids), 1)
        self.assertIsNotNone(added_ids[0])
        self.assertEqual(self.vector_store.get_collection_count(), 1)

        results = self.vector_store.query_similar_documents("ID-less document", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], added_ids[0])


    def test_query_with_metadata_filter(self):
        docs = [
            {"text": "Event A happened on Monday.", "metadata": {"day": "Monday", "type": "event"}, "id": "event_mon"},
            {"text": "Event B happened on Tuesday.", "metadata": {"day": "Tuesday", "type": "event"}, "id": "event_tue"},
            {"text": "Meeting notes from Monday.", "metadata": {"day": "Monday", "type": "notes"}, "id": "notes_mon"},
        ]
        self.vector_store.add_documents(docs)
        self.assertEqual(self.vector_store.get_collection_count(), 3)

        # Query for "event" but only on "Monday"
        results = self.vector_store.query_similar_documents("occurrence", top_k=2, metadata_filter={"day": "Monday"})
        self.assertTrue(len(results) >= 1)
        found_ids = [r["id"] for r in results]
        self.assertIn("event_mon", found_ids)
        self.assertNotIn("event_tue", found_ids)

        # Query for type "notes"
        results_notes = self.vector_store.query_similar_documents("summary", top_k=1, metadata_filter={"type": "notes"})
        self.assertEqual(len(results_notes), 1)
        self.assertEqual(results_notes[0]["id"], "notes_mon")

    def test_delete_documents_by_id(self):
        docs = [
            {"text": "To be deleted.", "metadata": {"status": "temp"}, "id": "delete_me"},
            {"text": "To be kept.", "metadata": {"status": "permanent"}, "id": "keep_me"},
        ]
        self.vector_store.add_documents(docs)
        self.assertEqual(self.vector_store.get_collection_count(), 2)

        self.vector_store.delete_documents(ids=["delete_me"])
        self.assertEqual(self.vector_store.get_collection_count(), 1)

        results = self.vector_store.query_similar_documents("deleted", top_k=2)
        found_ids = [r["id"] for r in results]
        self.assertNotIn("delete_me", found_ids)
        self.assertIn("keep_me", found_ids)

    def test_delete_documents_by_metadata_filter(self):
        docs = [
            {"text": "Item A, category X.", "metadata": {"category": "X"}, "id": "itemA"},
            {"text": "Item B, category Y.", "metadata": {"category": "Y"}, "id": "itemB"},
            {"text": "Item C, category X.", "metadata": {"category": "X"}, "id": "itemC"},
        ]
        self.vector_store.add_documents(docs)
        self.assertEqual(self.vector_store.get_collection_count(), 3)

        self.vector_store.delete_documents(metadata_filter={"category": "X"})
        self.assertEqual(self.vector_store.get_collection_count(), 1) # Only itemB should remain

        results = self.vector_store.query_similar_documents("item", top_k=3)
        found_ids = [r["id"] for r in results]
        self.assertIn("itemB", found_ids)
        self.assertNotIn("itemA", found_ids)
        self.assertNotIn("itemC", found_ids)

    def test_get_collection_count(self):
        self.assertEqual(self.vector_store.get_collection_count(), 0)
        self.vector_store.add_documents([{"text": "Doc 1", "id": "d1"}])
        self.assertEqual(self.vector_store.get_collection_count(), 1)
        self.vector_store.add_documents([{"text": "Doc 2", "id": "d2"}, {"text": "Doc 3", "id": "d3"}])
        self.assertEqual(self.vector_store.get_collection_count(), 3)
        self.vector_store.delete_documents(ids=["d1"])
        self.assertEqual(self.vector_store.get_collection_count(), 2)

# A separate test class for when ChromaDB is NOT available, to test mock fallbacks if desired.
# For now, the main tests are skipped if Chroma is not available.
class TestVectorStoreInterfaceMock(unittest.TestCase):
    @unittest.skipIf(CHROMA_AVAILABLE, "ChromaDB IS available, skipping mock interface tests.")
    def test_mock_chroma_vector_store_instantiation(self):
        # This test runs if CHROMA_AVAILABLE is False.
        # It verifies that our mock classes are used by ChromaVectorStore.

        # To truly test this, we'd need to ensure ChromaVectorStore uses the *mocked* chromadb
        # and embedding_functions. This might require patching them at the module level
        # where ChromaVectorStore imports them.

        # For this example, we'll just confirm it doesn't raise an immediate error
        # due to unmocked parts, assuming the mock setup at the top of the file is effective.
        try:
            # The key is that `odyssey.agent.vector_store.chromadb` and
            # `odyssey.agent.vector_store.embedding_functions` are patched.
            # We need to patch them where they are looked up by ChromaVectorStore.
            with patch('odyssey.agent.vector_store.chromadb', new=chromadb), \
                 patch('odyssey.agent.vector_store.embedding_functions', new=embedding_functions):

                # embedding_functions.SentenceTransformerEmbeddingFunction should now be our mock
                self.assertIs(embedding_functions.SentenceTransformerEmbeddingFunction, MockSentenceTransformerEmbeddingFunction)

                store = ChromaVectorStore(collection_name="mock_test", persist_directory=None)
                self.assertIsNotNone(store)
                self.assertIsInstance(store.client, MockChromaClient)
                self.assertIsInstance(store.collection, MockChromaCollection)
                self.assertEqual(store.get_collection_count(), 0)

                store.add_documents([{"text": "hello", "id": "m1", "metadata": {}}])
                self.assertEqual(store.get_collection_count(), 1)
                results = store.query_similar_documents("hi")
                self.assertEqual(len(results), 1) # Mock query behavior

        except ImportError as e:
            self.fail(f"ChromaVectorStore raised ImportError even with mocks: {e}")
        except Exception as e:
            self.fail(f"ChromaVectorStore raised an unexpected exception with mocks: {e}")


if __name__ == '__main__':
    unittest.main()
