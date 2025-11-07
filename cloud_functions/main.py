"""
Cloud Functions Entry Point for Forbes AI 50 Scraping

This module contains the main entry points for Cloud Functions:
- full_ingest: Full-load scraping for all companies
- daily_refresh: Daily refresh of key pages
"""

import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add src directory to path for imports
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from functions_framework import http
from flask import jsonify

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Import our modules with error handling
try:
    from gcs_utils import (
        load_json_from_gcs,
        upload_directory_to_gcs,
        save_json_to_gcs,
        check_gcs_file_exists,
        list_gcs_files,
        list_txt_files_from_gcs,
        download_text_from_gcs
    )
    from scraper import scrape_company
    logger.info("Successfully imported scraper modules")
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    logger.error(f"Python path: {sys.path}")
    logger.error(f"Looking for src at: {src_path}")
    logger.error(traceback.format_exc())
    raise

# Configuration from environment variables
PROJECT_ID = os.environ.get('GCP_PROJECT', 'project-orbit123')
BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'project-orbit-data-12345')
REGION = os.environ.get('REGION', 'us-central1')
SEED_FILE_PATH = 'seed/forbes_ai50_seed.json'
RAW_DATA_PREFIX = 'raw/'
RESULTS_PREFIX = 'scraping_results/'


@http
def full_ingest(request):
    """
    Cloud Function: Full-load ingestion for all Forbes AI 50 companies.
    
    Triggered by: HTTP request (manual or Cloud Scheduler)
    Process:
    1. Load companies from GCS seed file
    2. Create Cloud Tasks for each company (parallel processing)
    3. Wait for all tasks to complete (or return immediately)
    4. Aggregate and save results
    
    Args:
        request: Flask request object
        
    Returns:
        JSON response with status
    """
    if request.method != 'POST':
        return jsonify({'error': 'Only POST method allowed'}), 405
    
    try:
        logger.info("Starting full-load ingestion")
        
        # Load companies
        companies_data = load_json_from_gcs(BUCKET_NAME, SEED_FILE_PATH)
        if not companies_data:
            return jsonify({'error': 'Failed to load seed file'}), 500
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company['website']).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0]
        
        logger.info(f"Loaded {len(companies_data)} companies")
        
        # Process companies sequentially
        results = []
        
        for company in companies_data:
            try:
                result = scrape_and_upload_company(
                    company=company,
                    run_folder='initial_pull',
                    scrape_blog_posts=True,
                    max_blog_posts=20
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error scraping {company.get('company_name')}: {e}")
                results.append({
                    'company_name': company.get('company_name'),
                    'company_id': company.get('company_id'),
                    'status': 'error',
                    'error': str(e)
                })
        
        # Aggregate results
        successful = [r for r in results if r.get('status') == 'success']
        failed = [r for r in results if r.get('status') != 'success']
        total_pages = sum(r.get('pages_scraped', 0) for r in results)
        total_files = sum(r.get('files_uploaded', 0) for r in results)
        
        summary = {
            'scrape_date': datetime.now().isoformat(),
            'scraper_version': '4.0-cloud-functions',
            'run_folder': 'initial_pull',
            'total_companies': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'total_pages_posts': total_pages,
            'total_files_uploaded': total_files,
            'companies': results
        }
        
        # Save results to GCS
        results_path = f"{RESULTS_PREFIX}scraping_results_initial_pull.json"
        save_json_to_gcs(BUCKET_NAME, summary, results_path)
        
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(successful)}/{len(results)} companies',
            'summary': {
                'successful': len(successful),
                'failed': len(failed),
                'total_pages': total_pages,
                'total_files': total_files
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in full_ingest: {e}", exc_info=True)
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@http
def daily_refresh(request):
    """
    Cloud Function: Daily refresh of key pages for all companies.
    
    Triggered by: Cloud Scheduler (cron: 0 3 * * *)
    Process:
    1. Load companies from GCS
    2. Check for changes in key pages (homepage, about, careers, blog)
    3. Re-scrape only changed pages
    4. Upload to dated folder
    
    Args:
        request: Flask request object
        
    Returns:
        JSON response with status
    """
    if request.method != 'POST':
        return jsonify({'error': 'Only POST method allowed'}), 405
    
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        run_folder = f'daily_{today}'
        
        logger.info(f"Starting daily refresh for {today}")
        
        # Load companies
        companies_data = load_json_from_gcs(BUCKET_NAME, SEED_FILE_PATH)
        if not companies_data:
            return jsonify({'error': 'Failed to load seed file'}), 500
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company['website']).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0]
        
        results = []
        KEY_PAGES = ["homepage", "about", "careers", "blog"]
        
        for company in companies_data:
            try:
                # Check for changes
                changed_pages = check_changes(company, KEY_PAGES)
                
                if changed_pages or not check_gcs_file_exists(
                    BUCKET_NAME,
                    f"{RAW_DATA_PREFIX}{company['company_id']}/initial_pull/metadata.json"
                ):
                    # Scrape if changed or no previous data
                    result = scrape_and_upload_company(
                        company=company,
                        run_folder=run_folder,
                        scrape_blog_posts=True,
                        max_blog_posts=10
                    )
                    result['changed_pages'] = changed_pages
                else:
                    result = {
                        'company_name': company.get('company_name'),
                        'company_id': company.get('company_id'),
                        'status': 'skipped',
                        'message': 'No changes detected'
                    }
                
                results.append(result)
            except Exception as e:
                logger.error(f"Error in daily refresh for {company.get('company_name')}: {e}")
                results.append({
                    'company_name': company.get('company_name'),
                    'company_id': company.get('company_id'),
                    'status': 'error',
                    'error': str(e)
                })
        
        # Aggregate results
        successful = [r for r in results if r.get('status') == 'success']
        changed = [r for r in results if r.get('changed_pages')]
        
        summary = {
            'scrape_date': today,
            'scraper_version': '4.0-cloud-functions',
            'run_folder': run_folder,
            'total_companies': len(results),
            'successful': len(successful),
            'companies_with_changes': len(changed),
            'companies': results
        }
        
        # Save results
        results_path = f"{RESULTS_PREFIX}scraping_results_{run_folder}.json"
        save_json_to_gcs(BUCKET_NAME, summary, results_path)
        
        return jsonify({
            'status': 'success',
            'message': f'Daily refresh completed for {today}',
            'summary': {
                'successful': len(successful),
                'changed': len(changed),
                'total': len(results)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in daily_refresh: {e}", exc_info=True)
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


def scrape_and_upload_company(company: dict, run_folder: str, scrape_blog_posts: bool = True, max_blog_posts: int = 20) -> dict:
    """
    Helper function to scrape a company and upload to GCS.
    
    Args:
        company: Company dictionary
        run_folder: Folder name for this run (e.g., 'initial_pull' or 'daily_YYYY-MM-DD')
        scrape_blog_posts: Whether to scrape blog posts
        max_blog_posts: Maximum blog posts to scrape
        
    Returns:
        dict: Scraping result
    """
    import tempfile
    import shutil
    
    company_id = company.get('company_id')
    company_name = company.get('company_name', 'Unknown')
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix=f'scrape_{company_id}_'))
    
    try:
        # Scrape company
        result = scrape_company(
            company=company,
            output_dir=temp_dir,
            run_folder=run_folder,
            force_playwright=False,
            respect_robots=False,
            scrape_blog_posts=scrape_blog_posts,
            max_blog_posts=max_blog_posts
        )
        
        # Upload to GCS
        company_gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
        uploaded_count = upload_directory_to_gcs(
            bucket_name=BUCKET_NAME,
            local_dir_path=str(temp_dir / company_id / run_folder),
            gcs_prefix=company_gcs_prefix
        )
        
        result['files_uploaded'] = uploaded_count
        result['gcs_prefix'] = company_gcs_prefix
        
        return result
    finally:
        # Clean up
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def check_changes(company: dict, key_pages: list) -> list:
    """
    Check if key pages have changed by comparing content hashes.
    
    Args:
        company: Company dictionary
        key_pages: List of page types to check
        
    Returns:
        list: List of page types that have changed
    """
    # Placeholder: always return empty (no changes detected)
    # Full implementation would compare content hashes from previous runs
    return []


@http
def scrape_and_index(request):
    """
    Cloud Function: Scrape companies AND index them in Pinecone in one go.
    Supports batch processing to avoid timeout issues.
    
    Triggered by: HTTP request (manual or Cloud Scheduler)
    Query Parameters:
        - start: Start index (default: 0)
        - end: End index (default: None, processes all)
        - batch_size: Number of companies per batch (default: 3)
        - batch_index: Batch number (alternative to start/end)
    
    Process:
    1. Load companies from GCS seed file
    2. Determine batch range from parameters
    3. Scrape each company → Get HTML + TXT files → Upload to GCS
    4. Download TXT files from GCS → Chunk → Create embeddings → Store in Pinecone
    5. Aggregate and save results
    
    Args:
        request: Flask request object
        
    Returns:
        JSON response with status
    """
    if request.method != 'POST':
        return jsonify({'error': 'Only POST method allowed'}), 405
    
    try:
        # Get batch parameters from query string or request body
        start = int(request.args.get('start', 0))
        end = request.args.get('end')
        batch_size = int(request.args.get('batch_size', 3))
        batch_index = request.args.get('batch_index')
        
        # If batch_index is provided, calculate start position
        if batch_index is not None:
            start = int(batch_index) * batch_size
        
        # Calculate end if batch_size is provided and end is not explicitly set
        if end is None:
            end = start + batch_size
        else:
            end = int(end)
        
        logger.info(f"Starting scrape-and-index process (batch: start={start}, end={end}, batch_size={batch_size})")
        
        # Load companies from GCS
        companies_data = load_json_from_gcs(BUCKET_NAME, SEED_FILE_PATH)
        if not companies_data:
            return jsonify({'error': 'Failed to load seed file'}), 500
        
        total_companies = len(companies_data)
        
        # Validate batch range
        if start < 0 or start >= total_companies:
            return jsonify({'error': f'Invalid start index: {start}. Total companies: {total_companies}'}), 400
        
        if end > total_companies:
            end = total_companies  # Adjust end to not exceed total companies
        
        if start >= end:
            return jsonify({'error': f'Invalid range: start ({start}) >= end ({end})'}), 400
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company['website']).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0]
        
        # Slice companies for batch processing
        companies_batch = companies_data[start:end]
        batch_number = start // batch_size + 1 if batch_size > 0 else 1
        
        logger.info(f"Loaded {total_companies} total companies")
        logger.info(f"Processing batch {batch_number}: companies {start} to {end-1} ({len(companies_batch)} companies)")
        
        # Import chunking services
        try:
            from services.chunker import Chunker
            from services.embeddings import Embeddings, PineconeStorage
            logger.info("Successfully imported chunking services")
        except ImportError as e:
            logger.error(f"Failed to import chunking services: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to import chunking services: {str(e)}'}), 500
        
        # Initialize chunking services
        try:
            chunker = Chunker(chunk_size=1000)
            embeddings_client = Embeddings()
            pinecone_storage = PineconeStorage()
            logger.info("Successfully initialized chunking services")
        except Exception as e:
            logger.error(f"Failed to initialize chunking services: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to initialize chunking services: {str(e)}'}), 500
        
        # Process each company in the batch
        results = []
        total_chunks_created = 0
        
        for company in companies_batch:
            company_id = company.get('company_id')
            company_name = company.get('company_name', 'Unknown')
            
            try:
                logger.info(f"Processing {company_name} ({company_id})...")
                
                # Step 1: Scrape company and upload to GCS
                logger.info(f"  Scraping {company_name}...")
                scrape_result = scrape_and_upload_company(
                    company=company,
                    run_folder='initial_pull',
                    scrape_blog_posts=True,
                    max_blog_posts=20
                )
                
                if scrape_result.get('status') != 'success':
                    results.append({
                        'company_name': company_name,
                        'company_id': company_id,
                        'status': 'scrape_failed',
                        'error': scrape_result.get('error', 'Unknown error')
                    })
                    continue
                
                # Step 2: List TXT files from GCS
                logger.info(f"  Listing TXT files for {company_name}...")
                txt_files = list_txt_files_from_gcs(
                    bucket_name=BUCKET_NAME,
                    company_id=company_id,
                    run_folder='initial_pull'
                )
                
                if not txt_files:
                    logger.warning(f"  No TXT files found for {company_name}")
                    results.append({
                        'company_name': company_name,
                        'company_id': company_id,
                        'status': 'success',
                        'pages_scraped': scrape_result.get('pages_scraped', 0),
                        'files_uploaded': scrape_result.get('files_uploaded', 0),
                        'chunks_created': 0,
                        'warning': 'No TXT files found for chunking'
                    })
                    continue
                
                # Step 3: Process each TXT file
                logger.info(f"  Processing {len(txt_files)} TXT files for {company_name}...")
                chunks_created = 0
                
                for txt_file_path in txt_files:
                    try:
                        # Download TXT file content from GCS
                        txt_content = download_text_from_gcs(
                            bucket_name=BUCKET_NAME,
                            gcs_path=txt_file_path
                        )
                        
                        if not txt_content or len(txt_content.strip()) == 0:
                            logger.warning(f"  Empty or missing content for {txt_file_path}")
                            continue
                        
                        # Chunk the text
                        chunks = chunker.chunk_text(txt_content)
                        
                        # Get filename from GCS path
                        filename = txt_file_path.split('/')[-1]
                        source_path = f"{company_id}/{filename}"
                        
                        # Create embeddings and store in Pinecone
                        for chunk in chunks:
                            if not chunk.strip():
                                continue
                            
                            try:
                                embedding = embeddings_client.embed_text(chunk)
                                pinecone_storage.store_embedding(
                                    text=chunk,
                                    embedding=embedding,
                                    source_path=source_path
                                )
                                chunks_created += 1
                            except Exception as e:
                                logger.error(f"  Error processing chunk for {txt_file_path}: {e}")
                                continue
                        
                    except Exception as e:
                        logger.error(f"  Error processing TXT file {txt_file_path}: {e}")
                        logger.error(traceback.format_exc())
                        continue
                
                logger.info(f"  ✅ Completed {company_name}: {chunks_created} chunks created")
                
                results.append({
                    'company_name': company_name,
                    'company_id': company_id,
                    'status': 'success',
                    'pages_scraped': scrape_result.get('pages_scraped', 0),
                    'files_uploaded': scrape_result.get('files_uploaded', 0),
                    'txt_files_processed': len(txt_files),
                    'chunks_created': chunks_created
                })
                
                total_chunks_created += chunks_created
                
            except Exception as e:
                logger.error(f"Error processing {company_name}: {e}")
                logger.error(traceback.format_exc())
                results.append({
                    'company_name': company_name,
                    'company_id': company_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Aggregate results
        successful = [r for r in results if r.get('status') == 'success']
        failed = [r for r in results if r.get('status') != 'success']
        
        summary = {
            'scrape_date': datetime.now().isoformat(),
            'scraper_version': '5.0-scrape-and-index-batch',
            'run_folder': 'initial_pull',
            'batch_info': {
                'batch_number': batch_number,
                'batch_start': start,
                'batch_end': end,
                'batch_size': len(companies_batch),
                'total_companies': total_companies
            },
            'total_companies': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'total_chunks_indexed': total_chunks_created,
            'companies': results
        }
        
        # Save results to GCS with batch number
        results_path = f"{RESULTS_PREFIX}scraping_and_indexing_results_batch_{batch_number}.json"
        save_json_to_gcs(BUCKET_NAME, summary, results_path)
        
        logger.info(f"Batch {batch_number} completed: {len(successful)}/{len(results)} companies successful, {total_chunks_created} chunks indexed")
        
        return jsonify({
            'status': 'success',
            'message': f'Batch {batch_number} completed: Processed {len(successful)}/{len(results)} companies',
            'batch_info': {
                'batch_number': batch_number,
                'batch_start': start,
                'batch_end': end,
                'total_companies': total_companies
            },
            'summary': {
                'successful': len(successful),
                'failed': len(failed),
                'total_chunks_indexed': total_chunks_created,
                'total_companies_in_batch': len(results)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in scrape_and_index: {e}", exc_info=True)
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@http
def structured_extraction(request):
    """
    Cloud Function: Extract structured data from scraped HTML/TXT files.
    Supports batch processing to avoid timeout issues.
    
    Triggered by: HTTP request (manual or Cloud Scheduler)
    Query Parameters:
        - start: Start index (default: 0)
        - end: End index (default: None, processes all)
        - batch_size: Number of companies per batch (default: 3)
        - batch_index: Batch number (alternative to start/end)
    
    Process:
    1. Load companies from GCS seed file
    2. Determine batch range from parameters
    3. For each company:
       - Load scraped files from GCS (raw/{company_id}/initial_pull/)
       - Run structured extraction using Pydantic + Instructor
       - Save structured data to structured/{company_id}.json
       - Save payload to payloads/{company_id}.json
    4. Aggregate and save results
    
    Args:
        request: Flask request object
        
    Returns:
        JSON response with status
    """
    if request.method != 'POST':
        return jsonify({'error': 'Only POST method allowed'}), 405
    
    try:
        # Get batch parameters from query string or request body
        start = int(request.args.get('start', 0))
        end = request.args.get('end')
        batch_size = int(request.args.get('batch_size', 3))
        batch_index = request.args.get('batch_index')
        
        # If batch_index is provided, calculate start position
        if batch_index is not None:
            start = int(batch_index) * batch_size
        
        # Calculate end if batch_size is provided and end is not explicitly set
        if end is None:
            end = start + batch_size
        else:
            end = int(end)
        
        logger.info(f"Starting structured extraction process (batch: start={start}, end={end}, batch_size={batch_size})")
        
        # Load companies from GCS
        companies_data = load_json_from_gcs(BUCKET_NAME, SEED_FILE_PATH)
        if not companies_data:
            return jsonify({'error': 'Failed to load seed file'}), 500
        
        total_companies = len(companies_data)
        
        # Validate batch range
        if start < 0 or start >= total_companies:
            return jsonify({'error': f'Invalid start index: {start}. Total companies: {total_companies}'}), 400
        
        if end > total_companies:
            end = total_companies
        
        if start >= end:
            return jsonify({'error': f'Invalid range: start ({start}) >= end ({end})'}), 400
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company['website']).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0]
        
        # Slice companies for batch processing
        companies_batch = companies_data[start:end]
        batch_number = start // batch_size + 1 if batch_size > 0 else 1
        
        logger.info(f"Loaded {total_companies} total companies")
        logger.info(f"Processing batch {batch_number}: companies {start} to {end-1} ({len(companies_batch)} companies)")
        
        # Import structured extraction module
        try:
            from structured_extraction import extract_company_payload
            logger.info("Successfully imported structured extraction module")
        except ImportError as e:
            logger.error(f"Failed to import structured extraction module: {e}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'Failed to import structured extraction module: {str(e)}'}), 500
        
        # Process each company in the batch
        results = []
        total_events = 0
        total_products = 0
        total_leadership = 0
        
        for company in companies_batch:
            company_id = company.get('company_id')
            company_name = company.get('company_name', 'Unknown')
            
            try:
                logger.info(f"Processing {company_name} ({company_id})...")
                
                # Run structured extraction
                payload = extract_company_payload(company_id)
                
                # Count extracted entities
                events_count = len(payload.events)
                products_count = len(payload.products)
                leadership_count = len(payload.leadership)
                
                total_events += events_count
                total_products += products_count
                total_leadership += leadership_count
                
                logger.info(f"  ✅ Completed {company_name}: {events_count} events, {products_count} products, {leadership_count} leadership")
                
                results.append({
                    'company_name': company_name,
                    'company_id': company_id,
                    'status': 'success',
                    'events_extracted': events_count,
                    'products_extracted': products_count,
                    'leadership_extracted': leadership_count,
                    'structured_data_path': f"structured/{company_id}.json",
                    'payload_path': f"payloads/{company_id}.json"
                })
                
            except Exception as e:
                logger.error(f"Error processing {company_name}: {e}")
                logger.error(traceback.format_exc())
                results.append({
                    'company_name': company_name,
                    'company_id': company_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Aggregate results
        successful = [r for r in results if r.get('status') == 'success']
        failed = [r for r in results if r.get('status') != 'success']
        
        summary = {
            'extraction_date': datetime.now().isoformat(),
            'extractor_version': '1.0-structured-extraction-batch',
            'batch_info': {
                'batch_number': batch_number,
                'batch_start': start,
                'batch_end': end,
                'batch_size': len(companies_batch),
                'total_companies': total_companies
            },
            'total_companies': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'total_events_extracted': total_events,
            'total_products_extracted': total_products,
            'total_leadership_extracted': total_leadership,
            'companies': results
        }
        
        # Save results to GCS with batch number
        results_path = f"{RESULTS_PREFIX}structured_extraction_results_batch_{batch_number}.json"
        save_json_to_gcs(BUCKET_NAME, summary, results_path)
        
        logger.info(f"Batch {batch_number} completed: {len(successful)}/{len(results)} companies successful")
        
        return jsonify({
            'status': 'success',
            'message': f'Batch {batch_number} completed: Processed {len(successful)}/{len(results)} companies',
            'batch_info': {
                'batch_number': batch_number,
                'batch_start': start,
                'batch_end': end,
                'total_companies': total_companies
            },
            'summary': {
                'successful': len(successful),
                'failed': len(failed),
                'total_events': total_events,
                'total_products': total_products,
                'total_leadership': total_leadership,
                'total_companies_in_batch': len(results)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in structured_extraction: {e}", exc_info=True)
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


# Entry points for Cloud Functions
def main_full_ingest(request):
    """Entry point for full-load function"""
    return full_ingest(request)


def main_daily_refresh(request):
    """Entry point for daily refresh function"""
    return daily_refresh(request)


def main_scrape_and_index(request):
    """Entry point for scrape-and-index function"""
    return scrape_and_index(request)


def main_structured_extraction(request):
    """Entry point for structured extraction function"""
    return structured_extraction(request)

