"""
Lab 2: Full-Load Airflow DAG for Forbes AI 50

This DAG performs a one-time full ingestion of all Forbes AI 50 companies:
1. Load company list from GCS seed file
2. Scrape all pages for each company (mapped task)
3. Upload scraped data to GCS

Schedule: @once (runs once manually or on first deployment)
"""

from datetime import datetime
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
    from src.scraper import scrape_company, load_companies
    from src.gcs_utils import (
        load_json_from_gcs,
        upload_directory_to_gcs,
        save_json_to_gcs
    )
except ImportError as e:
    # If still fails, try direct import
    try:
        import scraper
        scrape_company = scraper.scrape_company
        load_companies = scraper.load_companies
    except:
        raise ImportError(f"Could not import scraper modules: {e}")

logger = logging.getLogger(__name__)

# Get bucket name from Airflow Variable (set via UI or gcloud command)
try:
    from airflow.models import Variable
    GCS_BUCKET_NAME = Variable.get("GCS_BUCKET_NAME", default_var="")
except Exception:
    GCS_BUCKET_NAME = ""

# Default values if variable not set
DEFAULT_BUCKET = "project-orbit-data"
SEED_FILE_PATH = "seed/forbes_ai50_seed.json"
RAW_DATA_PREFIX = "raw/"
RESULTS_PREFIX = "scraping_results/"

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
    'ai50_full_ingest_dag',
    default_args=default_args,
    description='Full-load ingestion for all Forbes AI 50 companies',
    schedule_interval=None,  # @once equivalent - manual trigger
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['ai50', 'scraping', 'full-load'],
) as dag:

    @task
    def load_company_list(**context):
        """
        Load company list from GCS seed file.
        
        Returns:
            List[dict]: List of company dictionaries
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        seed_path = f"gs://{bucket_name}/{SEED_FILE_PATH}"
        
        logger.info(f"Loading companies from {seed_path}")
        
        # Download seed file to temp location
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Load from GCS
            companies_data = load_json_from_gcs(bucket_name, SEED_FILE_PATH)
            
            if not companies_data:
                raise ValueError(f"Failed to load seed file from {seed_path}")
            
            # Add company_id if not present
            from urllib.parse import urlparse
            for company in companies_data:
                if 'company_id' not in company:
                    domain = urlparse(company['website']).netloc
                    company['company_id'] = domain.replace("www.", "").split(".")[0]
            
            logger.info(f"Loaded {len(companies_data)} companies")
            return companies_data
            
        except Exception as e:
            logger.error(f"Error loading company list: {e}")
            raise

    @task
    def scrape_company_pages(company: dict, **context):
        """
        Scrape all pages for a single company.
        This is a mapped task - one instance per company.
        
        Args:
            company: Company dictionary with name, website, company_id
            
        Returns:
            dict: Scraping result with status and statistics
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        logger.info(f"Scraping {company_name} ({company_id})")
        
        # Create temporary directory for scraping
        temp_dir = Path(tempfile.mkdtemp(prefix=f"scrape_{company_id}_"))
        run_folder = "initial_pull"
        
        try:
            # Scrape company
            result = scrape_company(
                company=company,
                output_dir=temp_dir,
                run_folder=run_folder,
                force_playwright=False,
                respect_robots=False,  # Bypass for academic use
                scrape_blog_posts=True,
                max_blog_posts=20
            )
            
            # Upload scraped data to GCS
            company_gcs_prefix = f"{RAW_DATA_PREFIX}{company_id}/{run_folder}/"
            uploaded_count = upload_directory_to_gcs(
                bucket_name=bucket_name,
                local_dir_path=str(temp_dir / company_id / run_folder),
                gcs_prefix=company_gcs_prefix
            )
            
            logger.info(f"Uploaded {uploaded_count} files for {company_name}")
            
            # Update result with upload info
            result['files_uploaded'] = uploaded_count
            result['gcs_prefix'] = company_gcs_prefix
            
            return result
            
        except Exception as e:
            logger.error(f"Error scraping {company_name}: {e}", exc_info=True)
            return {
                "company_name": company_name,
                "company_id": company_id,
                "status": "error",
                "error": str(e),
                "pages_scraped": 0,
                "pages_total": 12
            }
        finally:
            # Clean up temporary directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @task
    def store_results(all_results: list, **context):
        """
        Store aggregation results to GCS.
        
        Args:
            all_results: List of results from all company scraping tasks
        """
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        
        # Aggregate results
        successful = [r for r in all_results if r.get('status') == 'success']
        failed = [r for r in all_results if r.get('status') != 'success']
        total_pages = sum(r.get('pages_scraped', 0) for r in all_results)
        total_files = sum(r.get('files_uploaded', 0) for r in all_results)
        
        summary = {
            "scrape_date": datetime.now().isoformat(),
            "scraper_version": "3.0-airflow",
            "run_folder": "initial_pull",
            "total_companies": len(all_results),
            "successful": len(successful),
            "failed": len(failed),
            "total_pages_posts": total_pages,
            "total_files_uploaded": total_files,
            "average_per_company": round(total_pages / len(all_results), 1) if all_results else 0,
            "companies": all_results
        }
        
        # Save results to GCS
        results_path = f"{RESULTS_PREFIX}scraping_results_initial_pull.json"
        success = save_json_to_gcs(bucket_name, summary, results_path)
        
        if success:
            logger.info(f"Results saved to gs://{bucket_name}/{results_path}")
            logger.info(f"Summary: {len(successful)}/{len(all_results)} successful, {total_pages} pages, {total_files} files")
        else:
            logger.error("Failed to save results to GCS")
        
        return summary

    # Define task flow
    companies = load_company_list()
    
    # Expand: Create one task per company
    scrape_results = scrape_company_pages.expand(company=companies)
    
    # Aggregate results
    final_results = store_results(scrape_results)

