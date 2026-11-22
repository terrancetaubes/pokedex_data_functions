from __future__ import annotations

import csv
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

import azure.functions as func

from pokedex import get_pokedex_stats, parse_pokedex_rows_html
from storage import (
    download_text_blob,
    send_pokemon_job,
    upload_parquet_blob,
)


# =============================================================================
# PRIMARY FUNCTION: Build and upload the stats Parquet file after the rows upload.
# =============================================================================
def process_pokedex_rows_upload(blob_path: str) -> None:
    """Read stored Pokedex rows, build the stats DataFrame, and upload Parquet."""
    run_id = _run_id_from_path(blob_path)
    rows_html = download_text_blob(blob_path)
    rows = parse_pokedex_rows_html(rows_html)
    pokemon_stats_df = get_pokedex_stats(rows)

    output_path = (
        f"bronze/pokemondb/pokemon_stats/{run_id}/pokemon_stats.parquet"
    )
    upload_parquet_blob(output_path, pokemon_stats_df)

    logging.info(
        "Uploaded stats Parquet for run %s: %s rows.",
        run_id,
        len(pokemon_stats_df),
    )


# =============================================================================
# PRIMARY FUNCTION: Queue one independent detail job for every URL record.
# =============================================================================
def enqueue_pokemon_url_file(blob_path: str) -> None:
    """Read the URL control file and enqueue one message per Pokemon."""
    run_id = _run_id_from_path(blob_path)
    url_text = download_text_blob(blob_path)
    records = _parse_url_records(url_text)

    for record in records:
        send_pokemon_job({"run_id": run_id, **record})

    logging.info(
        "Queued %s individual Pokemon detail jobs for run %s.",
        len(records),
        run_id,
    )


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Create a unique ID for one extraction run.
# -----------------------------------------------------------------------------
def _new_run_id() -> str:
    """Create a UTC timestamp and random suffix for an extraction run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Validate a run ID before using it in an ADLS path.
# -----------------------------------------------------------------------------
def _validate_run_id(value: str) -> str:
    """Reject run IDs that contain unsafe path characters."""
    value = value.strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError(
            "run_id must contain only letters, numbers, underscores, "
            "or hyphens. Maximum length is 80."
        )
    return value


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Convert URL records to the tab-separated control-file format.
# -----------------------------------------------------------------------------
def _serialize_url_records(records: list[dict[str, Any]]) -> str:
    """Serialize Pokemon IDs, names, and URLs as tab-separated text."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["pokemon_id", "pokemon_name", "url"],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Parse the tab-separated Pokemon URL control file.
# -----------------------------------------------------------------------------
def _parse_url_records(content: str) -> list[dict[str, Any]]:
    """Convert URL control-file rows into validated queue-job records."""
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    records: list[dict[str, Any]] = []

    for row in reader:
        if not row.get("pokemon_id") or not row.get("url"):
            continue

        records.append(
            {
                "pokemon_id": int(row["pokemon_id"]),
                "pokemon_name": row.get("pokemon_name", ""),
                "url": row["url"],
            }
        )

    if not records:
        raise ValueError("The Pokemon URL file contains no valid job records.")

    return records


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Extract the container-relative blob path from an Event Grid event.
# -----------------------------------------------------------------------------
def _blob_path_from_event(event: func.EventGridEvent) -> str:
    """Return the blob path without the container name."""
    subject = event.subject or ""
    marker = "/blobs/"

    if marker in subject:
        return unquote(subject.split(marker, 1)[1]).lstrip("/")

    event_data = event.get_json()
    blob_url = event_data.get("url", "")
    path = unquote(urlparse(blob_url).path).lstrip("/")

    container_prefix = (
        os.environ.get("STORAGE_CONTAINER_NAME", "pokemon") + "/"
    )
    if path.startswith(container_prefix):
        path = path[len(container_prefix):]

    if not path:
        raise ValueError("Could not determine the blob path from Event Grid.")

    return path


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Read and validate the run ID from a standard Bronze blob path.
# -----------------------------------------------------------------------------
def _run_id_from_path(blob_path: str) -> str:
    """Extract the run ID from a path such as bronze/source/{run_id}/file."""
    parts = blob_path.split("/")
    if len(parts) < 4:
        raise ValueError(f"Unexpected Bronze blob path: {blob_path}")
    return _validate_run_id(parts[2])


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Create a safe folder name from a Pokemon name.
# -----------------------------------------------------------------------------
def _slugify(value: str) -> str:
    """Convert a Pokemon name into a safe, compact folder-name segment."""
    value = (value or "unknown-pokemon").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "unknown-pokemon"
