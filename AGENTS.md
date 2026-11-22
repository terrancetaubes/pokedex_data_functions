# AGENTS.md: pokedex_data_functions

Read the parent `../AGENTS.md` first. Its rules apply here.

## Purpose

Azure Functions (Python v2 model) that extract Pokemon data from PokemonDB and PokeAPI into ADLS Gen2. Azure Data Factory starts the index extraction. Event Grid and Storage Queues drive the rest.

## Layout

| Path | Contents |
|---|---|
| `function_app/` | The Function App project. This folder is the deployable unit. Put only runtime code here. |
| `function_app/function_app.py` | Function entry points. Do not add helpers here. |
| `function_app/function_utils.py` | Private helpers for `function_app.py` |
| `function_app/.funcignore` | Files that the deploy package must not contain |
| `tests/` | pytest tests. Outside `function_app/` so they are not deployed. |
| `pytest.ini`, `requirements-dev.txt` | Test configuration and dev packages (pytest, ruff) |
| `.github/workflows/ci-cd.yml` | Lint, test, and compile on pull requests and branch pushes. Deploy to `dev` from `develop` and to `itg` from `release/**`. |
| `docs/` | `ENVIRONMENTS.md` and `RUNBOOK.md` |

## Project Overview

The Pokémon data platform uses Azure Functions to support two capabilities:

- Data ingestion and processing.
- On-demand data retrieval for AI agents.

The platform uses Azure Data Lake Storage Gen2 (ADLS Gen2) for data storage, Azure Event Grid for event-driven orchestration, Azure Storage Queue for asynchronous job processing, and Azure Data Factory (ADF) to initiate ingestion.

Agent tools are not in this repository. The PokeAPI species tool moved to `pokedex_agent_app` (`src/pokedex_agent/tools/`). This repository now contains the data pipeline only.

1. Data Pipeline Functions

extract_pokedex_initializers

Trigger: HTTP (route: extract-pokedex-initializers)
Caller: Azure Data Factory
Type: Data pipeline entry point
Purpose: Starts a Pokédex ingestion run.

Responsibilities:

Downloads the Pokédex index from PokémonDB.
Extracts Pokédex rows.
Extracts individual Pokémon URLs.
Generates a run ID.
Uploads source files to ADLS Gen2.

on_pokedex_rows_uploaded

Trigger: Azure Event Grid — Blob Created
Type: Event-driven data processing
Purpose: Processes the uploaded Pokédex rows.

Responsibilities:

Receives the file-upload event.
Reads the Pokédex rows from ADLS.
Creates the pokemon_stats_df DataFrame.
Writes the Pokémon stats dataset as Parquet.

on_pokemon_urls_uploaded

Trigger: Azure Event Grid — Blob Created
Type: Event-driven job orchestration
Purpose: Creates individual Pokémon processing jobs.

Responsibilities:

Receives the file-upload event.
Reads the Pokémon URL list.
Creates one queue message per Pokémon.
Sends messages to the pokemon-detail-jobs Azure Storage Queue.

process_pokemon_detail_job

Trigger: Azure Storage Queue
Type: Asynchronous data processing worker
Purpose: Processes one Pokémon per queue message.

Responsibilities:

Reads a Pokémon processing job.
Extracts Pokémon details.
Extracts biography and Pokédex entry text.
Extracts training and breeding information.
Extracts moves learned and TM moves.
Writes structured and unstructured outputs to ADLS Gen2.
Writes a job completion record.
Expected outputs include:

Pokémon biography: TXT
Pokédex entry: TXT
Pokédex details: JSON
Training information: JSON
Breeding information: JSON
Moves learned: Parquet
TM moves: Parquet

2. Agent-Facing API Functions

None in this repository. The PokeAPI species tool (`get_pokemon_species_traits`) moved to `pokedex_agent_app`.

3. Trigger Types

Trigger

Purpose

HTTP

Executes a Function when an API request is received.

Event Grid

Executes a Function when a configured storage event occurs.

Storage Queue

Executes a Function when a message becomes available for processing.

4. End-to-End Data Pipeline

The ingestion process follows this sequence:

Azure Data Factory calls extract_pokedex_initializers.
The Function extracts the Pokédex rows and Pokémon URLs.
The Function uploads both files to ADLS Gen2.
Event Grid detects the Pokédex rows upload.
on_pokedex_rows_uploaded creates the Pokémon stats Parquet dataset.
Event Grid detects the Pokémon URL list upload.
on_pokemon_urls_uploaded creates individual Pokémon jobs.
Azure Storage Queue holds the processing messages.
process_pokemon_detail_job processes each Pokémon independently.
The Function writes the extracted data to ADLS Gen2.
The queue allows individual Pokémon jobs to execute asynchronously and independently.

5. ADLS Gen2 Storage Organization

The data lake follows a medallion architecture.
Bronze: Original source data and API responses.
Silver: Extracted, cleaned, and structured datasets.
Gold: Curated datasets designed for application and analytical consumption.
Control: Run manifests, job completion records, processing status, and error records.

Status: The code writes only Bronze today. Silver, Gold, and Control are planned. Job completion records are in `bronze/pokemondb/init/{run_id}/completed_jobs/` until a Control layer exists.

Current Bronze paths (container `pokemon`):

- `bronze/pokemondb/init/{run_id}/pokedex_rows.html`, `pokemon_urls.txt`, `completed_jobs/{id}-{slug}.json`
- `bronze/pokemondb/pokemon_stats/{run_id}/pokemon_stats.parquet`
- `bronze/pokemondb/pokemon_details/{run_id}/{id}-{slug}/` (`pokemon_bio.txt`, `pokedex_entry.txt`, `pokedex_data.json`, `training.json`, `breeding.json`)
- `bronze/pokemondb/moves_learned/{run_id}/{id}-{slug}.parquet`
- `bronze/pokemondb/moves_tm/{run_id}/{id}-{slug}.parquet`

Organize data primarily by processing layer, source system, and business entity. Do not use file extensions as the primary directory structure.

Use Parquet for structured analytical datasets, JSON for structured API or document data, and TXT for extracted text.

6. Python Module Responsibilities

Python modules support the Azure Function entry points.

function_app.py: Defines Azure Functions, their triggers, and their primary execution flow.

function_utils.py: Contains private helper functions used by Function entry points.

pokedex.py: Contains Pokédex extraction and parsing logic.

pokemon_details.py: Contains individual Pokémon detail extraction logic.

storage.py: Contains ADLS Gen2 and Azure Storage Queue operations.

pokeapi.py: Moved to pokedex_agent_app. It is no longer in this repository.

Utility functions are not independent Azure Functions or agent tools. They are reusable Python functions called by the primary Functions.

7. Architecture Principles

Keep ingestion separate from agent tools. This repository contains ingestion only.
Use HTTP triggers for externally initiated requests.
Use Event Grid for event-driven processing.
Use Storage Queues for asynchronous, distributed jobs.
Use ADLS Gen2 as the central data lake.
Use managed identities for Azure resource access.
Keep secrets out of source code.
Make processing idempotent so duplicate events or messages do not create incorrect data.
Track ingestion runs and individual job outcomes.

## Rules for agents

- Keep the code style in `function_app/README.md`: `# ===` blocks for workflows, `# ---` blocks for utilities.
- Do not hard-code storage account names, URLs, or keys. Read them from app settings (`os.environ`).
- Authenticate to Azure with `DefaultAzureCredential` and the Function's managed identity. Do not use connection strings in code.
- Do not add agent-facing HTTP endpoints here. Agent tools belong in `pokedex_agent_app`.
- Do not commit `local.settings.json`. Use `local.settings.example.json` as the template.
- Dependencies are pinned with lower bounds in `requirements.txt`. Add new packages there with a reason in the change log.
- Log every change in `AGENT_CHANGELOG.md`.
