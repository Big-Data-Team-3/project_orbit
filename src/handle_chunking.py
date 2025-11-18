# region: imports
import os
import json
from typing import List, Dict, Tuple
from services.chunker import Chunker
from services.embeddings import Embeddings, PineconeStorage
import time
from pathlib import Path
# endregion: imports

# region: functions
def get_list_of_text_files(directory: str) -> List[str]:
    """
    Recursively find all *_clean.txt files in comprehensive_extraction directories.
    Structure: data/raw/{company_name}/comprehensive_extraction/*_clean.txt
    """
    text_files = []
    for root, dirs, files in os.walk(directory):
        # Only look in comprehensive_extraction directories
        if os.path.basename(root) == 'comprehensive_extraction':
            for file in files:
                # Only process *_clean.txt files (cleaned text content)
                if file.endswith('_clean.txt'):
                    text_files.append(os.path.join(root, file))
    return sorted(text_files)

def extract_text_from_json(json_file: str) -> str:
    """
    Extract text content from a *_complete.json file.
    Tries multiple fields and structures to get meaningful text.
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        text_parts = []
        
        # Priority 1: Extract from text_content dict (most comprehensive)
        if 'text_content' in data and isinstance(data['text_content'], dict):
            tc = data['text_content']
            # Get full_text if available (best source - contains all text)
            if 'full_text' in tc and isinstance(tc['full_text'], str) and len(tc['full_text']) > 100:
                text_parts.append(tc['full_text'])
            # If no full_text, reconstruct from components
            elif 'paragraphs' in tc or 'headings' in tc:
                # Get all headings first (for structure)
                if 'headings' in tc and isinstance(tc['headings'], list):
                    for heading in tc['headings']:
                        if isinstance(heading, str) and len(heading.strip()) > 10:
                            text_parts.append(heading)
                # Get all paragraphs
                if 'paragraphs' in tc and isinstance(tc['paragraphs'], list):
                    for para in tc['paragraphs']:
                        if isinstance(para, str) and len(para.strip()) > 20:
                            text_parts.append(para)
                # Get lists
                if 'lists' in tc and isinstance(tc['lists'], list):
                    for list_item in tc['lists']:
                        if isinstance(list_item, str) and len(list_item.strip()) > 20:
                            text_parts.append(list_item)
                # Get quotes
                if 'quotes' in tc and isinstance(tc['quotes'], list):
                    for quote in tc['quotes']:
                        if isinstance(quote, str) and len(quote.strip()) > 20:
                            text_parts.append(quote)
        
        # Priority 2: Direct text fields (if text_content not available)
        if not text_parts:
            text_fields = ['clean_text', 'content', 'text', 'body', 'raw_text']
            for field in text_fields:
                if field in data and isinstance(data[field], str) and len(data[field]) > 50:
                    text_parts.append(data[field])
                    break
        
        # Priority 3: Extract from structured_data if available
        if 'structured_data' in data and isinstance(data['structured_data'], dict):
            structured = data['structured_data']
            # Try to get text from structured data
            if 'text' in structured and isinstance(structured['text'], str) and len(structured['text']) > 50:
                text_parts.append(structured['text'])
        
        # Priority 4: Extract from metadata/description fields
        if 'metadata' in data and isinstance(data['metadata'], dict):
            meta = data['metadata']
            for field in ['description', 'title', 'meta_description', 'og_description']:
                if field in meta and isinstance(meta[field], str) and len(meta[field]) > 20:
                    text_parts.append(meta[field])
        
        # Priority 5: Try top-level metadata fields
        for field in ['title', 'description', 'meta_description']:
            if field in data and isinstance(data[field], str) and len(data[field]) > 20:
                text_parts.append(data[field])
        
        # Combine all text parts, removing duplicates
        seen = set()
        unique_parts = []
        for part in text_parts:
            part_clean = part.strip()
            if part_clean and part_clean not in seen and len(part_clean) > 20:
                seen.add(part_clean)
                unique_parts.append(part_clean)
        
        combined_text = '\n\n'.join(unique_parts)
        
        # If we have meaningful text, return it
        if len(combined_text.strip()) > 100:
            return combined_text
        
        return ""
    except Exception as e:
        print(f"   ⚠️  Error reading JSON {json_file}: {e}")
        return ""

def get_list_of_json_files(directory: str) -> List[str]:
    """
    Find all *_complete.json files that might have text content.
    We'll use these as fallback if clean.txt files are missing.
    """
    json_files = []
    for root, dirs, files in os.walk(directory):
        if os.path.basename(root) == 'comprehensive_extraction':
            for file in files:
                if file.endswith('_complete.json') and not file.startswith('extracted_entities'):
                    json_files.append(os.path.join(root, file))
    return sorted(json_files)

def process_file(file_path: str, chunker: Chunker, embeddings: Embeddings, 
                 pinecone_storage: PineconeStorage) -> Tuple[int, int]:
    """
    Process a single file (txt or json) and store chunks in vector DB.
    
    Returns:
        Tuple of (chunks_created, chunks_stored)
    """
    file_path_obj = Path(file_path)
    company_name = file_path_obj.parent.parent.name  # Get company name from path
    filename = file_path_obj.name
    
    # Determine page type from filename
    page_type = filename.replace('_clean.txt', '').replace('_complete.json', '')
    
    try:
        if file_path.endswith('.txt'):
            # Read text file directly
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        elif file_path.endswith('.json'):
            # Extract text from JSON
            text = extract_text_from_json(file_path)
            if not text or len(text) < 50:
                return 0, 0  # Skip if no meaningful text
        else:
            return 0, 0
        
        if not text or len(text.strip()) < 50:
            return 0, 0  # Skip very short files
        
        # Chunk the text
        chunks = chunker.chunk_text(text)
        chunks_created = len(chunks)
        chunks_stored = 0
        
        # Store each chunk
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 20:  # Skip very short chunks
                continue
            
            try:
                embedding = embeddings.embed_text(chunk)
                # Create source path: company_name/page_type/chunk_index
                source_path = f"{company_name}/{page_type}"
                
                # Create unique ID: company_page_chunk_index
                chunk_id = f"{company_name}_{page_type}_{i}_{hash(chunk) % 10000}"
                
                pinecone_storage.store_embedding(
                    text=chunk,
                    embedding=embedding,
                    id=chunk_id,
                    source_path=source_path
                )
                chunks_stored += 1
            except Exception as e:
                print(f"   ⚠️  Error storing chunk {i}: {e}")
                continue
        
        return chunks_created, chunks_stored
        
    except Exception as e:
        print(f"   ❌ Error processing {file_path}: {e}")
        return 0, 0

# endregion: functions

# region: main
if __name__ == "__main__":
    print("="*80)
    print("🚀 Starting Chunking & Embedding Process")
    print("="*80)
    
    directory = os.path.join(Path(__file__).parent.parent, "data", "raw")
    print(f"📂 Directory: {directory}")
    
    # Get all clean text files (primary source)
    text_files = get_list_of_text_files(directory=directory)
    print(f"📄 Found {len(text_files)} *_clean.txt files")
    
    # Also get JSON files to extract text from
    json_files = get_list_of_json_files(directory=directory)
    print(f"📄 Found {len(json_files)} *_complete.json files")
    
    if not text_files and not json_files:
        print("❌ No files found! Make sure you've run the scraper first.")
        exit(1)
    
    # Combine both file types for processing
    all_files = text_files + json_files
    print(f"📊 Total files to process: {len(all_files)}")
    
    # Initialize services
    chunker = Chunker(chunk_size=1000)  # 1000 character chunks
    embeddings = Embeddings()
    pinecone_storage = PineconeStorage()
    
    print(f"\n📊 Processing files...")
    start_time = time.time()
    
    total_chunks = 0
    total_stored = 0
    companies_processed = set()
    
    for file_path in all_files:
        company_name = Path(file_path).parent.parent.name
        companies_processed.add(company_name)
        
        file_type = "📄" if file_path.endswith('.txt') else "📋"
        print(f"  {file_type} Processing: {Path(file_path).name} ({company_name})")
        chunks_created, chunks_stored = process_file(
            file_path, chunker, embeddings, pinecone_storage
        )
        total_chunks += chunks_created
        total_stored += chunks_stored
        if chunks_stored > 0:
            print(f"     ✓ Created {chunks_created} chunks, stored {chunks_stored}")
        else:
            print(f"     ⚠️  Skipped (no meaningful text extracted)")
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "="*80)
    print("✅ Chunking process completed successfully")
    print("="*80)
    print(f"📊 Statistics:")
    print(f"   • Companies processed: {len(companies_processed)}")
    print(f"   • TXT files processed: {len(text_files)}")
    print(f"   • JSON files processed: {len(json_files)}")
    print(f"   • Total files processed: {len(all_files)}")
    print(f"   • Total chunks created: {total_chunks}")
    print(f"   • Total chunks stored: {total_stored}")
    print(f"   • Time elapsed: {elapsed_time:.2f} seconds")
    if len(all_files) > 0:
        print(f"   • Average: {elapsed_time/len(all_files):.2f} seconds per file")
    print("="*80)
# endregion: main