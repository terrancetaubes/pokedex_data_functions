from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient


_blob_service_client: BlobServiceClient | None = None
_queue_client: QueueClient | None = None


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Upload text content to a blob path.
# -----------------------------------------------------------------------------
def upload_text_blob(
    blob_path: str,
    content: str,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    blob_client = _get_blob_client(blob_path)
    blob_client.upload_blob(
        content.encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Serialize a Python object as JSON and upload it.
# -----------------------------------------------------------------------------
def upload_json_blob(blob_path: str, value: Any) -> None:
    content = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    upload_text_blob(
        blob_path,
        content,
        content_type="application/json; charset=utf-8",
    )


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Serialize a DataFrame as Parquet and upload it.
# -----------------------------------------------------------------------------
def upload_parquet_blob(blob_path: str, dataframe: pd.DataFrame) -> None:
    buffer = BytesIO()
    dataframe.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    blob_client = _get_blob_client(blob_path)
    blob_client.upload_blob(
        buffer.getvalue(),
        overwrite=True,
        content_settings=ContentSettings(
            content_type="application/vnd.apache.parquet"
        ),
    )


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Download a blob and decode its content as UTF-8 text.
# -----------------------------------------------------------------------------
def download_text_blob(blob_path: str) -> str:
    blob_client = _get_blob_client(blob_path)
    return blob_client.download_blob().readall().decode("utf-8")


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Send one Pokemon detail job to the Storage Queue.
# -----------------------------------------------------------------------------
def send_pokemon_job(message: dict[str, Any]) -> None:
    queue_client = _get_queue_client()
    queue_client.send_message(json.dumps(message, ensure_ascii=False))


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the Blob client for the configured storage account.
# -----------------------------------------------------------------------------
def _get_blob_client(blob_path: str):
    container_client = _get_blob_service_client().get_container_client(
        _container_name()
    )
    return container_client.get_blob_client(blob_path)


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Create or return the cached Blob service client.
# -----------------------------------------------------------------------------
def _get_blob_service_client() -> BlobServiceClient:
    global _blob_service_client

    if _blob_service_client is None:
        account_url = f"https://{_account_name()}.blob.core.windows.net"
        _blob_service_client = BlobServiceClient(
            account_url=account_url,
            credential=_credential(),
        )

    return _blob_service_client


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Create or return the cached Queue client.
# -----------------------------------------------------------------------------
def _get_queue_client() -> QueueClient:
    global _queue_client

    if _queue_client is None:
        queue_name = os.environ.get(
            "POKEMON_QUEUE_NAME", "pokemon-detail-jobs"
        )
        queue_url = f"https://{_account_name()}.queue.core.windows.net"
        _queue_client = QueueClient(
            account_url=queue_url,
            queue_name=queue_name,
            credential=_credential(),
        )

    return _queue_client


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Read and validate the storage account name setting.
# -----------------------------------------------------------------------------
def _account_name() -> str:
    value = os.environ.get("STORAGE_ACCOUNT_NAME")
    if not value:
        raise RuntimeError("STORAGE_ACCOUNT_NAME is not configured.")
    return value


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the configured ADLS container name.
# -----------------------------------------------------------------------------
def _container_name() -> str:
    return os.environ.get("STORAGE_CONTAINER_NAME", "pokemon")


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Create an identity credential for local or Azure execution.
# -----------------------------------------------------------------------------
def _credential() -> DefaultAzureCredential:
    # Locally, DefaultAzureCredential can use Azure CLI after `az login`.
    # In Azure, it can use the Function App's managed identity.
    return DefaultAzureCredential()
