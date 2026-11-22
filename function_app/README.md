# Pokemon ADLS Azure Functions

This project refactors the supplied PokemonDB extraction code into an Azure
Functions app. Azure Data Factory starts the index extraction. Event Grid
reacts to the two control-file uploads. Azure Queue Storage runs one detail
extraction per Pokemon. The agent tool for PokeAPI species traits moved to
`pokedex_agent_app`.

The primary functions are grouped at the top of `function_app.py`. Private
helper functions from that file are in `function_utils.py`. Each Python file
uses different comment-block styles for primary functions and utility functions.

## Python project structure

| File | Responsibility |
|---|---|
| `function_app.py` | Azure Function triggers and primary execution flow |
| `function_utils.py` | Private helper functions used by the Function App |
| `pokedex.py` | Pokedex index and stats extraction |
| `pokemon_details.py` | One-Pokemon detail-page extraction |
| `storage.py` | ADLS Blob and Storage Queue operations |

`function_app.py` contains only Azure Function entry points. Its private
helper functions are in `function_utils.py`. The extraction modules keep
small, domain-specific parsing helpers next to the primary extraction logic.

The code uses two comment styles to show the execution structure:

- `# ===` blocks mark primary workflows and Azure Function entry points.
- `# ---` blocks mark supporting utilities and parsing helpers.

Within each module, primary workflows appear first. Supporting helpers follow
in the order in which the workflows use them.

## Function flow

1. ADF calls `POST /api/extract-pokedex-initializers`.
2. The function downloads the PokemonDB Pokedex page.
3. It writes:
   - `bronze/pokemondb/init/{run_id}/pokedex_rows.html`
   - `bronze/pokemondb/init/{run_id}/pokemon_urls.txt`
4. A `BlobCreated` event for `pokedex_rows.html` starts the stats function
   path. It reads the HTML rows, creates `pokemon_stats_df`, and writes:
   - `bronze/pokemondb/pokemon_stats/{run_id}/pokemon_stats.parquet`
5. A `BlobCreated` event for `pokemon_urls.txt` reads the tab-separated rows
   and sends one message per Pokemon to `pokemon-detail-jobs`.
6. The queue-triggered function handles one Pokemon per message. It writes
   biography and Pokedex text, JSON details, and Parquet move DataFrames.


## ADLS Gen2 layout

The code uses run-specific paths. This keeps each extraction run separate.

```text
pokemon/
└── bronze/
    └── pokemondb/
        ├── init/
        │   └── {run_id}/
        │       ├── pokedex_rows.html
        │       ├── pokemon_urls.txt
        │       └── completed_jobs/{pokemon_id:04d}-{slug}.json
        ├── pokemon_stats/
        │   └── {run_id}/pokemon_stats.parquet
        ├── pokemon_details/
        │   └── {run_id}/{pokemon_id:04d}-{slug}/
        │       ├── pokemon_bio.txt
        │       ├── pokedex_entry.txt
        │       ├── pokedex_data.json
        │       ├── training.json
        │       └── breeding.json
        ├── moves_learned/
        │   └── {run_id}/{pokemon_id:04d}-{slug}.parquet
        └── moves_tm/
            └── {run_id}/{pokemon_id:04d}-{slug}.parquet
```

`{slug}` is the lower-case Pokemon name with non-alphanumeric characters
replaced by `-`. Example: `0025-pikachu`.

The path is organized by layer, then source system (`pokemondb`), then
entity. The Function app writes only to Bronze. Silver, Gold, and Control
layers are planned but not built. The completion records are in
`bronze/pokemondb/init/{run_id}/completed_jobs/` until a Control layer exists.

## Before local testing

1. Create an ADLS Gen2 storage account with Hierarchical namespace enabled.
2. Create a private container named `pokemon`.
3. Create a Storage Queue named `pokemon-detail-jobs`.
4. Give your developer account `Storage Blob Data Contributor` on the storage
   account or container.
5. Give your developer account `Storage Queue Data Contributor` on the queue
   or storage account.
6. Install Azure Functions Core Tools and Python 3.11.
7. Sign in with `az login`.
8. Copy `local.settings.example.json` to `local.settings.json`.
9. Set `AzureWebJobsStorage` to a storage connection string for the Functions
   host. Set the storage account name and queue endpoint in the other settings.
10. Install packages with `pip install -r requirements.txt`.

Do not commit `local.settings.json`. It contains local secrets.

For local queue-trigger authentication, the `PokemonQueue__queueServiceUri`
setting uses `DefaultAzureCredential`. After `az login`, the SDK can use your
Azure CLI identity. For an Azure-hosted Function App, set
`PokemonQueue__credential` to `managedidentity`.

## Azure Function App settings

Configure these application settings:

| Setting | Value |
|---|---|
| `STORAGE_ACCOUNT_NAME` | Your ADLS Gen2 storage account name |
| `STORAGE_CONTAINER_NAME` | `pokemon` |
| `POKEMON_QUEUE_NAME` | `pokemon-detail-jobs` |
| `PokemonQueue__queueServiceUri` | `https://{account}.queue.core.windows.net` |
| `PokemonQueue__credential` | `managedidentity` |
| `AzureWebJobsStorage` | Function host storage connection |

The Function App's system-assigned managed identity needs:
- `Storage Blob Data Contributor` on the `pokemon` container or storage account.
- `Storage Queue Data Contributor` on the queue or storage account.

The queue role lets the Event Grid handler enqueue work and lets the queue
trigger process messages. For tighter access, separate the sender and
processor identities and grant the narrower queue data roles.

The Function host also needs its own `AzureWebJobsStorage` access. This is
separate from the `STORAGE_ACCOUNT_NAME` SDK setting.

## Event Grid setup

Create **two** Event Grid subscriptions on the ADLS Gen2 storage account.
Both subscriptions use event type `Microsoft.Storage.BlobCreated`.

Subscription 1:
- Subject begins with:
  `/blobServices/default/containers/pokemon/blobs/bronze/pokemondb/init/`
- Subject ends with: `/pokedex_rows.html`
- Endpoint function: `on_pokedex_rows_uploaded`

Subscription 2:
- Subject begins with:
  `/blobServices/default/containers/pokemon/blobs/bronze/pokemondb/init/`
- Subject ends with: `/pokemon_urls.txt`
- Endpoint function: `on_pokemon_urls_uploaded`

Each subscription invokes a separate Function. The code also checks the
complete blob path before it acts. It ignores Parquet, JSON, text, and
completion files. This prevents recursive processing.

Both Event Grid subscriptions must be active before the index function
uploads its first files. Configure dead-lettering and monitor Event Grid
delivery failures for production.

## ADF setup

Use an Azure Function activity to call:

`POST https://{function-app}.azurewebsites.net/api/extract-pokedex-initializers`

Configure the Function key in the ADF linked service/activity. The request
body can be `{}`. You can also pass a run ID:

```json
{
  "run_id": "@pipeline().RunId"
}
```

The function returns HTTP 202 after it uploads both control files. The
subsequent stats and detail work runs asynchronously from Event Grid and
Queue Storage. The ADF activity does not wait for all Pokemon jobs to finish.

For end-to-end run monitoring, query the completion files under
`bronze/pokemondb/init/{run_id}/completed_jobs/` and compare their count with the number
of rows in `pokemon_urls.txt`. In production, add a run-status record and a
finalization function to mark the run complete or failed.

## Run locally

From this project folder:

```bash
func start
```

Call the index function:

```bash
curl -X POST http://localhost:7071/api/extract-pokedex-initializers \
  -H "Content-Type: application/json" \
  -d "{}"
```

For local end-to-end event testing, connect the storage account's Event Grid
subscription to the local Function endpoint or manually invoke the
Event Grid-triggered function with a test event. The queue trigger can process
messages from the configured queue.

## Important source adjustments

The project preserves the supplied extraction approach and corrects a few
issues needed for reliable execution:

- `from __future__ import annotations` must appear before ordinary imports;
  it is not needed in every file, but is placed correctly where used.
- The supplied `get_pokedex_stats()` referenced an undefined variable
  `pokemon_stats_df`. This version returns the DataFrame it builds.
- The original local runner only processed `pokemon_urls[25:26]`. The queue
  fan-out now creates a job for every URL record.
- URL records and stats rows use the same ordered, sequential `pokemon_id`.
  This is a project key, not necessarily the National Pokedex number.
  `filter_pokedex_rows_urls` creates both from the same filtered rows, so the
  IDs agree. The filter keeps National Dex numbers up to 493 (Gen 1 to 4).
- The move `level` value stays text so values such as `Evo.` are preserved.
- `power` and `accuracy` are converted to nullable integers. A trailing `%`
  is removed before conversion.
- Move DataFrames use `pokemon_id` and the same columns as the SQL staging
  tables. The extra generated `id` column from the source helper is not
  written.
- The PokeAPI agent tool is maintained in `pokedex_agent_app`.

## Production notes

- Event Grid and Queue Storage deliver events/messages at least once.
  A message can be delivered again. The output paths are deterministic for
  a run and Pokemon, so a retry overwrites the same files.
- The per-Pokemon queue pattern limits each execution to one detail page.
  `host.json` starts with a modest queue batch size of four. Adjust only after
  measuring PokemonDB rate limits and Function App capacity.
- Queue messages that fail repeatedly go to `pokemon-detail-jobs-poison`.
  Monitor that queue.
- The `completed` JSON file is written only after all files for that Pokemon
  upload successfully.
- The URL list and stats file use the same project IDs. Do not independently
  regenerate IDs in the downstream process.
- Add a durable run-status/finalization step before treating a run as
  complete. The number of completion JSON files should match the URL count.
- For production, use managed identity, least-privilege data roles, Key Vault
  for any non-identity secrets, Application Insights, and Event Grid
  dead-lettering.
