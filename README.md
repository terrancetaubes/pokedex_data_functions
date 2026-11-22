# pokedex_data_functions

Azure Functions that extract Pokedex data into Azure Data Lake Storage Gen2. The Function App project is in `function_app/`. Its own README describes the functions and the data layout. Tests are in `tests/`, outside the deployed folder.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # runtime packages plus pytest and ruff
pytest                                   # run from the repository root
cd function_app
cp local.settings.example.json local.settings.json   # never commit this file
func start
```

## CI/CD

- Pull requests and pushes to `develop` or `release/**`: lint, tests, and compile (`ci-cd.yml`).
- Merge to `develop`: deploy the Function App to `dev`.
- Push to `release/<n>`: deploy the Function App to `itg`.

Azure sign-in uses OpenID Connect. No secrets are stored in this repository. Environment settings: `docs/ENVIRONMENTS.md`. Branch flow: `docs/BRANCHING_AND_RELEASE.md` in the project folder.
