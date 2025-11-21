# Handle Chunking - End-to-End Explanation

## Overview

`handle_chunking.py` is a data processing pipeline that takes scraped company website content and prepares it for vector search. It chunks text content, generates embeddings, and stores them in a vector database (Pinecone) for semantic search capabilities.

### Key Features
- **Text Extraction**: Extracts text from both `*_clean.txt` files and `*_complete.json` files
- **Intelligent Chunking**: Splits text into 1000-character chunks using the Chunker service
- **Embedding Generation**: Creates embeddings using the Embeddings service
- **Vector Storage**: Stores chunks with metadata in Pinecone for retrieval
- **Source Tracking**: Maintains source paths (company/page_type) for each chunk

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Entry Point                         │
│  main() → Process all files                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              File Discovery                                  │
│  get_list_of_text_files() → Find *_clean.txt               │
│  get_list_of_json_files() → Find *_complete.json           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              File Processing Loop                            │
│  For each file:                                             │
│    process_file()                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Text         │ │ Chunking     │ │ Embedding    │
│ Extraction   │ │ Service      │ │ Service      │
└──────────────┘ └──────────────┘ └──────────────┘
        │              │              │
        └──────────────┴──────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Pinecone Storage                                │
│  Store chunks with metadata                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Function Catalog

### 1. File Discovery Functions

#### `get_list_of_text_files(directory: str) -> List[str]`
**Purpose**: Recursively find all `*_clean.txt` files in `comprehensive_extraction` directories.

**Search Pattern**:
- Looks for directories named `comprehensive_extraction`
- Finds files ending with `_clean.txt`
- Structure: `data/raw/{company_name}/comprehensive_extraction/*_clean.txt`

**Returns**: Sorted list of file paths.

**Example**:
```
data/raw/anthropic/comprehensive_extraction/homepage_clean.txt
data/raw/anthropic/comprehensive_extraction/about_clean.txt
```

---

#### `get_list_of_json_files(directory: str) -> List[str]`
**Purpose**: Find all `*_complete.json` files that might contain text content.

**Search Pattern**:
- Looks for directories named `comprehensive_extraction`
- Finds files ending with `_complete.json`
- Excludes `extracted_entities.json` files

**Returns**: Sorted list of file paths.

**Use Case**: Fallback if `_clean.txt` files are missing or incomplete.

---

### 2. Text Extraction Functions

#### `extract_text_from_json(json_file: str) -> str`
**Purpose**: Extract meaningful text content from a `*_complete.json` file using multiple strategies.

**Extraction Priority**:

1. **Priority 1: `text_content` dict** (most comprehensive)
   - `full_text`: Complete text content (best source)
   - If no `full_text`, reconstructs from:
     - `headings`: All heading text (h1-h6)
     - `paragraphs`: All paragraph text
     - `lists`: All list items
     - `quotes`: All blockquote text

2. **Priority 2: Direct text fields**
   - `clean_text`, `content`, `text`, `body`, `raw_text`
   - Uses first field found with >50 characters

3. **Priority 3: Structured data**
   - Extracts from `structured_data.text` if available

4. **Priority 4: Metadata fields**
   - `description`, `title`, `meta_description`, `og_description`

5. **Priority 5: Top-level fields**
   - `title`, `description`, `meta_description`

**Text Processing**:
- Removes duplicates
- Filters out very short text (<20 characters)
- Combines all parts with `\n\n` separator
- Returns empty string if final text <100 characters

**Returns**: Combined text string or empty string.

**Error Handling**: Returns empty string on any exception.

---

### 3. File Processing Function

#### `process_file(file_path: str, chunker: Chunker, embeddings: Embeddings, pinecone_storage: PineconeStorage) -> Tuple[int, int]`
**Purpose**: Process a single file (txt or json) and store chunks in vector database.

**Process Flow**:

1. **Extract Company & Page Type**:
   ```python
   company_name = file_path.parent.parent.name  # e.g., "anthropic"
   page_type = filename.replace('_clean.txt', '').replace('_complete.json', '')
   # e.g., "homepage", "about", "careers"
   ```

2. **Read Text Content**:
   - If `.txt`: Read directly
   - If `.json`: Extract text using `extract_text_from_json()`
   - Skip if no meaningful text (<50 characters)

3. **Chunk Text**:
   - Use `chunker.chunk_text(text)` to split into chunks
   - Default chunk size: 1000 characters

4. **Store Each Chunk**:
   - Generate embedding: `embeddings.embed_text(chunk)`
   - Create source path: `{company_name}/{page_type}`
   - Create unique ID: `{company_name}_{page_type}_{chunk_index}_{hash}`
   - Store in Pinecone with:
     - `text`: Chunk content
     - `embedding`: Vector embedding
     - `id`: Unique identifier
     - `source_path`: Company and page type

5. **Skip Very Short Chunks**: Chunks <20 characters are skipped

**Returns**: Tuple of `(chunks_created, chunks_stored)`

**Error Handling**:
- Returns `(0, 0)` on any exception
- Logs errors but continues processing

---

### 4. Main Execution Flow

#### `main()` (if `__name__ == "__main__"`)
**Purpose**: Main entry point that orchestrates the entire chunking process.

**Execution Flow**:

1. **Initialize**:
   - Set up directory path: `data/raw`
   - Print header with process name

2. **Discover Files**:
   - Find all `*_clean.txt` files
   - Find all `*_complete.json` files
   - Combine both lists
   - Exit if no files found

3. **Initialize Services**:
   - `Chunker(chunk_size=1000)`: 1000-character chunks
   - `Embeddings()`: Embedding generation service
   - `PineconeStorage()`: Vector database storage

4. **Process Files**:
   - For each file:
     - Extract company name
     - Track companies processed
     - Call `process_file()`
     - Accumulate statistics (chunks created, stored)
     - Print progress

5. **Print Summary**:
   - Companies processed
   - Files processed (TXT vs JSON)
   - Total chunks created
   - Total chunks stored
   - Time elapsed
   - Average time per file

---

## End-to-End Flow

### 1. Initialization Phase

```
main()
  └─> Set directory: data/raw
  └─> get_list_of_text_files()
       └─> Walk directory tree
       └─> Find comprehensive_extraction directories
       └─> Collect *_clean.txt files
  └─> get_list_of_json_files()
       └─> Walk directory tree
       └─> Find comprehensive_extraction directories
       └─> Collect *_complete.json files
  └─> Combine file lists
  └─> Initialize services:
       ├─> Chunker(chunk_size=1000)
       ├─> Embeddings()
       └─> PineconeStorage()
```

### 2. File Processing Phase

```
For each file in all_files:
  └─> process_file()
       ├─> Extract company_name and page_type from path
       │
       ├─> Read text content:
       │    ├─> If .txt: Read directly
       │    └─> If .json: extract_text_from_json()
       │         ├─> Try text_content.full_text
       │         ├─> Try text_content components (headings, paragraphs, lists)
       │         ├─> Try direct text fields
       │         ├─> Try structured_data
       │         └─> Try metadata fields
       │
       ├─> Skip if text < 50 characters
       │
       ├─> Chunk text:
       │    └─> chunker.chunk_text(text)
       │         └─> Returns list of ~1000-character chunks
       │
       └─> For each chunk:
            ├─> Skip if chunk < 20 characters
            ├─> Generate embedding:
            │    └─> embeddings.embed_text(chunk)
            ├─> Create metadata:
            │    ├─> source_path: "{company_name}/{page_type}"
            │    └─> chunk_id: "{company_name}_{page_type}_{index}_{hash}"
            └─> Store in Pinecone:
                 └─> pinecone_storage.store_embedding(
                      text=chunk,
                      embedding=embedding,
                      id=chunk_id,
                      source_path=source_path
                 )
```

### 3. Summary Phase

```
main() (continued)
  └─> Calculate statistics:
       ├─> Companies processed (unique set)
       ├─> TXT files processed
       ├─> JSON files processed
       ├─> Total chunks created
       ├─> Total chunks stored
       └─> Time elapsed
  └─> Print summary report
```

---

## Key Concepts

### 1. File Structure

The script expects files in this structure:
```
data/raw/
  {company_name}/
    comprehensive_extraction/
      homepage_clean.txt
      homepage_complete.json
      about_clean.txt
      about_complete.json
      careers_clean.txt
      careers_complete.json
      ...
```

### 2. Chunking Strategy

- **Chunk Size**: 1000 characters (configurable via Chunker)
- **Overlap**: Handled by Chunker service (if configured)
- **Minimum Chunk**: 20 characters (very short chunks are skipped)

### 3. Source Path Format

Source paths follow the pattern: `{company_name}/{page_type}`

**Examples**:
- `anthropic/homepage`
- `anthropic/about`
- `baseten/careers`

This allows filtering search results by company or page type.

### 4. Chunk ID Format

Chunk IDs follow the pattern: `{company_name}_{page_type}_{chunk_index}_{hash}`

**Examples**:
- `anthropic_homepage_0_1234`
- `anthropic_homepage_1_5678`

The hash ensures uniqueness even if chunk content is similar.

### 5. Text Extraction Priority

When extracting from JSON files, the script tries multiple sources in order:
1. Structured text content (best quality)
2. Direct text fields
3. Structured data
4. Metadata fields

This ensures maximum text recovery from different JSON structures.

### 6. Error Handling

- **File Read Errors**: Logged, returns empty string, file skipped
- **Chunking Errors**: Logged, file skipped
- **Embedding Errors**: Logged, chunk skipped, processing continues
- **Storage Errors**: Logged, chunk skipped, processing continues

The process is resilient and continues even if individual files or chunks fail.

---

## Dependencies

### Internal Services
- **`services.chunker.Chunker`**: Text chunking service
- **`services.embeddings.Embeddings`**: Embedding generation service
- **`services.embeddings.PineconeStorage`**: Vector database storage service

### Standard Library
- `os`: File system operations
- `json`: JSON parsing
- `pathlib.Path`: Path handling
- `time`: Timing measurements
- `typing`: Type hints

---

## Usage

### Command Line

```bash
# Run from project root
python src/handle_chunking.py
```

### Expected Output

```
================================================================================
🚀 Starting Chunking & Embedding Process
================================================================================
📂 Directory: data/raw
📄 Found 24 *_clean.txt files
📄 Found 24 *_complete.json files
📊 Total files to process: 48

📊 Processing files...
  📄 Processing: homepage_clean.txt (anthropic)
     ✓ Created 5 chunks, stored 5
  📄 Processing: about_clean.txt (anthropic)
     ✓ Created 12 chunks, stored 12
  ...

================================================================================
✅ Chunking process completed successfully
================================================================================
📊 Statistics:
   • Companies processed: 5
   • TXT files processed: 24
   • JSON files processed: 24
   • Total files processed: 48
   • Total chunks created: 342
   • Total chunks stored: 342
   • Time elapsed: 45.23 seconds
   • Average: 0.94 seconds per file
================================================================================
```

---

## Output

### Vector Database (Pinecone)

Each chunk is stored with:
- **ID**: Unique identifier
- **Embedding**: Vector representation (dimensions depend on embedding model)
- **Metadata**:
  - `text`: Original chunk text
  - `source_path`: Company and page type

### Search Capabilities

After processing, you can:
- Search by semantic similarity (using embeddings)
- Filter by company: `source_path.startswith("anthropic/")`
- Filter by page type: `source_path.endswith("/homepage")`
- Retrieve original text from stored chunks

---

## Performance Considerations

1. **Batch Processing**: Files are processed sequentially (can be parallelized)
2. **Chunk Size**: 1000 characters balances context vs. granularity
3. **Embedding Generation**: May be rate-limited by API (if using external service)
4. **Storage**: Pinecone operations are async but called sequentially

### Optimization Opportunities

- Parallel file processing (multiprocessing/threading)
- Batch embedding generation
- Batch Pinecone storage operations
- Caching embeddings for duplicate chunks

---

## Error Scenarios

### No Files Found
```
❌ No files found! Make sure you've run the scraper first.
```
**Solution**: Run `scraper_v2.py` first to generate `*_clean.txt` and `*_complete.json` files.

### Missing Services
If Chunker, Embeddings, or PineconeStorage are not properly configured:
- Check service initialization
- Verify API keys (if using external services)
- Check service dependencies

### Empty Text Extraction
If JSON files don't contain extractable text:
- Check JSON structure matches expected format
- Verify text fields exist in JSON
- May need to adjust `extract_text_from_json()` priority logic

---

## Integration with Other Components

### Input
- **Source**: Output from `scraper_v2.py`
- **Files**: `*_clean.txt` and `*_complete.json` in `comprehensive_extraction` directories

### Output
- **Vector Database**: Pinecone with embedded chunks
- **Use Case**: Semantic search for RAG pipeline

### Next Steps
After chunking, the vector database can be used by:
- `rag_pipeline.py`: Retrieval-Augmented Generation
- `rag_search.py`: Semantic search queries
- Dashboard applications: Company information retrieval

---

## Future Enhancements

Potential improvements:
- **Incremental Processing**: Only process new/changed files
- **Parallel Processing**: Process multiple files concurrently
- **Chunk Overlap**: Configurable overlap between chunks
- **Metadata Enrichment**: Add more metadata (page URL, crawl date, etc.)
- **Deduplication**: Skip duplicate chunks across files
- **Progress Persistence**: Resume from last processed file
- **Chunk Quality Scoring**: Filter low-quality chunks

