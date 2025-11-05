# region: imports
import os
from typing import List
from services.chunker import Chunker
from services.embeddings import Embeddings, PineconeStorage
import time
from pathlib import Path
# endregion: imports

# region: functions
def get_list_of_text_files(directory: str) -> List[str]:
    """
    Recursively find all .txt files in company-specific folders under initial_pull directories.
    Structure: data/raw/{company_name}/initial_pull/*.txt
    """
    text_files = []
    for root, dirs, files in os.walk(directory):
        # Only look in initial_pull directories
        if os.path.basename(root) == 'initial_pull':
            for file in files:
                if file.endswith('.txt'):
                    text_files.append(os.path.join(root, file))
    return text_files

# endregion: functions

# region: main
if __name__ == "__main__":
    print("-"*80)
    print("Starting chunking process...")
    directory = os.path.join(Path(__file__).parent.parent, "data", "raw")
    print(f"Directory: {directory}")
    text_files = get_list_of_text_files(directory=directory)
    print(f"Found {len(text_files)} text files")
    chunker = Chunker()
    embeddings = Embeddings()
    pinecone_storage = PineconeStorage()
    start_time = time.time()
    for text_file in text_files:
        print(f"Processing {text_file}...")
        text = open(text_file, "r").read()
        chunks = chunker.chunk_text(text)
        for chunk in chunks:
            embedding = embeddings.embed_text(chunk)
            # get company name from text file path
            company_name = text_file.split("/")[-3]
            # get filename from text file path
            filename = text_file.split("/")[-1]
            # join strings of company name and filename to get source path
            source_path = f"{company_name}/{filename}"
            pinecone_storage.store_embedding(chunk, embedding, source_path=source_path)
    print(f"Total time: {time.time() - start_time:.2f} seconds")
    print("✅ Chunking process completed successfully")
    print("-"*80)
# endregion: main