"""
Assignment 5: Initial Load DAG (Version 2)
Performs initial data load, chunking, and payload assembly for Forbes AI 50 companies.

This DAG uses version2/ master folder structure to avoid conflicts with existing data:
- All data stored under: version2/raw/, version2/payloads/, version2/results/, version2/structured/

Flow:
1. Loads company list from GCS seed file (limited to 5 companies for testing)
2. Scrapes companies using scraper_v2.py → saves to version2/raw/{company_id}/comprehensive_extraction/
3. Chunks scraped text files and stores embeddings in Pinecone
4. Extracts structured data using structured_extraction_v2.py → reads from version2/raw/{company_id}/comprehensive_extraction/
5. Saves payloads to version2/payloads/ and structured data to version2/structured/
6. Stores results summary in version2/results/

Schedule: @once (manual trigger for initial load)
"""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil
import json
import logging
import os
import sys

from airflow import DAG
from airflow.decorators import task, task_group
from airflow.models import Variable

# Add src to path for imports (will be used in tasks)
src_path = '/opt/airflow/src'
if src_path not in sys.path:
    sys.path.insert(0, src_path)

logger = logging.getLogger(__name__)

# Get configuration from Airflow Variables (set in Cloud Composer)
try:
    GCS_BUCKET_NAME = Variable.get("GCS_BUCKET_NAME", default_var="")
    PROJECT_ID = Variable.get("PROJECT_ID", default_var="")
    PINECONE_API_KEY = Variable.get("PINECONE_API_KEY", default_var="")
    PINECONE_INDEX = Variable.get("PINECONE_INDEX", default_var="")
    EMBEDDING_MODEL = Variable.get("EMBEDDING_MODEL", default_var="text-embedding-3-small")
    EMBEDDING_DIMENSION = Variable.get("EMBEDDING_DIMENSION", default_var="1024")
except Exception:
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
    PROJECT_ID = os.getenv("PROJECT_ID", "")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX = os.getenv("PINECONE_INDEX", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION = os.getenv("EMBEDDING_DIMENSION", "1024")

# Default values
DEFAULT_BUCKET = "project-orbit-data-12345"  # Update with your bucket name
V2_MASTER_FOLDER = "version2"  # Master folder for version 2 data
SEED_FILE_PATH = "seed/forbes_ai50_seed.json"
RAW_DATA_PREFIX = f"{V2_MASTER_FOLDER}/raw/"
PAYLOADS_PREFIX = f"{V2_MASTER_FOLDER}/payloads/"
RESULTS_PREFIX = f"{V2_MASTER_FOLDER}/results/"
RUN_FOLDER = "comprehensive_extraction"  # Folder name for scraper output

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,  # Increased from 1 to 2 for better reliability with 50 companies
    'retry_delay': timedelta(minutes=10),  # Wait 10 minutes before retry
    # Enable parallel execution for pipeline behavior
    'max_active_tis_per_dag': 5,  # Reduced to 5 for batches of 3 companies
}

with DAG(
    'orbit_initial_load_dag',
    default_args=default_args,
    description='Initial load V2: Scrape → Chunk (Pinecone) + Extract (Payloads) - Processing all companies with controlled parallelism (max 5 concurrent), using version2/ folder',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['orbit', 'initial-load', 'scraping', 'extraction'],
    # Enable dynamic task mapping for pipeline behavior (per-company processing)
    max_active_tasks=5,  # Allow up to 5 companies to process in parallel (prevents resource exhaustion)
) as dag:

    @task
    def load_company_list(**context):
        """Load company list from GCS seed file (all companies, parallelism controlled by max_active_tasks)"""
        from gcs_utils import load_json_from_gcs, get_gcs_client  # Import here to avoid timeout
        import traceback
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        
        logger.info(f"Loading companies from gs://{bucket_name}/{SEED_FILE_PATH}")
        
        # Check if GCS client can be initialized
        try:
            client = get_gcs_client()
            logger.info(f"✅ GCS client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize GCS client: {e}")
            logger.error(f"   Traceback: {traceback.format_exc()}")
            raise ValueError(f"GCS client initialization failed: {e}")
        
        # Try to verify file exists before loading
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(SEED_FILE_PATH)
            exists = blob.exists()
            logger.info(f"   File exists check: {exists}")
            if not exists:
                # List available files in seed/ prefix for debugging
                logger.warning(f"   ⚠️  Seed file not found. Checking available files in seed/ prefix...")
                try:
                    seed_files = list(bucket.list_blobs(prefix="seed/"))
                    if seed_files:
                        logger.info(f"   Found {len(seed_files)} file(s) in seed/ prefix:")
                        for b in seed_files[:5]:  # Show first 5
                            logger.info(f"     - {b.name}")
                    else:
                        logger.warning(f"   No files found in seed/ prefix")
                except Exception as list_err:
                    logger.warning(f"   Could not list files: {list_err}")
        except Exception as check_err:
            logger.warning(f"   Could not check file existence: {check_err}")
        
        companies_data = load_json_from_gcs(bucket_name, SEED_FILE_PATH)
        
        if not companies_data:
            logger.error(f"❌ load_json_from_gcs returned None")
            raise ValueError(f"Failed to load seed file from GCS: gs://{bucket_name}/{SEED_FILE_PATH}. Check logs above for details.")
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company.get('website', '')).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0] if domain else company.get('company_name', '').lower()
        
        # Process all companies, but parallelism is controlled by max_active_tasks (set to 5)
        # This allows up to 5 companies to process in parallel, preventing resource exhaustion
        logger.info(f"✅ Loaded {len(companies_data)} total companies for processing")
        logger.info(f"   Parallelism: Up to 5 companies will process simultaneously")
        return companies_data

    @task(execution_timeout=timedelta(hours=2))  # Allow up to 2 hours per company (scraping can be slow)
    def scrape_company_data(company: dict, **context):
        """Scrape company using scraper_v2.py"""
        from scraper_v2 import scrape_company  # Import here to avoid timeout
        from gcs_utils import upload_directory_to_gcs  # Import here to avoid timeout
        import asyncio  # Import for async execution
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        logger.info(f"🔍 Scraping {company_name} ({company_id})")
        
        temp_dir = Path(tempfile.mkdtemp(prefix=f"scrape_{company_id}_"))
        run_folder = RUN_FOLDER  # Use comprehensive_extraction folder
        
        try:
            # Set environment variables for scraper_v2
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Scrape using scraper_v2 (it's async, so use asyncio.run)
            logger.info(f"  Starting async scraping for {company_name}...")
            logger.info(f"  Output directory: {temp_dir}")
            logger.info(f"  Run folder: {run_folder}")
            
            # Execute async scraping function (reduced max_pages for faster testing)
            result = asyncio.run(scrape_company(
                company=company,
                output_dir=temp_dir,
                run_folder=run_folder,
                max_pages=15  # Reduced from 30 for faster scraping
            ))
            
            logger.info(f"  Scraping function returned: status={result.get('status')}, pages_crawled={result.get('pages_crawled', 0)}")
            
            # Verify scraping was successful and files were created
            output_path = temp_dir / company_id / run_folder
            if not output_path.exists():
                raise ValueError(f"Scraping completed but no output directory created: {output_path}")
            
            # Check if any files were created
            files_created = list(output_path.glob("*"))
            if not files_created:
                raise ValueError(f"Scraping completed but no files were created in {output_path}")
            
            logger.info(f"  ✅ Scraping completed: {len(files_created)} files created in {output_path}")
            
            # Verify result status
            if result.get('status') != 'success':
                error_msg = result.get('error', 'Unknown error')
                logger.warning(f"  ⚠️  Scraping returned status: {result.get('status')}, error: {error_msg}")
                # Still try to upload if files exist
            
            # Upload to GCS
            company_gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
            logger.info(f"  Uploading to GCS: gs://{bucket_name}/{company_gcs_prefix}")
            
            uploaded_count = upload_directory_to_gcs(
                bucket_name=bucket_name,
                local_dir_path=str(output_path),
                gcs_prefix=company_gcs_prefix
            )
            
            if uploaded_count == 0:
                logger.warning(f"  ⚠️  No files were uploaded to GCS")
            
            result['files_uploaded'] = uploaded_count
            result['gcs_prefix'] = company_gcs_prefix
            result['status'] = 'success' if uploaded_count > 0 else 'partial'
            
            logger.info(f"✅ {company_name}: {uploaded_count} files uploaded to {company_gcs_prefix}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error scraping {company_name}: {e}", exc_info=True)
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
            return {
                "company_name": company_name,
                "company_id": company_id,
                "status": "error",
                "error": str(e),
                "files_uploaded": 0
            }
        finally:
            if temp_dir.exists():
                logger.info(f"  Cleaning up temp directory: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)

    @task(execution_timeout=timedelta(minutes=30))  # Allow up to 30 minutes for chunking
    def chunk_and_index(company: dict, scrape_result: dict, **context):
        """Chunk scraped text files and store embeddings in Pinecone"""
        from services.chunker import Chunker
        from services.embeddings import Embeddings, PineconeStorage
        from gcs_utils import list_files_from_gcs, read_file_from_gcs
        import json
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        logger.info(f"🔗 Chunking and indexing {company_name} ({company_id})")
        
        # Check if scraping was successful
        if scrape_result.get('status') != 'success':
            logger.warning(f"⏭️  Skipping chunking for {company_name} - scraping failed")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "skipped",
                "reason": "scraping_failed",
                "chunks_created": 0,
                "chunks_stored": 0
            }
        
        try:
            # Set environment variables
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Set Pinecone environment variables (from module-level variables or env)
            # Use module-level variables that were loaded at DAG definition time
            pinecone_api_key = PINECONE_API_KEY or os.getenv("PINECONE_API_KEY", "")
            pinecone_index = PINECONE_INDEX or os.getenv("PINECONE_INDEX", "")
            embedding_model = EMBEDDING_MODEL or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            embedding_dimension = EMBEDDING_DIMENSION or os.getenv("EMBEDDING_DIMENSION", "1024")
            
            # Set them in environment for PineconeStorage to use
            if pinecone_api_key:
                os.environ['PINECONE_API_KEY'] = pinecone_api_key
            if pinecone_index:
                os.environ['PINECONE_INDEX'] = pinecone_index
            if embedding_model:
                os.environ['EMBEDDING_MODEL'] = embedding_model
            if embedding_dimension:
                os.environ['EMBEDDING_DIMENSION'] = embedding_dimension
            
            # Verify required variables are set
            if not pinecone_api_key:
                raise ValueError("PINECONE_API_KEY is not set. Please set it in Airflow Variables or .env file")
            if not pinecone_index:
                raise ValueError("PINECONE_INDEX is not set. Please set it in Airflow Variables or .env file")
            
            # Initialize services
            chunker = Chunker(chunk_size=1000)
            embeddings = Embeddings()
            pinecone_storage = PineconeStorage()
            
            # List files from GCS (using version2/raw structure)
            gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{RUN_FOLDER}/"
            all_files = list_files_from_gcs(bucket_name, gcs_prefix)
            
            # Filter for text and JSON files
            text_files = [f for f in all_files if f.endswith('_clean.txt') and 'blog_posts' not in f]
            json_files = [f for f in all_files if f.endswith('_complete.json') and 'extracted_entities' not in f and 'blog_posts' not in f]
            
            logger.info(f"  Found {len(text_files)} text files and {len(json_files)} JSON files")
            
            total_chunks_created = 0
            total_chunks_stored = 0
            
            # Process text files
            for file_path in text_files:
                try:
                    # Read file from GCS
                    text = read_file_from_gcs(bucket_name, file_path)
                    if not text or len(text.strip()) < 50:
                        continue
                    
                    # Determine page type
                    filename = Path(file_path).name
                    page_type = filename.replace('_clean.txt', '')
                    
                    # Chunk the text
                    chunks = chunker.chunk_text(text)
                    total_chunks_created += len(chunks)
                    
                    # Store each chunk
                    for i, chunk in enumerate(chunks):
                        if len(chunk.strip()) < 20:
                            continue
                        
                        try:
                            embedding = embeddings.embed_text(chunk)
                            source_path = f"{company_id}/{page_type}"
                            chunk_id = f"{company_id}_{page_type}_{i}_{hash(chunk) % 10000}"
                            
                            pinecone_storage.store_embedding(
                                text=chunk,
                                embedding=embedding,
                                id=chunk_id,
                                source_path=source_path
                            )
                            total_chunks_stored += 1
                        except Exception as e:
                            logger.warning(f"  ⚠️  Error storing chunk {i} from {filename}: {e}")
                            continue
                    
                except Exception as e:
                    logger.warning(f"  ⚠️  Error processing {file_path}: {e}")
                    continue
            
            # Process JSON files (extract text first)
            for file_path in json_files:
                try:
                    # Read and extract text from JSON
                    json_content = read_file_from_gcs(bucket_name, file_path)
                    if not json_content:
                        continue
                    
                    data = json.loads(json_content)
                    
                    # Extract text from JSON
                    text_parts = []
                    if 'text_content' in data and isinstance(data['text_content'], dict):
                        tc = data['text_content']
                        if 'full_text' in tc and isinstance(tc['full_text'], str) and len(tc['full_text']) > 100:
                            text_parts.append(tc['full_text'])
                    
                    if not text_parts:
                        continue
                    
                    text = '\n\n'.join(text_parts)
                    if len(text.strip()) < 50:
                        continue
                    
                    # Determine page type
                    filename = Path(file_path).name
                    page_type = filename.replace('_complete.json', '')
                    
                    # Chunk and store
                    chunks = chunker.chunk_text(text)
                    total_chunks_created += len(chunks)
                    
                    for i, chunk in enumerate(chunks):
                        if len(chunk.strip()) < 20:
                            continue
                        
                        try:
                            embedding = embeddings.embed_text(chunk)
                            source_path = f"{company_id}/{page_type}"
                            chunk_id = f"{company_id}_{page_type}_{i}_{hash(chunk) % 10000}"
                            
                            pinecone_storage.store_embedding(
                                text=chunk,
                                embedding=embedding,
                                id=chunk_id,
                                source_path=source_path
                            )
                            total_chunks_stored += 1
                        except Exception as e:
                            logger.warning(f"  ⚠️  Error storing chunk {i} from {filename}: {e}")
                            continue
                    
                except Exception as e:
                    logger.warning(f"  ⚠️  Error processing {file_path}: {e}")
                    continue
            
            logger.info(f"✅ {company_name}: Created {total_chunks_created} chunks, stored {total_chunks_stored} in Pinecone")
            
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "success",
                "chunks_created": total_chunks_created,
                "chunks_stored": total_chunks_stored,
                "files_processed": len(text_files) + len(json_files)
            }
            
        except Exception as e:
            logger.error(f"❌ Error chunking {company_name}: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "error",
                "error": str(e),
                "chunks_created": 0,
                "chunks_stored": 0
            }

    @task(execution_timeout=timedelta(minutes=15))  # Allow up to 15 minutes for extraction
    def extract_and_save_payload(company: dict, scrape_result: dict, **context):
        """Extract structured data and save payload using structured_extraction_v2.py"""
        from structured_extraction_v2 import extract_company_payload, save_payload_to_storage  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        # Check if scraping was successful
        if scrape_result.get('status') != 'success':
            logger.warning(f"⏭️  Skipping extraction for {company_name} - scraping failed")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "skipped",
                "reason": "scraping_failed"
            }
        
        logger.info(f"📊 Extracting payload for {company_name} ({company_id})")
        
        try:
            # Set environment variables for structured_extraction_v2
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            os.environ['V2_MASTER_FOLDER'] = V2_MASTER_FOLDER  # Tell structured_extraction_v2 to use version2/ prefix
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Extract payload using structured_extraction_v2
            payload = extract_company_payload(company_id)
            
            # Save payload to storage (GCS or local)
            saved_path = save_payload_to_storage(company_id, payload)
            
            logger.info(f"✅ {company_name}: Payload saved to {saved_path}")
            
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "success",
                "payload_path": str(saved_path) if saved_path else None,
                "events_count": len(payload.events) if hasattr(payload, 'events') else 0,
                "products_count": len(payload.products) if hasattr(payload, 'products') else 0,
                "leadership_count": len(payload.leadership) if hasattr(payload, 'leadership') else 0,
            }
            
        except Exception as e:
            logger.error(f"❌ Error extracting payload for {company_name}: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "error",
                "error": str(e)
            }

    @task
    def log_initial_load_results(scrape_results: list, chunking_results: list, payload_results: list, **context):
        """Log and store initial load results to GCS bucket"""
        from gcs_utils import save_json_to_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        
        # Resolve LazyXComAccess objects to actual lists/dicts for JSON serialization
        # When using .expand(), Airflow returns LazyXComAccess which needs to be resolved
        try:
            # Convert to list if it's a LazyXComAccess object
            if hasattr(scrape_results, '__iter__') and not isinstance(scrape_results, (list, dict, str)):
                scrape_results = list(scrape_results)
            if hasattr(chunking_results, '__iter__') and not isinstance(chunking_results, (list, dict, str)):
                chunking_results = list(chunking_results)
            if hasattr(payload_results, '__iter__') and not isinstance(payload_results, (list, dict, str)):
                payload_results = list(payload_results)
        except Exception as e:
            logger.warning(f"⚠️  Could not resolve LazyXComAccess, trying alternative method: {e}")
            # Alternative: convert to list explicitly
            scrape_results = [r for r in scrape_results] if scrape_results else []
            chunking_results = [r for r in chunking_results] if chunking_results else []
            payload_results = [r for r in payload_results] if payload_results else []
        
        # Calculate statistics
        scraping_successful = len([r for r in scrape_results if r.get('status') == 'success'])
        scraping_failed = len([r for r in scrape_results if r.get('status') != 'success'])
        
        chunking_successful = len([r for r in chunking_results if r.get('status') == 'success'])
        chunking_failed = len([r for r in chunking_results if r.get('status') == 'error'])
        chunking_skipped = len([r for r in chunking_results if r.get('status') == 'skipped'])
        total_chunks = sum(r.get('chunks_stored', 0) for r in chunking_results)
        
        extraction_successful = len([r for r in payload_results if r.get('status') == 'success'])
        extraction_failed = len([r for r in payload_results if r.get('status') == 'error'])
        extraction_skipped = len([r for r in payload_results if r.get('status') == 'skipped'])
        
        total_files = sum(r.get('files_uploaded', 0) for r in scrape_results)
        total_events = sum(r.get('events_count', 0) for r in payload_results)
        total_products = sum(r.get('products_count', 0) for r in payload_results)
        total_leadership = sum(r.get('leadership_count', 0) for r in payload_results)
        
        summary = {
            "load_date": datetime.now().isoformat(),
            "version": "v2-initial-load-with-chunking",
            "folder_structure": f"{V2_MASTER_FOLDER}/",
            "dag_run_id": context.get('dag_run').run_id if context.get('dag_run') else None,
            "total_companies": len(scrape_results),
            "scraping": {
                "successful": scraping_successful,
                "failed": scraping_failed,
                "total_files_uploaded": total_files
            },
            "chunking": {
                "successful": chunking_successful,
                "failed": chunking_failed,
                "skipped": chunking_skipped,
                "total_chunks_stored": total_chunks
            },
            "extraction": {
                "successful": extraction_successful,
                "failed": extraction_failed,
                "skipped": extraction_skipped,
                "total_events": total_events,
                "total_products": total_products,
                "total_leadership": total_leadership
            },
            "companies": {
                "scraping": scrape_results,
                "chunking": chunking_results,
                "extraction": payload_results
            }
        }
        
        # Save to GCS bucket
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_path = f"{RESULTS_PREFIX}initial_load_{timestamp}.json"
        
        success = save_json_to_gcs(bucket_name, summary, results_path)
        
        if success:
            logger.info(f"✅ Initial load results saved to gs://{bucket_name}/{results_path}")
            logger.info(f"   Scraping: {scraping_successful}/{len(scrape_results)} successful, {total_files} files")
            logger.info(f"   Chunking: {chunking_successful}/{len(chunking_results)} successful, {total_chunks} chunks stored")
            logger.info(f"   Extraction: {extraction_successful}/{len(payload_results)} successful")
            logger.info(f"   Events: {total_events}, Products: {total_products}, Leadership: {total_leadership}")
        else:
            logger.error(f"❌ Failed to save results to GCS")
        
        return summary

    # Define task flow - Pipeline pattern: each company processes independently
    # Using .expand() with mapped dependencies - Airflow 2.x should start downstream tasks
    # as soon as individual upstream tasks complete (per-task dependencies)
    companies = load_company_list()
    
    # Step 1: Scrape all companies (parallel)
    scrape_results = scrape_company_data.expand(company=companies)
    
    # Step 2 & 3: Chunk and Extract (parallel, per-company pipeline)
    # Each company's chunk/extract depends only on that company's scrape result
    # This should enable pipeline behavior where chunking starts as soon as each company's scraping finishes
    chunking_results = chunk_and_index.expand(
        company=companies,
        scrape_result=scrape_results
    )
    
    payload_results = extract_and_save_payload.expand(
        company=companies,
        scrape_result=scrape_results
    )
    
    # Step 4: Log results (depends on all)
    final_summary = log_initial_load_results(scrape_results, chunking_results, payload_results)