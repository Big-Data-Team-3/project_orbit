#!/usr/bin/env python3
"""
Forbes AI50 Chunking Script

Chunks text into smaller chunks of a specified size.
"""
from typing import List
import logging
import dotenv
import os
dotenv.load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")    
logger = logging.getLogger(__name__)


class Chunker:
    def __init__(self, chunk_size: int = 1000):
        self.chunk_size = chunk_size

    def chunk_text(self, text: str) -> List[str]:
        return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size)]


