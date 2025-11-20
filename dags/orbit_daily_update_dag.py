"""
Assignment 5: Daily Update DAG (Version 2)
Incremental updates of snapshots and vector DB for all Forbes AI 50 companies.

This DAG uses version2/ master folder structure to match initial load:
- All data stored under: version2/raw/, version2/payloads/, version2/results/

Flow:
1. Loads company list from GCS seed file
2. Checks for changes in key pages (homepage, about, careers, blog) by comparing with version2/raw/{company_id}/comprehensive_extraction/
3. Re-scrapes changed pages using scraper_v2.py → saves to version2/raw/{company_id}/daily_{date}/
4. Chunks changed pages and updates Pinecone embeddings
5. Updates structured extraction for changed companies → reads from version2/raw/{company_id}/daily_{date}/
6. Updates payloads in version2/payloads/
7. Stores daily update results in version2/results/

Schedule: 0 3 * * * (3 AM daily)
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
from airflow.decorators import task
from airflow.models import Variable

# Add src to path for imports (will be used in tasks)
src_path = '/opt/airflow/src'
if src_path not in sys.path:
    sys.path.insert(0, src_path)

logger = logging.getLogger(__name__)

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
RUN_FOLDER = "comprehensive_extraction"  # Folder name for initial load scraper output
RAW_DATA_PREFIX = f"{V2_MASTER_FOLDER}/raw/"
PAYLOADS_PREFIX = f"{V2_MASTER_FOLDER}/payloads/"
RESULTS_PREFIX = f"{V2_MASTER_FOLDER}/results/"
KEY_PAGES = ["homepage", "about", "careers", "blog"]

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
    'max_active_tis_per_dag': 5,
}

with DAG(
    'orbit_daily_update_dag',
    default_args=default_args,
    description='Daily update V2: Incremental scraping + chunking + extraction - Using version2/ folder structure',
    schedule_interval='0 3 * * *',  # 3 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['orbit', 'daily-update', 'incremental', 'version2'],
    max_active_tasks=5,  # Control parallelism
) as dag:

    @task
    def load_company_list(**context):
        """Load company list from GCS"""
        from gcs_utils import load_json_from_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        companies_data = load_json_from_gcs(bucket_name, SEED_FILE_PATH)
        
        if not companies_data:
            raise ValueError(f"Failed to load seed file from GCS: gs://{bucket_name}/{SEED_FILE_PATH}")
        
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company.get('website', '')).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0] if domain else company.get('company_name', '').lower()
        
        logger.info(f"✅ Loaded {len(companies_data)} companies for daily update")
        return companies_data

    @task(execution_timeout=timedelta(hours=2))  # Allow up to 2 hours per company
    def check_and_scrape_changes(company: dict, **context):
        """Check for changes and re-scrape if needed"""
        from scraper_v2 import scrape_company  # Import here to avoid timeout
        from gcs_utils import (
            check_gcs_file_exists,
            list_gcs_files,
            load_json_from_gcs,
            upload_directory_to_gcs
        )  # Import here to avoid timeout
        import asyncio  # Import for async execution
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        today = datetime.now().strftime('%Y-%m-%d')
        run_folder = f"daily_{today}"
        
        logger.info(f"🔍 Checking changes for {company_name} ({company_id})")
        
        # Check previous metadata for content hashes
        previous_hashes = {}
        try:
            # Try to load latest metadata from comprehensive_extraction (initial load) first
            initial_metadata_path = f"{RAW_DATA_PREFIX}{company_id}/{RUN_FOLDER}/metadata.json"
            if check_gcs_file_exists(bucket_name, initial_metadata_path):
                metadata = load_json_from_gcs(bucket_name, initial_metadata_path)
                if metadata and 'pages' in metadata:
                    for page_info in metadata['pages']:
                        if page_info.get('found') and page_info.get('content_hash'):
                            previous_hashes[page_info['page_type']] = page_info['content_hash']
            
            # Also check latest daily run (in version2 structure)
            daily_prefix = f"{RAW_DATA_PREFIX}{company_id}/daily_"
            daily_runs = list_gcs_files(bucket_name, daily_prefix)
            if daily_runs:
                # Extract dates and get most recent
                daily_dates = []
                for run_path in daily_runs:
                    # Extract date from path like "raw/company_id/daily_2025-01-15/"
                    parts = run_path.split('/')
                    for part in parts:
                        if part.startswith('daily_'):
                            date_str = part.replace('daily_', '')
                            try:
                                datetime.strptime(date_str, '%Y-%m-%d')
                                daily_dates.append((date_str, run_path))
                            except:
                                pass
                
                if daily_dates:
                    daily_dates.sort(reverse=True)  # Most recent first
                    latest_date, latest_path = daily_dates[0]
                    latest_metadata_path = f"{latest_path.rstrip('/')}/metadata.json"
                    
                    if check_gcs_file_exists(bucket_name, latest_metadata_path):
                        metadata = load_json_from_gcs(bucket_name, latest_metadata_path)
                        if metadata and 'pages' in metadata:
                            for page_info in metadata['pages']:
                                if page_info.get('found') and page_info.get('content_hash'):
                                    previous_hashes[page_info['page_type']] = page_info['content_hash']
        except Exception as e:
            logger.warning(f"Could not load previous metadata for {company_name}: {e}")
        
        temp_dir = Path(tempfile.mkdtemp(prefix=f"daily_{company_id}_"))
        changed_pages = []
        
        try:
            # Set environment variables
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Scrape company (scraper_v2 will handle change detection)
            # Note: scrape_company is async, so we need to use asyncio.run()
            result = asyncio.run(scrape_company(
                company=company,
                output_dir=temp_dir,
                run_folder=run_folder,
                max_pages=30
            ))
            
            # Check which pages changed
            new_metadata_path = temp_dir / company_id / run_folder / "metadata.json"
            if new_metadata_path.exists():
                new_metadata = json.loads(new_metadata_path.read_text())
                if 'pages' in new_metadata:
                    for page_info in new_metadata['pages']:
                        page_type = page_info.get('page_type')
                        new_hash = page_info.get('content_hash')
                        
                        if page_type in KEY_PAGES:
                            old_hash = previous_hashes.get(page_type)
                            if old_hash != new_hash:
                                changed_pages.append(page_type)
                                logger.info(f"  📝 {page_type}: Changed")
            
            # Upload to GCS
            company_gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
            uploaded_count = upload_directory_to_gcs(
                bucket_name=bucket_name,
                local_dir_path=str(temp_dir / company_id / run_folder),
                gcs_prefix=company_gcs_prefix
            )
            
            result['files_uploaded'] = uploaded_count
            result['changed_pages'] = changed_pages
            result['has_changes'] = len(changed_pages) > 0
            result['gcs_prefix'] = company_gcs_prefix
            
            logger.info(f"  ✅ {company_name}: {len(changed_pages)} pages changed, {uploaded_count} files uploaded")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in daily update for {company_name}: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "error",
                "error": str(e),
                "has_changes": False,
                "changed_pages": []
            }
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @task(execution_timeout=timedelta(minutes=30))
    def chunk_changed_pages(company: dict, scrape_result: dict, **context):
        """Chunk changed pages and update Pinecone embeddings"""
        from services.chunker import Chunker
        from services.embeddings import Embeddings, PineconeStorage
        from gcs_utils import list_files_from_gcs, read_file_from_gcs
        import json
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        # Skip if no changes
        if not scrape_result.get('has_changes', False):
            logger.info(f"⏭️  Skipping chunking for {company_name} - no changes")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "skipped",
                "reason": "no_changes",
                "chunks_created": 0,
                "chunks_stored": 0
            }
        
        logger.info(f"🔗 Chunking changed pages for {company_name} ({company_id})")
        
        try:
            # Set environment variables
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Set Pinecone environment variables
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
            
            # Get today's run folder
            today = datetime.now().strftime('%Y-%m-%d')
            run_folder = f"daily_{today}"
            
            # List files from today's daily run
            gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
            all_files = list_files_from_gcs(bucket_name, gcs_prefix)
            
            # Filter for text and JSON files
            text_files = [f for f in all_files if f.endswith('_clean.txt') and 'blog_posts' not in f]
            json_files = [f for f in all_files if f.endswith('_complete.json') and 'extracted_entities' not in f and 'blog_posts' not in f]
            
            # Only process changed pages
            changed_pages = scrape_result.get('changed_pages', [])
            if changed_pages:
                # Filter files to only include changed pages
                text_files = [f for f in text_files if any(page in f for page in changed_pages)]
                json_files = [f for f in json_files if any(page in f for page in changed_pages)]
            
            logger.info(f"  Found {len(text_files)} text files and {len(json_files)} JSON files for changed pages")
            
            total_chunks_created = 0
            total_chunks_stored = 0
            
            # Process text files
            for file_path in text_files:
                try:
                    text = read_file_from_gcs(bucket_name, file_path)
                    if not text or len(text.strip()) < 50:
                        continue
                    
                    filename = Path(file_path).name
                    page_type = filename.replace('_clean.txt', '')
                    
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
            
            # Process JSON files
            for file_path in json_files:
                try:
                    json_content = read_file_from_gcs(bucket_name, file_path)
                    if not json_content:
                        continue
                    
                    data = json.loads(json_content)
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
                    
                    filename = Path(file_path).name
                    page_type = filename.replace('_complete.json', '')
                    
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
    def update_payload_if_changed(company: dict, scrape_result: dict, **context):
        """Update payload only if pages changed"""
        from structured_extraction_v2 import extract_company_payload, save_payload_to_storage  # Import here to avoid timeout
        
        if not scrape_result.get('has_changes', False):
            logger.info(f"⏭️  Skipping {company.get('company_name')} - no changes detected")
            return {
                "company_id": company.get('company_id'),
                "company_name": company.get('company_name'),
                "status": "skipped",
                "reason": "no_changes"
            }
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        logger.info(f"📊 Updating payload for {company_name} (changes detected)")
        
        try:
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            os.environ['V2_MASTER_FOLDER'] = V2_MASTER_FOLDER  # Tell structured_extraction_v2 to use version2/ prefix
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Re-extract payload
            payload = extract_company_payload(company_id)
            saved_path = save_payload_to_storage(company_id, payload)
            
            logger.info(f"✅ {company_name}: Payload updated at {saved_path}")
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
            logger.error(f"❌ Error updating payload for {company_name}: {e}")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "error",
                "error": str(e)
            }

    @task
    def log_daily_update_results(all_results: list, chunking_results: list, payload_results: list, **context):
        """Log daily update results to GCS bucket"""
        from gcs_utils import save_json_to_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Resolve LazyXComAccess objects to actual lists/dicts for JSON serialization
        try:
            if hasattr(chunking_results, '__iter__') and not isinstance(chunking_results, (list, dict, str)):
                chunking_results = list(chunking_results)
        except Exception as e:
            logger.warning(f"⚠️  Could not resolve LazyXComAccess for chunking_results: {e}")
            chunking_results = [r for r in chunking_results] if chunking_results else []
        
        # Calculate statistics
        companies_with_changes = len([r for r in all_results if r.get('has_changes', False)])
        total_changed_pages = sum(len(r.get('changed_pages', [])) for r in all_results)
        total_files = sum(r.get('files_uploaded', 0) for r in all_results)
        
        chunking_successful = len([r for r in chunking_results if r.get('status') == 'success'])
        chunking_failed = len([r for r in chunking_results if r.get('status') == 'error'])
        chunking_skipped = len([r for r in chunking_results if r.get('status') == 'skipped'])
        total_chunks = sum(r.get('chunks_stored', 0) for r in chunking_results)
        
        payload_updated = len([r for r in payload_results if r.get('status') == 'success'])
        payload_skipped = len([r for r in payload_results if r.get('status') == 'skipped'])
        payload_failed = len([r for r in payload_results if r.get('status') == 'error'])
        
        total_events = sum(r.get('events_count', 0) for r in payload_results if r.get('status') == 'success')
        total_products = sum(r.get('products_count', 0) for r in payload_results if r.get('status') == 'success')
        total_leadership = sum(r.get('leadership_count', 0) for r in payload_results if r.get('status') == 'success')
        
        summary = {
            "update_date": datetime.now().isoformat(),
            "date": today,
            "version": "v2-daily-update",
            "folder_structure": f"{V2_MASTER_FOLDER}/",
            "dag_run_id": context.get('dag_run').run_id if context.get('dag_run') else None,
            "total_companies": len(all_results),
            "scraping": {
                "companies_with_changes": companies_with_changes,
                "total_changed_pages": total_changed_pages,
                "total_files_uploaded": total_files
            },
            "chunking": {
                "successful": chunking_successful,
                "failed": chunking_failed,
                "skipped": chunking_skipped,
                "total_chunks_stored": total_chunks
            },
            "extraction": {
                "payloads_updated": payload_updated,
                "payloads_skipped": payload_skipped,
                "payloads_failed": payload_failed,
                "total_events": total_events,
                "total_products": total_products,
                "total_leadership": total_leadership
            },
            "companies": [
                {
                    "company_id": r.get('company_id'),
                    "company_name": r.get('company_name'),
                    "has_changes": r.get('has_changes', False),
                    "changed_pages": r.get('changed_pages', []),
                    "files_uploaded": r.get('files_uploaded', 0),
                    "payload_status": next((p.get('status') for p in payload_results if p.get('company_id') == r.get('company_id')), 'unknown')
                }
                for r in all_results
            ]
        }
        
        # Save to GCS bucket
        results_path = f"{RESULTS_PREFIX}daily_update_{today}.json"
        
        success = save_json_to_gcs(bucket_name, summary, results_path)
        
        if success:
            logger.info(f"✅ Daily update results saved to gs://{bucket_name}/{results_path}")
            logger.info(f"   Summary: {companies_with_changes} companies with changes, {payload_updated} payloads updated")
            logger.info(f"   Changed pages: {total_changed_pages}, Files: {total_files}")
            logger.info(f"   Chunking: {chunking_successful}/{len(chunking_results)} successful, {total_chunks} chunks stored")
        else:
            logger.error(f"❌ Failed to save daily update results to GCS")
        
        return summary

    # Task flow - Pipeline pattern: each company processes independently
    companies = load_company_list()
    
    # Step 1: Check for changes and scrape (parallel)
    scrape_results = check_and_scrape_changes.expand(company=companies)
    
    # Step 2: Chunk changed pages and update Pinecone (parallel, per-company)
    chunking_results = chunk_changed_pages.expand(
        company=companies,
        scrape_result=scrape_results
    )
    
    # Step 3: Update payloads only for changed companies (parallel, per-company)
    payload_results = update_payload_if_changed.expand(
        company=companies,
        scrape_result=scrape_results
    )
    
    # Step 4: Log results to bucket (depends on all)
    final_summary = log_daily_update_results(scrape_results, chunking_results, payload_results)