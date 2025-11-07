"""
Lab 3: Daily Refresh Airflow DAG for Forbes AI 50

This DAG performs daily refresh of key pages for all companies:
1. Load company list from GCS
2. For each company, check if key pages changed (using content hash)
3. Re-scrape only changed pages (About, Careers, Blog)
4. Upload results to dated folder in GCS

Schedule: 0 3 * * * (3 AM daily)
Key pages: homepage, about, careers, blog
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil
import json
import logging

from airflow import DAG
from airflow.decorators import task
from airflow.operators.python import PythonOperator

# Import scraper functions
# Cloud Composer uses /home/airflow/gcs/plugins/ for plugins
import sys
import os

# Try multiple import paths for Cloud Composer
possible_paths = [
    '/home/airflow/gcs/plugins',
    '/home/airflow/gcs/dags',
    os.path.join(os.path.dirname(__file__), '..'),
]

for path in possible_paths:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from src.scraper import scrape_company, load_companies, compute_content_hash
    from src.gcs_utils import (
        load_json_from_gcs,
        upload_directory_to_gcs,
        save_json_to_gcs,
        check_gcs_file_exists,
        list_gcs_files
    )
except ImportError as e:
    # If still fails, try direct import
    try:
        import scraper
        scrape_company = scraper.scrape_company
        load_companies = scraper.load_companies
        compute_content_hash = scraper.compute_content_hash
    except:
        raise ImportError(f"Could not import scraper modules: {e}")

logger = logging.getLogger(__name__)

# Get bucket name from Airflow Variable
try:
    from airflow.models import Variable
    GCS_BUCKET_NAME = Variable.get("GCS_BUCKET_NAME", default_var="")
except Exception:
    GCS_BUCKET_NAME = ""

# Default values
DEFAULT_BUCKET = "project-orbit-data"
SEED_FILE_PATH = "seed/forbes_ai50_seed.json"
RAW_DATA_PREFIX = "raw/"
RESULTS_PREFIX = "scraping_results/"

# Key pages to check for changes (daily refresh)
KEY_PAGES = ["homepage", "about", "careers", "blog"]

# DAG configuration
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': 300,  # 5 minutes
}

with DAG(
    'ai50_daily_refresh_dag',
    default_args=default_args,
    description='Daily refresh of key pages for Forbes AI 50 companies',
    schedule_interval='0 3 * * *',  # 3 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['ai50', 'scraping', 'daily-refresh'],
) as dag:

    @task
    def load_company_list(**context):
        """
        Load company list from GCS seed file.
        
        Returns:
            List[dict]: List of company dictionaries
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        
        logger.info(f"Loading companies from GCS")
        
        companies_data = load_json_from_gcs(bucket_name, SEED_FILE_PATH)
        
        if not companies_data:
            raise ValueError(f"Failed to load seed file from GCS")
        
        # Add company_id if not present
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company['website']).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0]
        
        logger.info(f"Loaded {len(companies_data)} companies")
        return companies_data

    @task
    def check_and_scrape_changes(company: dict, **context):
        """
        Check if key pages changed and re-scrape if needed.
        This is a mapped task - one instance per company.
        
        Args:
            company: Company dictionary
            
        Returns:
            dict: Scraping result with change detection info
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        # Get today's date for folder name
        today = datetime.now().strftime('%Y-%m-%d')
        run_folder = f"daily_{today}"
        
        logger.info(f"Checking changes for {company_name} ({company_id})")
        
        # Try to load previous metadata to compare hashes
        previous_metadata_path = f"{RAW_DATA_PREFIX}{company_id}/initial_pull/metadata.json"
        previous_hashes = {}
        
        try:
            # Try to get initial_pull metadata first
            if check_gcs_file_exists(bucket_name, previous_metadata_path):
                prev_metadata = load_json_from_gcs(bucket_name, previous_metadata_path)
                if prev_metadata and 'pages' in prev_metadata:
                    for page_info in prev_metadata['pages']:
                        if page_info.get('found') and page_info.get('content_hash'):
                            previous_hashes[page_info['page_type']] = page_info['content_hash']
            
            # Also check latest daily run
            daily_runs = list_gcs_files(bucket_name, f"{RAW_DATA_PREFIX}{company_id}/daily_")
            if daily_runs:
                # Get most recent daily run
                daily_runs.sort(reverse=True)
                latest_daily = daily_runs[0] if daily_runs else None
                if latest_daily:
                    latest_metadata_path = f"{latest_daily.rstrip('/')}/metadata.json"
                    if check_gcs_file_exists(bucket_name, latest_metadata_path):
                        latest_metadata = load_json_from_gcs(bucket_name, latest_metadata_path)
                        if latest_metadata and 'pages' in latest_metadata:
                            for page_info in latest_metadata['pages']:
                                if page_info.get('found') and page_info.get('content_hash'):
                                    previous_hashes[page_info['page_type']] = page_info['content_hash']
            
        except Exception as e:
            logger.warning(f"Could not load previous metadata for {company_name}: {e}")
            # If no previous data, we'll scrape everything
        
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix=f"daily_{company_id}_"))
        
        try:
            # Scrape company (only key pages for daily refresh)
            # Note: The scraper will scrape all pages, but we can filter results
            result = scrape_company(
                company=company,
                output_dir=temp_dir,
                run_folder=run_folder,
                force_playwright=False,
                respect_robots=False,
                scrape_blog_posts=True,
                max_blog_posts=10  # Fewer blog posts for daily refresh
            )
            
            # Check which pages actually changed
            new_metadata_path = temp_dir / company_id / run_folder / "metadata.json"
            changed_pages = []
            
            if new_metadata_path.exists():
                new_metadata = json.loads(new_metadata_path.read_text())
                if 'pages' in new_metadata:
                    for page_info in new_metadata['pages']:
                        page_type = page_info.get('page_type')
                        new_hash = page_info.get('content_hash')
                        
                        if page_type in KEY_PAGES:
                            old_hash = previous_hashes.get(page_type)
                            if old_hash and new_hash:
                                if old_hash != new_hash:
                                    changed_pages.append(page_type)
                                    logger.info(f"  {page_type}: Changed (hash mismatch)")
                                else:
                                    logger.debug(f"  {page_type}: Unchanged")
                            elif new_hash:
                                # New page found
                                changed_pages.append(page_type)
                                logger.info(f"  {page_type}: New page found")
            
            # Upload to GCS
            company_gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
            uploaded_count = upload_directory_to_gcs(
                bucket_name=bucket_name,
                local_dir_path=str(temp_dir / company_id / run_folder),
                gcs_prefix=company_gcs_prefix
            )
            
            result['files_uploaded'] = uploaded_count
            result['gcs_prefix'] = company_gcs_prefix
            result['changed_pages'] = changed_pages
            result['pages_checked'] = KEY_PAGES
            result['has_previous_data'] = len(previous_hashes) > 0
            
            logger.info(f"  {company_name}: {len(changed_pages)} pages changed, {uploaded_count} files uploaded")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in daily refresh for {company_name}: {e}", exc_info=True)
            return {
                "company_name": company_name,
                "company_id": company_id,
                "status": "error",
                "error": str(e),
                "pages_scraped": 0,
                "changed_pages": [],
                "run_folder": run_folder
            }
        finally:
            # Clean up
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @task
    def log_daily_results(all_results: list, **context):
        """
        Log and store daily refresh results.
        
        Args:
            all_results: List of results from all company tasks
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Aggregate results
        successful = [r for r in all_results if r.get('status') == 'success']
        failed = [r for r in all_results if r.get('status') != 'success']
        total_pages = sum(r.get('pages_scraped', 0) for r in all_results)
        total_files = sum(r.get('files_uploaded', 0) for r in all_results)
        total_changed = sum(len(r.get('changed_pages', [])) for r in all_results)
        
        summary = {
            "scrape_date": datetime.now().isoformat(),
            "scraper_version": "3.0-airflow",
            "run_folder": f"daily_{today}",
            "total_companies": len(all_results),
            "successful": len(successful),
            "failed": len(failed),
            "total_pages_posts": total_pages,
            "total_files_uploaded": total_files,
            "total_pages_changed": total_changed,
            "companies_with_changes": len([r for r in successful if r.get('changed_pages')]),
            "companies": all_results
        }
        
        # Save results to GCS
        results_path = f"{RESULTS_PREFIX}scraping_results_daily_{today}.json"
        success = save_json_to_gcs(bucket_name, summary, results_path)
        
        if success:
            logger.info(f"Daily results saved to gs://{bucket_name}/{results_path}")
            logger.info(f"Summary: {len(successful)}/{len(all_results)} successful, "
                       f"{total_changed} pages changed, {total_files} files uploaded")
        else:
            logger.error("Failed to save daily results to GCS")
        
        # Log failed companies
        if failed:
            logger.warning(f"Failed companies ({len(failed)}):")
            for r in failed:
                logger.warning(f"  - {r.get('company_name')}: {r.get('error', 'Unknown error')}")
        
        return summary

    # Define task flow
    companies = load_company_list()
    
    # Expand: Create one task per company
    scrape_results = check_and_scrape_changes.expand(company=companies)
    
    # Log results
    daily_summary = log_daily_results(scrape_results)

