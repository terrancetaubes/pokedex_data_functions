# Security policy

## Reporting a vulnerability

Do not open a public issue. Contact the repository owner directly through a private channel.

## Rules

- No secrets, keys, or connection strings in code or workflow files.
- `local.settings.json` is git-ignored. Use managed identity in Azure.
- Azure sign-in in CI uses OIDC federated credentials only.
- Storage access uses the Function's user-assigned managed identity with Storage Blob Data Contributor on the data lake resource group only.
- Pull requests from forks do not receive Azure credentials.
