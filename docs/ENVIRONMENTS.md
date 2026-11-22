# Environments

Branch-to-environment mapping: `../../docs/BRANCHING_AND_RELEASE.md` in the project folder.

## GitHub environment variables (set in `dev` and `itg`)

| Name | Type | Value |
|---|---|---|
| `AZURE_TENANT_ID` | variable | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | variable | Subscription ID |
| `AZURE_CLIENT_ID` | variable | `gh-pokedex-data-functions-<env>` client ID |
| `AZURE_FUNCTIONAPP_NAME` | variable | `func-pokedex-<env>-<suffix>` (see infra `docs/ENVIRONMENTS.md`) |

## Application settings

Application settings are set by Bicep in `pokedex_infra/modules/apps.bicep`. They include the storage account, queue name, container name, and identity client ID. Do not put settings in source control. For local development, use `function_app/local.settings.json`, created from the example file.

## Azure Function App prerequisites

- Event Grid subscriptions for blob-created events, one for `pokedex` rows and one for the URL list. Create them once per environment. They are not in Bicep yet.
- The function's identity needs the roles set in `pokedex_infra/identity/rbac.bicep`.
