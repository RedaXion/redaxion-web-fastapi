import os
import json
from google.cloud import storage
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize GCS Client lazily
_storage_client = None
_bucket_name = os.getenv("GCS_BUCKET_NAME")

def get_storage_client():
    global _storage_client
    if _storage_client:
        return _storage_client

    try:
        # Option 1: Try loading from JSON env var (Railway)
        gcs_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if gcs_credentials_json:
            from google.oauth2 import service_account
            credentials_dict = json.loads(gcs_credentials_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_dict)
            _storage_client = storage.Client(credentials=credentials, project=credentials_dict.get("project_id"))
            logger.info("✅ GCS Client initialized from GOOGLE_CREDENTIALS_JSON")
        else:
            # Option 2: Try default credentials (local dev with gcloud auth)
            logger.info("ℹ️ Attempting default GCS credentials...")
            _storage_client = storage.Client()
            logger.info("✅ GCS Client initialized with default credentials")
            
        return _storage_client
        
    except Exception as e:
        logger.error(f"⚠️ Could not initialize GCS client: {e}")
        return None

def upload_file_to_gcs(source_file_path: str, destination_blob_name: str, content_type: str = "application/pdf") -> str:
    """
    Uploads a file to Google Cloud Storage and returns the public URL.
    Returns None if upload fails or GCS is not configured.
    """
    client = get_storage_client()
    if not client or not _bucket_name:
        logger.warning(f"⚠️ Skipping upload for {source_file_path}: GCS not configured.")
        return None

    try:
        bucket = client.bucket(_bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        blob.upload_from_filename(source_file_path, content_type=content_type)
        
        # Make public if needed, or just return the storage URL
        # For this use case, we probably want a long-lived signed URL or just public read if it's safe?
        # Let's assume the bucket might verify permissions, but for a "generic" web app often files are public.
        # However, for paid content, we might want signed URLs.
        # For now, let's keep it simple: if the bucket allows public, fine.
        
        # Determine URL
        # blob.make_public() # Optional: WARNING - makes file publicly accessible
        
        public_url = f"https://storage.googleapis.com/{_bucket_name}/{destination_blob_name}"
        logger.info(f"✅ Uploaded to GCS: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"❌ Failed to upload to GCS: {e}")
        return None
