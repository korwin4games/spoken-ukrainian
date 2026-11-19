# Run the test suite in Docker

Run these commands from the repository root in PowerShell with Docker Desktop running in Linux containers mode. Set `$spoken` to a clean, standalone host Git checkout at the Spoken revision in `sources.lock.json`. Use a checkout with Git's original line endings (`core.autocrlf=false` when checking out the pin). The image build downloads the public base images and installs the Ubuntu test dependencies. The test run works offline.

```powershell
New-Item -ItemType Directory -Force build | Out-Null
git -c core.autocrlf=false archive --format=tar -o build/docker-tests-source.tar HEAD
docker build --tag spoken-ukrainian-tests tools/docker-tests
$archive = (Resolve-Path build/docker-tests-source.tar).Path
$spoken = (Resolve-Path ../spoken-wow).Path
docker run --rm --network none `
  --mount "type=bind,source=$archive,target=/input/source.tar,readonly" `
  --mount "type=bind,source=$spoken,target=/input/spoken-wow,readonly" `
  spoken-ukrainian-tests
```

Pass another commit or branch to `git archive` to test it. The archive contains committed Git files with their original line endings. The container receives the archive and pinned checkout read-only. It writes the Python environment, diagnostic ZIP, and synthetic test data inside the disposable container.

The runner uses Ubuntu 24.04, Python 3.12, Lua 5.4, Node.js, and `uv`. It checks the project version, builds the diagnostic ZIP, and runs the frontend and Python suites. GitHub CI also runs pinned-source integration checks and local Quest/Gossip package builds beyond this test runner.

## Check the host SQLite database

Keep the real database and voice files in their existing host directories. The test suite uses synthetic SQLite databases and requires no voice mount. To check your stored review database, set `$database` to the actual host file, using the same path as your normal `SPOKEN_TRANSLATION_DB` setting. Close the review manager before running the read-only check.

```powershell
$database = (Resolve-Path 'D:/path/to/translations.sqlite3').Path
$databaseDirectory = Split-Path -Parent $database
$databaseName = Split-Path -Leaf $database
docker run --rm --network none `
  --mount "type=bind,source=$archive,target=/input/source.tar,readonly" `
  --mount "type=bind,source=$databaseDirectory,target=/database,readonly" `
  --env "SPOKEN_TRANSLATION_DB=/database/$databaseName" `
  spoken-ukrainian-tests db-status
```

The status command prints ledger revisions and translation counts from the mounted database. It opens SQLite in read-only mode and leaves the database and any companion files in the host directory.
