from __future__ import annotations

import json
import logging
import os

import azure.functions as func

from function_utils import (
    process_pokedex_rows_upload,
    enqueue_pokemon_url_file,
    _new_run_id,
    _validate_run_id,
    _serialize_url_records,
    _slugify,
    _blob_path_from_event,
)
from pokedex import create_pokedex_html_urls
from pokemon_details import get_pokemon_data

from storage import (
    upload_json_blob,
    upload_parquet_blob,
    upload_text_blob,
)


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# =============================================================================
# PRIMARY FUNCTION 1: Extract the Pokedex index and upload the two init files.
# =============================================================================
@app.route(
    route="extract-pokedex-initializers",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def extract_pokedex_initializers(req: func.HttpRequest) -> func.HttpResponse:
    """ADF entry point. Upload the filtered Pokedex rows and Pokemon URLs."""
    try:
        try:
            body = req.get_json()
        except ValueError:
            body = {}

        requested_run_id = body.get("run_id") if isinstance(body, dict) else None
        run_id = (
            _validate_run_id(requested_run_id)
            if requested_run_id
            else _new_run_id()
        )

        rows_html, url_records = create_pokedex_html_urls()
        url_text = _serialize_url_records(url_records)

        rows_path = f"bronze/pokemondb/init/{run_id}/pokedex_rows.html"
        urls_path = f"bronze/pokemondb/init/{run_id}/pokemon_urls.txt"

        # Upload rows first. Its BlobCreated event starts the stats workflow.
        upload_text_blob(
            rows_path,
            rows_html,
            content_type="text/html; charset=utf-8",
        )

        # Upload URLs second. Its BlobCreated event queues detail jobs.
        upload_text_blob(urls_path, url_text)

        response = {
            "status": "accepted",
            "run_id": run_id,
            "pokemon_count": len(url_records),
            "pokedex_rows_blob": rows_path,
            "pokemon_urls_blob": urls_path,
        }

        logging.info(
            "Created Pokedex run %s with %s Pokemon records.",
            run_id,
            len(url_records),
        )

        return func.HttpResponse(
            json.dumps(response),
            status_code=202,
            mimetype="application/json",
        )

    except Exception as exc:
        logging.exception("Pokedex index extraction failed.")
        return func.HttpResponse(
            json.dumps({"status": "failed", "error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )


# =============================================================================
# PRIMARY FUNCTION 2: Create stats Parquet after pokedex_rows.html is uploaded.
# =============================================================================
@app.event_grid_trigger(arg_name="event")
def on_pokedex_rows_uploaded(event: func.EventGridEvent) -> None:
    """Create the Pokemon stats Parquet file after the rows file arrives."""
    if event.event_type != "Microsoft.Storage.BlobCreated":
        return

    blob_path = _blob_path_from_event(event)
    if not (
        blob_path.startswith("bronze/pokemondb/init/")
        and blob_path.endswith("/pokedex_rows.html")
    ):
        return

    logging.info("Processing Pokedex rows upload: %s", blob_path)
    process_pokedex_rows_upload(blob_path)


# =============================================================================
# PRIMARY FUNCTION 3: Queue one detail job per record after the URL file arrives.
# =============================================================================
@app.event_grid_trigger(arg_name="event")
def on_pokemon_urls_uploaded(event: func.EventGridEvent) -> None:
    """Fan out one queue message per URL when pokemon_urls.txt is uploaded."""
    if event.event_type != "Microsoft.Storage.BlobCreated":
        return

    blob_path = _blob_path_from_event(event)
    if not (
        blob_path.startswith("bronze/pokemondb/init/")
        and blob_path.endswith("/pokemon_urls.txt")
    ):
        return

    logging.info("Processing Pokemon URL upload: %s", blob_path)
    enqueue_pokemon_url_file(blob_path)


# =============================================================================
# PRIMARY FUNCTION 4: Process one Pokemon detail job and write its Bronze files.
# =============================================================================
@app.queue_trigger(
    arg_name="message",
    queue_name=os.environ.get("POKEMON_QUEUE_NAME", "pokemon-detail-jobs"),
    connection="PokemonQueue",
)
def process_pokemon_detail_job(message: func.QueueMessage) -> None:
    """Process one Pokemon URL per message and upload its extracted data."""
    job = json.loads(message.get_body().decode("utf-8"))

    run_id = _validate_run_id(str(job["run_id"]))
    pokemon_id = int(job["pokemon_id"])
    pokemon_name = str(job.get("pokemon_name") or f"pokemon-{pokemon_id}")
    url = str(job["url"])

    pokemon_data = get_pokemon_data(url, pokemon_id)

    # Use the name from the detail page when it is available.
    pokemon_name = pokemon_data.get("pokemon_name") or pokemon_name
    slug = _slugify(pokemon_name)
    pokemon_folder = f"{pokemon_id:04d}-{slug}"

    text_base = f"bronze/pokemondb/pokemon_details/{run_id}/{pokemon_folder}"
    json_base = f"bronze/pokemondb/pokemon_details/{run_id}/{pokemon_folder}"

    upload_text_blob(
        f"{text_base}/pokemon_bio.txt",
        pokemon_data["pokemon_bio"],
    )
    upload_text_blob(
        f"{text_base}/pokedex_entry.txt",
        pokemon_data["pokedex_entry"],
    )

    upload_json_blob(
        f"{json_base}/pokedex_data.json",
        pokemon_data["pokedex_data"],
    )
    upload_json_blob(
        f"{json_base}/training.json",
        pokemon_data["training"],
    )
    upload_json_blob(
        f"{json_base}/breeding.json",
        pokemon_data["breeding"],
    )

    upload_parquet_blob(
        f"bronze/pokemondb/moves_learned/{run_id}/{pokemon_folder}.parquet",
        pokemon_data["moves_learned"],
    )
    upload_parquet_blob(
        f"bronze/pokemondb/moves_tm/{run_id}/{pokemon_folder}.parquet",
        pokemon_data["moves_tm"],
    )

    # Write this record only after every Pokemon file upload succeeds.
    upload_json_blob(
        f"bronze/pokemondb/init/{run_id}/completed_jobs/{pokemon_folder}.json",
        {
            "run_id": run_id,
            "pokemon_id": pokemon_id,
            "pokemon_name": pokemon_name,
            "source_url": url,
            "status": "success",
        },
    )

    logging.info(
        "Completed Pokemon detail job. run_id=%s pokemon_id=%s name=%s",
        run_id,
        pokemon_id,
        pokemon_name,
    )
