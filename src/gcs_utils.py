"""
GCS Utility Functions for Cloud Composer Integration

Provides helper functions for uploading/downloading files to/from Google Cloud Storage.
Used by Airflow DAGs to interact with GCS buckets.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from google.cloud import storage
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

# Cache the client to avoid re-initialization
_gcs_client = None


def get_gcs_client() -> storage.Client:
    """
    Get a GCS client instance.
    Uses service account credentials from config/gcp.json if available,
    otherwise falls back to Application Default Credentials.
    
    Returns:
        storage.Client: Initialized GCS client
    """
    global _gcs_client
    
    # Return cached client if available
    if _gcs_client is not None:
        return _gcs_client
    
    try:
        project_id = os.getenv("PROJECT_ID")
        
        # Try to use credentials file if it exists (local/Docker development)
        # In Airflow, the config directory is mounted at /opt/airflow/config
        credentials_paths = [
            Path("/opt/airflow/config/gcp.json"),  # Airflow Docker container path
            Path(__file__).parent.parent / "config" / "gcp.json",  # Local development path
        ]
        
        credentials_path = None
        for path in credentials_paths:
            if path.exists():
                credentials_path = path
                break
        
        if credentials_path and credentials_path.exists():
            try:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(
                    str(credentials_path)
                )
                _gcs_client = storage.Client(project=project_id, credentials=credentials)
                logger.info(f"✅ GCS client initialized with credentials from {credentials_path}")
                return _gcs_client
            except ImportError:
                logger.warning("⚠️  google.oauth2.service_account not available, using default credentials")
            except Exception as e:
                logger.warning(f"⚠️  Failed to load credentials from {credentials_path}: {e}, using default credentials")
        
        # Fall back to Application Default Credentials (production/Cloud Run)
        _gcs_client = storage.Client(project=project_id)
        logger.info("✅ GCS client initialized with Application Default Credentials")
        return _gcs_client
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize GCS client: {e}")
        # Still try to return a basic client as fallback
        try:
            _gcs_client = storage.Client()
            return _gcs_client
        except Exception as fallback_error:
            logger.error(f"❌ Fallback GCS client initialization also failed: {fallback_error}")
            raise


def upload_file_to_gcs(
    bucket_name: str,
    local_file_path: str,
    gcs_blob_path: str,
    content_type: Optional[str] = None
) -> bool:
    """
    Upload a file to Google Cloud Storage.
    
    Args:
        bucket_name: Name of the GCS bucket
        local_file_path: Local file path to upload
        gcs_blob_path: Destination path in GCS (e.g., 'raw/company_id/page.html')
        content_type: Optional content type (e.g., 'text/html', 'application/json')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_path)
        
        # Set content type if provided
        if content_type:
            blob.content_type = content_type
        
        blob.upload_from_filename(local_file_path)
        logger.info(f"Uploaded {local_file_path} to gs://{bucket_name}/{gcs_blob_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_file_path} to GCS: {e}")
        return False


def upload_string_to_gcs(
    bucket_name: str,
    content: str,
    gcs_blob_path: str,
    content_type: Optional[str] = None
) -> bool:
    """
    Upload a string to Google Cloud Storage.
    
    Args:
        bucket_name: Name of the GCS bucket
        content: String content to upload
        gcs_blob_path: Destination path in GCS
        content_type: Optional content type
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_path)
        
        if content_type:
            blob.content_type = content_type
        
        blob.upload_from_string(content, content_type=content_type)
        logger.info(f"Uploaded string to gs://{bucket_name}/{gcs_blob_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload string to GCS: {e}")
        return False


def download_file_from_gcs(
    bucket_name: str,
    gcs_blob_path: str,
    local_file_path: str
) -> bool:
    """
    Download a file from Google Cloud Storage.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_blob_path: Source path in GCS
        local_file_path: Local destination path
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_path)
        
        # Create parent directories if needed
        Path(local_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        blob.download_to_filename(local_file_path)
        logger.info(f"Downloaded gs://{bucket_name}/{gcs_blob_path} to {local_file_path}")
        return True
    except NotFound:
        logger.warning(f"File not found in GCS: gs://{bucket_name}/{gcs_blob_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to download from GCS: {e}")
        return False


def download_string_from_gcs(
    bucket_name: str,
    gcs_blob_path: str
) -> Optional[str]:
    """
    Download a file from GCS as a string.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_blob_path: Source path in GCS
        
    Returns:
        str: File content as string, or None if failed
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_path)
        
        content = blob.download_as_text()
        logger.info(f"Downloaded string from gs://{bucket_name}/{gcs_blob_path}")
        return content
    except NotFound:
        logger.warning(f"File not found in GCS: gs://{bucket_name}/{gcs_blob_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to download string from GCS: {e}")
        return None


def list_gcs_files(
    bucket_name: str,
    prefix: str,
    delimiter: Optional[str] = None
) -> List[str]:
    """
    List files in a GCS bucket with the given prefix.
    
    Args:
        bucket_name: Name of the GCS bucket
        prefix: Prefix to filter files (e.g., 'raw/company_id/')
        delimiter: Optional delimiter (e.g., '/' to list only top-level)
        
    Returns:
        List[str]: List of blob paths matching the prefix
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        blobs = bucket.list_blobs(prefix=prefix, delimiter=delimiter)
        return [blob.name for blob in blobs]
    except Exception as e:
        logger.error(f"Failed to list files in GCS: {e}")
        return []


def check_gcs_file_exists(
    bucket_name: str,
    gcs_blob_path: str
) -> bool:
    """
    Check if a file exists in GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_blob_path: Path to check in GCS
        
    Returns:
        bool: True if file exists, False otherwise
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_path)
        return blob.exists()
    except Exception as e:
        logger.error(f"Failed to check file existence in GCS: {e}")
        return False


def upload_directory_to_gcs(
    bucket_name: str,
    local_dir_path: str,
    gcs_prefix: str
) -> int:
    """
    Upload a directory recursively to GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
        local_dir_path: Local directory path to upload
        gcs_prefix: Prefix in GCS (e.g., 'raw/company_id/initial_pull/')
        
    Returns:
        int: Number of files uploaded
    """
    uploaded_count = 0
    local_path = Path(local_dir_path)
    
    if not local_path.is_dir():
        logger.error(f"Not a directory: {local_dir_path}")
        return 0
    
    try:
        for file_path in local_path.rglob('*'):
            if file_path.is_file():
                # Get relative path from local_dir_path
                relative_path = file_path.relative_to(local_path)
                # Convert Windows path separators to forward slashes
                relative_path_str = str(relative_path).replace('\\', '/')
                gcs_blob_path = f"{gcs_prefix.rstrip('/')}/{relative_path_str}"
                
                # Determine content type
                content_type = None
                if file_path.suffix == '.html':
                    content_type = 'text/html'
                elif file_path.suffix == '.json':
                    content_type = 'application/json'
                elif file_path.suffix == '.txt':
                    content_type = 'text/plain'
                
                if upload_file_to_gcs(bucket_name, str(file_path), gcs_blob_path, content_type):
                    uploaded_count += 1
        
        logger.info(f"Uploaded {uploaded_count} files from {local_dir_path} to gs://{bucket_name}/{gcs_prefix}")
        return uploaded_count
    except Exception as e:
        logger.error(f"Failed to upload directory to GCS: {e}")
        return uploaded_count


def load_json_from_gcs(
    bucket_name: str,
    gcs_blob_path: str
) -> Optional[dict]:
    """
    Load a JSON file from GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_blob_path: Path to JSON file in GCS
        
    Returns:
        dict: Parsed JSON content, or None if failed
    """
    content = download_string_from_gcs(bucket_name, gcs_blob_path)
    if content is None:
        return None
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from GCS: {e}")
        return None


def save_json_to_gcs(
    bucket_name: str,
    data: dict,
    gcs_blob_path: str
) -> bool:
    """
    Save a dictionary as JSON to GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
        data: Dictionary to save as JSON
        gcs_blob_path: Destination path in GCS
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        json_str = json.dumps(data, indent=2)
        return upload_string_to_gcs(
            bucket_name,
            json_str,
            gcs_blob_path,
            content_type='application/json'
        )
    except Exception as e:
        logger.error(f"Failed to save JSON to GCS: {e}")
        return False


def read_file_from_gcs(
    bucket_name: str,
    file_path: str
) -> Optional[str]:
    """
    Read a file from GCS bucket as a string.
    Alias for download_string_from_gcs for compatibility.
    
    Args:
        bucket_name: Name of the GCS bucket
        file_path: Path to file in GCS
        
    Returns:
        str: File content as string, or None if failed
    """
    return download_string_from_gcs(bucket_name, file_path)


def list_files_from_gcs(
    bucket_name: str,
    prefix: str
) -> List[str]:
    """
    List files in GCS bucket with given prefix.
    Alias for list_gcs_files for compatibility.
    
    Args:
        bucket_name: Name of the GCS bucket
        prefix: Prefix to filter files (e.g., 'raw/company_id/')
        
    Returns:
        List[str]: List of blob paths matching the prefix
    """
    return list_gcs_files(bucket_name, prefix)

