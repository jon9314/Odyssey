"""
Vector Store Interface and Implementations for semantic memory.
Allows for adding documents, generating embeddings, and querying for similar documents.
"""
import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

# Attempt to import chromadb and its components.
# If not installed, ChromaVectorStore will not be usable but interface can be defined.
try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None # Placeholder if not installed
    embedding_functions = None
    logging.warning("ChromaDB library not found. ChromaVectorStore will not be available.")


logger = logging.getLogger(__name__)

class VectorStoreInterface(ABC):
    """
    Abstract base class for a vector store.
    Defines the common interface for adding and querying documents based on semantic similarity.
    """

    @abstractmethod
    def add_documents(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Adds documents to the vector store.
        Each document is a dictionary, expected to have 'text', 'metadata', and optionally 'id'.
        If 'id' is not provided, it should be generated.

        :param documents: A list of document dictionaries.
                          Example: [{"text": "My document text", "metadata": {"source": "file.txt"}, "id": "doc1"}]
        :return: A list of IDs for the added documents.
        :raises: Exception if documents could not be added.
        """
        pass

    @abstractmethod
    def query_similar_documents(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries the vector store for documents similar to the query_text.

        :param query_text: The text to find similar documents for.
        :param top_k: The number of top similar documents to return.
        :param metadata_filter: Optional dictionary to filter results based on metadata.
                                Example: {"source": "file.txt"}
        :return: A list of result dictionaries, each containing 'text', 'metadata', 'id', and 'distance'.
                 Example: [{"text": "...", "metadata": {...}, "id": "doc1", "distance": 0.23}]
        """
        pass

    @abstractmethod
    def delete_documents(self, ids: Optional[List[str]] = None, metadata_filter: Optional[Dict[str, Any]] = None) -> None:
        """
        Deletes documents from the vector store based on IDs or a metadata filter.
        At least one of `ids` or `metadata_filter` must be provided.

        :param ids: A list of document IDs to delete.
        :param metadata_filter: A dictionary to filter documents for deletion.
        :raises: ValueError if both `ids` and `metadata_filter` are None.
                 Exception on deletion failure.
        """
        pass

    @abstractmethod
    def get_collection_count(self) -> int:
        """
        Returns the total number of items in the collection.
        """
        pass


class ChromaVectorStore(VectorStoreInterface):
    """
    A vector store implementation using ChromaDB.
    """
    def __init__(self,
                 collection_name: str = "odyssey_semantic_memory",
                 persist_directory: Optional[str] = "var/memory/vector_store/chroma",
                 embedding_model_name: str = 'all-MiniLM-L6-v2', # Default SentenceTransformer model
                 ollama_client = None, # Keep for future use if switching embedding func
                 ollama_embedding_model: Optional[str] = None # Model for Ollama embeddings
                ):
        """
        Initializes the ChromaVectorStore.

        :param collection_name: Name of the collection in ChromaDB.
        :param persist_directory: Directory to persist ChromaDB data. If None, uses in-memory.
        :param embedding_model_name: Name of the SentenceTransformer model to use for embeddings.
                                     This is used if ollama_client is not provided or fails.
        :param ollama_client: An optional instance of OllamaClient for generating embeddings.
        :param ollama_embedding_model: The specific model name to use with OllamaClient for embeddings.
        """
        if not chromadb:
            raise ImportError("ChromaDB library is not installed. Please install it to use ChromaVectorStore.")

        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_model_name = embedding_model_name

        # TODO: Decide on embedding function strategy.
        # Option 1: Use Chroma's built-in SentenceTransformerEmbeddingFunction (simpler for now).
        # Option 2: Create a custom embedding function wrapper around OllamaClient.generate_embeddings.
        #           This would allow using Ollama-hosted models for embeddings.
        # For now, using SentenceTransformer for robustness and ease of setup, as OllamaClient
        # might not be configured with a dedicated embedding model, or batching might be an issue.

        if embedding_functions:
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name
            )
            logger.info(f"ChromaVectorStore initialized with SentenceTransformer model: {self.embedding_model_name}")
        else:
            # This case should ideally be prevented by the ImportError check above,
            # but as a fallback if only `chromadb` was imported but not `chromadb.utils`.
            logger.error("ChromaDB embedding functions not available. Cannot initialize SentenceTransformerEmbeddingFunction.")
            raise ImportError("ChromaDB embedding functions not available.")

        if self.persist_directory:
            logger.info(f"ChromaDB will persist data to: {self.persist_directory}")
            self.client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            logger.info("ChromaDB will run in-memory (no persistence).")
            self.client = chromadb.Client()

        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function
                # metadata={"hnsw:space": "cosine"} # Example: configure index, default is l2
            )
            logger.info(f"ChromaDB collection '{self.collection_name}' loaded/created. Count: {self.collection.count()}")
        except Exception as e:
            logger.error(f"Failed to get or create ChromaDB collection '{self.collection_name}': {e}", exc_info=True)
            raise

    def add_documents(self, documents: List[Dict[str, Any]]) -> List[str]:
        texts_to_add = []
        metadatas_to_add = []
        ids_to_add = []

        for doc in documents:
            if not doc.get("text"):
                logger.warning(f"Document missing 'text' field, skipping: {doc.get('id', 'N/A')}")
                continue

            texts_to_add.append(doc["text"])
            metadatas_to_add.append(doc.get("metadata", {})) # Ensure metadata is at least an empty dict

            doc_id = doc.get("id") or str(uuid.uuid4())
            ids_to_add.append(doc_id)

        if not texts_to_add:
            logger.info("No valid documents provided to add.")
            return []

        try:
            logger.info(f"Adding {len(texts_to_add)} documents to Chroma collection '{self.collection_name}'. First ID: {ids_to_add[0] if ids_to_add else 'N/A'}")
            self.collection.add(
                documents=texts_to_add,
                metadatas=metadatas_to_add,
                ids=ids_to_add
            )
            logger.info(f"Successfully added {len(ids_to_add)} documents. New collection count: {self.collection.count()}")
            return ids_to_add
        except Exception as e:
            logger.error(f"Failed to add documents to Chroma collection '{self.collection_name}': {e}", exc_info=True)
            # Consider if partial adds need handling or if it's atomic. Chroma's add is generally atomic for the batch.
            raise

    def query_similar_documents(
        self,
        query_text: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if top_k <= 0:
            logger.warning("top_k must be positive. Returning empty list.")
            return []
        try:
            logger.debug(f"Querying Chroma collection '{self.collection_name}' for '{query_text[:100]}...', top_k={top_k}, filter={metadata_filter}")
            results = self.collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where=metadata_filter, # Chroma's `where` filter
                include=['metadatas', 'documents', 'distances', 'ids'] # Explicitly include ids
            )

            formatted_results = []
            # ChromaDB query results structure for a single query_text:
            # results = {
            # 'ids': [['id1', 'id2']],
            # 'distances': [[0.1, 0.2]],
            # 'metadatas': [[{'meta1': 'val1'}, {'meta2': 'val2'}]],
            # 'documents': [['doc text 1', 'doc text 2']]
            # }
            if results and results.get('ids') and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    formatted_results.append({
                        "id": results['ids'][0][i],
                        "text": results['documents'][0][i] if results['documents'] and results['documents'][0] else None,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else None,
                        "distance": results['distances'][0][i] if results['distances'] and results['distances'][0] else None,
                    })
            logger.debug(f"Query returned {len(formatted_results)} results.")
            return formatted_results
        except Exception as e:
            logger.error(f"Failed to query Chroma collection '{self.collection_name}': {e}", exc_info=True)
            return [] # Return empty list on error

    def delete_documents(self, ids: Optional[List[str]] = None, metadata_filter: Optional[Dict[str, Any]] = None) -> None:
        if not ids and not metadata_filter:
            raise ValueError("Either 'ids' or 'metadata_filter' must be provided for deletion.")

        try:
            log_msg = "Attempting to delete documents from Chroma collection"
            if ids: log_msg += f" by IDs (count: {len(ids)}, first ID: {ids[0] if ids else 'N/A'})"
            if metadata_filter: log_msg += f" by metadata filter: {metadata_filter}"
            logger.info(log_msg)

            self.collection.delete(ids=ids, where=metadata_filter)
            logger.info(f"Deletion operation completed. New collection count: {self.collection.count()}")
        except Exception as e:
            logger.error(f"Failed to delete documents from Chroma collection '{self.collection_name}': {e}", exc_info=True)
            raise

    def get_collection_count(self) -> int:
        try:
            count = self.collection.count()
            logger.debug(f"Collection '{self.collection_name}' count: {count}")
            return count
        except Exception as e:
            logger.error(f"Failed to get count for Chroma collection '{self.collection_name}': {e}", exc_info=True)
            return 0 # Or raise


# Example Usage (Conceptual - would run if this script is executed directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Running VectorStore example...")

    # Ensure persist directory exists for this example if used
    persist_dir_example = "var/memory/vector_store_example_chroma"
    if chromadb: # Only run example if chromadb is available
        import shutil
        if os.path.exists(persist_dir_example):
            logger.info(f"Removing existing example persist directory: {persist_dir_example}")
            shutil.rmtree(persist_dir_example)
        os.makedirs(persist_dir_example, exist_ok=True)

        try:
            # Using default SentenceTransformer model
            vector_db = ChromaVectorStore(collection_name="my_test_collection", persist_directory=persist_dir_example)

            logger.info(f"Initial collection count: {vector_db.get_collection_count()}")

            # Add documents
            docs_to_add = [
                {"text": "The quick brown fox jumps over the lazy dog.", "metadata": {"source": "common-phrases", "chapter": 1}, "id": "phrase1"},
                {"text": "Odyssey is an AI agent that can rewrite its own code.", "metadata": {"source": "project-readme", "version": "0.1"}}, # ID will be auto-generated
                {"text": "Large language models are transforming technology.", "metadata": {"source": "tech-news", "year": 2023}, "id": "news1"},
                {"text": "A lazy cat sleeps all day.", "metadata": {"source": "observations", "animal": "cat"}},
            ]
            added_ids = vector_db.add_documents(docs_to_add)
            logger.info(f"Added document IDs: {added_ids}")
            logger.info(f"Collection count after add: {vector_db.get_collection_count()}")

            # Query for similar documents
            query1 = "agile canine"
            results1 = vector_db.query_similar_documents(query1, top_k=2)
            logger.info(f"\nQuery: '{query1}'")
            for res in results1:
                logger.info(f"  ID: {res['id']}, Dist: {res['distance']:.4f}, Text: '{res['text']}', Meta: {res['metadata']}")

            query2 = "AI systems self-improvement"
            results2 = vector_db.query_similar_documents(query2, top_k=2, metadata_filter={"source": "project-readme"})
            logger.info(f"\nQuery: '{query2}' with filter {{'source': 'project-readme'}}")
            for res in results2:
                 logger.info(f"  ID: {res['id']}, Dist: {res['distance']:.4f}, Text: '{res['text']}', Meta: {res['metadata']}")

            # Delete a document
            if added_ids and len(added_ids) > 1: # Ensure there's something to delete
                id_to_delete = next((d.get("id") for d in docs_to_add if d.get("id") == "phrase1"), None) # Get ID of "phrase1"
                if id_to_delete:
                    logger.info(f"\nDeleting document with ID: {id_to_delete}")
                    vector_db.delete_documents(ids=[id_to_delete])
                    logger.info(f"Collection count after delete: {vector_db.get_collection_count()}")

                    results_after_delete = vector_db.query_similar_documents(query1, top_k=2)
                    logger.info(f"Query results for '{query1}' after deleting '{id_to_delete}':")
                    for res in results_after_delete:
                        logger.info(f"  ID: {res['id']}, Dist: {res['distance']:.4f}, Text: '{res['text']}', Meta: {res['metadata']}")

            # Test deleting with filter
            logger.info("\nDeleting documents with metadata filter {'animal': 'cat'}")
            vector_db.delete_documents(metadata_filter={"animal": "cat"})
            logger.info(f"Collection count after metadata filter delete: {vector_db.get_collection_count()}")


        except ImportError:
            logger.error("ChromaDB or SentenceTransformers not installed, skipping ChromaVectorStore example.")
        except Exception as e:
            logger.error(f"An error occurred during the ChromaVectorStore example: {e}", exc_info=True)
        finally:
            # Clean up example directory
            # if os.path.exists(persist_dir_example):
            #     logger.info(f"Cleaning up example persist directory: {persist_dir_example}")
            #     shutil.rmtree(persist_dir_example)
            pass # Keep for inspection for now
    else:
        logger.info("ChromaDB not detected, skipping ChromaVectorStore example run.")

    logger.info("VectorStore example finished.")
