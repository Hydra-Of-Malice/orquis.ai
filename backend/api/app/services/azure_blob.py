"""
Azure Blob Storage service for audio/video files.
"""
import os
from urllib.parse import urlparse


def _get_client():
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if not conn_str:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING not configured")
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(conn_str)


def _get_container() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "recordings")


def upload_blob(local_path: str, blob_name: str) -> str:
    """Upload a file and return its public URL."""
    client = _get_client()
    container = _get_container()
    with open(local_path, "rb") as f:
        client.get_blob_client(container=container, blob=blob_name).upload_blob(f, overwrite=True)
    account = client.account_name
    return f"https://{account}.blob.core.windows.net/{container}/{blob_name}"


def generate_sas_url(blob_url: str, expiry_hours: int = 1) -> str:
    """Generate a short-lived SAS URL for a blob."""
    from datetime import datetime, timezone, timedelta
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions

    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    container = _get_container()

    parsed = urlparse(blob_url)
    blob_name = parsed.path.lstrip(f"/{container}/")

    from azure.storage.blob import BlobServiceClient as _BSC
    bsc = _BSC.from_connection_string(conn_str)
    account_key = bsc.credential.account_key
    account_name = bsc.account_name

    sas = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas}"


def delete_blob_prefix(prefix_url: str):
    """Delete all blobs under a URL prefix."""
    client = _get_client()
    container = _get_container()
    parsed = urlparse(prefix_url)
    prefix = parsed.path.lstrip(f"/{container}/")
    cc = client.get_container_client(container)
    for blob in cc.list_blobs(name_starts_with=prefix):
        cc.delete_blob(blob.name, delete_snapshots="include")


def list_blobs_with_prefix(prefix_url: str) -> list:
    client = _get_client()
    container = _get_container()
    parsed = urlparse(prefix_url)
    prefix = parsed.path.lstrip(f"/{container}/")
    cc = client.get_container_client(container)
    return list(cc.list_blobs(name_starts_with=prefix))
