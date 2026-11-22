# Runbook

## CI fails on lint or tests

Run `ruff check --select E9,F function_app tests` and `pytest` from the repository root locally. Fix the reported line. Do not disable the rule.

## Deploy fails at the Azure login step

The GitHub environment's `AZURE_CLIENT_ID` does not match an app with a federated credential for `environment:<env>`. See `pokedex_infra/docs/RUNBOOK.md`.

## Function returns errors after deploy

1. Check the Function App's Application Insights for the exception.
2. Check the app settings. `AzureWebJobsStorage__accountName` and `PokemonQueue__queueServiceUri` must point at the environment's storage account.
3. Check the identity roles in `pokedex_infra/identity/rbac.bicep`.

## Roll back

Revert the commit on the branch and let CD run again. For a release branch, revert on the release branch and merge the same fix into `develop`.
