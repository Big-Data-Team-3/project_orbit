import os
import dotenv
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
from typing import List, Dict
from pinecone import Pinecone, ServerlessSpec
import hashlib
import time
import random
dotenv.load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
# text-embedding-3-small produces 1536 dimensions by default
# But can be reduced. Check your existing index dimension.
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

client = OpenAI(api_key=OPENAI_API_KEY)

class Embeddings:
    def __init__(self, max_retries: int = 5, base_delay: float = 0.2, max_delay: float = 30.0):
        self.client = client
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def embed_text(self, text: str) -> List[float]:
        """
        Embed text with exponential backoff retry logic.
        
        Args:
            text: The text to embed
            
        Returns:
            List[float]: The embedding vector (dimension matches EMBEDDING_DIMENSION)
            
        Raises:
            Exception: If all retries are exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                # If dimension is specified and different from model default, use dimensions parameter
                embedding_params = {
                    "input": text,
                    "model": EMBEDDING_MODEL
                }
                
                # text-embedding-3-small default is 1536, but we can reduce it
                if EMBEDDING_DIMENSION != 1536:
                    embedding_params["dimensions"] = EMBEDDING_DIMENSION
                
                response = self.client.embeddings.create(**embedding_params)
                return response.data[0].embedding
                
            except (RateLimitError, APIError, APIConnectionError, APITimeoutError) as e:
                last_exception = e
                
                # Don't retry on the last attempt
                if attempt == self.max_retries - 1:
                    raise
                
                # Calculate exponential backoff with jitter
                delay = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay
                )
                
                print(f"API error (attempt {attempt + 1}/{self.max_retries}): {type(e).__name__}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
                
            except Exception as e:
                # For unexpected errors, don't retry
                raise
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception

class PineconeStorage:

    def __init__(self):
        self.check_environment()
        self.client = Pinecone(api_key=PINECONE_API_KEY)
        self.index = self.initialize_index()
    

    def check_environment(self):
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY is not set")
        if not PINECONE_INDEX:
            raise ValueError("PINECONE_INDEX is not set")
        
        return True
    
    def initialize_index(self):
        # Check if index exists by listing all indexes
        existing_indexes = [idx.name for idx in self.client.list_indexes()]
        
        if PINECONE_INDEX not in existing_indexes:
            print(f"Index {PINECONE_INDEX} not found. Creating...")
            self.client.create_index(
                name=PINECONE_INDEX,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            print(f"Index {PINECONE_INDEX} created")
        else:
            print(f"Index {PINECONE_INDEX} already exists")
        
        self.index = self.client.Index(PINECONE_INDEX)
        return self.index
    def store_embedding(self, text: str, embedding: List[float], id: str = None, source_path: str = None):
        """
        Store an embedding in Pinecone.
        
        Args:
            text: The text content (used to generate ID if not provided)
            embedding: The embedding vector
            id: Optional custom ID. If not provided, generates a hash from the text.
        """
        if id is None:
            # Generate a unique ID from the text using hash
            id = hashlib.md5(text.encode()).hexdigest()
        
        self.index.upsert(vectors=[{
            "id": id,
            "values": embedding,
            "metadata": {
                "text": text,
                "source_path": source_path
            }
        }])

    def retrieve_embedding(self, id: str) -> List[float]:
        return self.index.fetch(ids=[id]).vectors[0].values
    
    def query(self, embedding: List[float], top_k: int = 10, filter_dict: dict = None) -> List[Dict]:
        """
        Query Pinecone index for similar vectors.
        
        Args:
            embedding: The query embedding vector
            top_k: Number of results to return
            filter_dict: Optional metadata filter
            
        Returns:
            List of dictionaries with 'text', 'source_path', and 'score' keys
        """
        query_params = {
            "vector": embedding,
            "top_k": top_k,
            "include_metadata": True
        }
        
        if filter_dict is not None:
            query_params["filter"] = filter_dict
        
        query_response = self.index.query(**query_params)
        
        results = []
        for match in query_response.matches:
            results.append({
                "text": match.metadata.get("text", ""),
                "source_path": match.metadata.get("source_path", ""),
                "score": match.score
            })
        
        return results
    