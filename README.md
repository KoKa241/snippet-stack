# Snippet Stack

A private web application for saving code snippets and terminal commands. Built with Python 3.12, Django 5.2 LTS, SQLite, Gunicorn, and WhiteNoise. The frontend uses server-rendered templates, CSS, and a small amount of vanilla JavaScript, with no npm build, CDN, or external fonts.

## Features

- Registration, login, logout, and a private library for each account.
- Create, edit, delete with confirmation, favorite, and copy complete snippets.
- Comma-separated tags, hybrid search, programming-language filters, sorting, and pagination.
- A dedicated terminal commands section. Saved code is never executed by the application.
- Responsive desktop and mobile layouts, with persistent System, Light, and Dark themes.
- English by default. Open **Settings → Interface language** to switch to Russian. Account preferences follow the user across devices; guest preferences are saved in a browser cookie. The browser's preferred language does not override the English default.
- Editor shortcuts: Tab to indent, Ctrl/⌘ + Enter to save, and a warning before leaving unsaved changes. Press `/` to focus search.
- PWA manifests, PNG icons, and a service worker. Installation requires a compatible browser and HTTPS or localhost. The offline screen follows the last selected interface language; private pages and snippet contents are never cached for offline access.

## Quick start with Docker

Requires a running Docker Engine / Docker Desktop with Compose v2.

```sh
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste the generated value into `SECRET_KEY` in `.env`, then run:

```sh
docker compose up --build -d
```

Open [http://localhost:8000](http://localhost:8000) and create an account. Migrations run on startup. SQLite and downloaded models are stored in the persistent `snippet_data` volume.

```sh
docker compose logs -f web
docker compose logs -f search-indexer
docker compose down
```

`docker compose down -v` deletes the database and model cache. Use ordinary `docker compose down` when stopping the application without deleting its data.

## Ports and environment variables

The default port mapping is `127.0.0.1:8000:8000`: host address, host port, container port. Gunicorn listens on port 8000 inside the container. SQLite and the background indexer do not expose ports. For a different local host port, change the mapping to `127.0.0.1:8080:8000`. To accept connections from other machines, bind the host address to `0.0.0.0` and configure the allowed hostname and firewall accordingly.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Required | A long random Django signing key. Keep it stable across restarts. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames/IPs, without scheme or port. |
| `CSRF_TRUSTED_ORIGINS` | Empty | Comma-separated trusted origins, including scheme and any nonstandard port. |
| `HTTPS` | `false` | Enables HTTPS redirects, secure cookies, and HSTS. TLS is terminated by your reverse proxy. |
| `TRUST_PROXY` | `false` | Trusts `X-Forwarded-Proto` from a controlled reverse proxy. |
| `SEARCH_SEMANTIC_ENABLED` | `true` | Enables local semantic search and background embedding updates. |
| `SEARCH_THREADS` | `2` | ONNX CPU threads per process. |

Compose sets `DEBUG=false`. Direct Django commands do not automatically read `.env`; export variables in your shell. `DATA_DIR` defaults to `data/` locally and `/app/data` in Docker. `SEARCH_MODEL_CACHE` defaults to the `models/` subdirectory of `DATA_DIR`. `SEARCH_MIN_SIMILARITY` defaults to `0.25`. These three advanced variables are supported by Django but are not currently forwarded from `.env` by Compose; add them to the relevant service `environment` sections to override them in Docker.

The interface language is an individual setting in the application, not an environment variable.

## Local development

Requires Python 3.11+:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DEBUG=true
python manage.py migrate
python manage.py runserver
```

The local database is `data/db.sqlite3`. Secrets, runtime data, the virtual environment, and collected static files are excluded from Git and the Docker build context. No application accounts or passwords are built into the repository.

## Checks and tests

```sh
SECRET_KEY=test-only python manage.py collectstatic --noinput
SECRET_KEY=test-only python manage.py test
SECRET_KEY=test-only python manage.py check
node --test tests/theme.test.cjs  # Optional Node.js check for browser theme behavior.
```

Tests cover authentication, snippet CRUD, tags, filtering, pagination, account isolation, CSRF, HTML escaping, POST-only mutations, login throttling, search maintenance, RRF, index migrations, fallback behavior, language preferences, API key lifecycle, API owner isolation, parameter validation, rate limits, encrypted backup round-trips, tamper detection, import validation, and rollback. The real-model semantic test is opt-in and requires an already downloaded model:

```sh
python manage.py index_search
RUN_SEMANTIC_TESTS=1 python manage.py test snippets.test_search
```

It uses an isolated test database, indexes English commands, and verifies Russian queries through BM25, cosine retrieval, RRF, and the results page. Regular tests do not download model files.

## Translation workflow

English strings are the source text. Templates use Django `translate`/`blocktranslate`; Python forms and messages use gettext. Russian translations live in `locale/ru/LC_MESSAGES/django.po`. Django supplies translations for its built-in authentication forms, validation messages, and errors.

After changing translatable strings, install GNU gettext and run:

```sh
python manage.py makemessages --locale ru --ignore .venv --ignore data --ignore staticfiles
# Translate new entries in locale/ru/LC_MESSAGES/django.po.
python manage.py compilemessages --locale ru --ignore .venv
python manage.py build_locale_assets
```

The compiled catalog is included in the repository and rebuilt during Docker image creation. `build_locale_assets` generates `static/i18n/ru.json` and the Russian PWA manifest from the same catalog; Docker runs it before collecting static files. When adding offline messages, register the English source strings in that command. Bump the service worker cache version when changing cached public assets.

Only interface text is translated. User-authored code, titles, descriptions, tags, and search input retain their original content. Cross-language search fixtures intentionally contain Russian queries.

## Production deployment

Put an HTTPS reverse proxy such as Caddy or Nginx in front of the loopback-only application port. Add your domain to `ALLOWED_HOSTS` and its full origin to `CSRF_TRUSTED_ORIGINS`. Keep `127.0.0.1` in `ALLOWED_HOSTS` for the healthcheck.

```dotenv
ALLOWED_HOSTS=snippets.example.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://snippets.example.com
HTTPS=true
TRUST_PROXY=true
```

Enable `TRUST_PROXY` only if the trusted proxy **overwrites** incoming `X-Forwarded-Proto` and direct access to the backend is restricted. For Nginx, use `proxy_set_header Host $host;` and `proxy_set_header X-Forwarded-Proto $scheme;`. Limit request bodies to 256 KiB and rate-limit registration and login at the proxy. Configure the real client IP for django-axes when using a proxy; by default, clients connecting through the same proxy may share an IP lockout.

With `HTTPS=true`, the application enables secure cookies, HTTPS redirects, and HSTS. `/health/` is exempt from redirects and returns database availability only.

```sh
docker compose exec web python manage.py check --deploy
```

Security controls include Django ORM queries, standard password hashing and validation, CSRF protection, automatic HTML escaping, owner checks, a strict Content Security Policy, HttpOnly session and language cookies, and frame embedding restrictions. Five failed login attempts lock an IP for 15 minutes, with shared state in SQLite. Registration is open. Email password recovery and MFA are not implemented.

Containers run without root or Linux capabilities. Dependencies are pinned in `requirements.txt`; keep security patches current. SQLite suits personal libraries and small teams. Writes are serialized; high write concurrency would require a PostgreSQL migration and a review of the SQLite-specific search implementation.

## SQLite backups

Use SQLite's backup API to create a consistent snapshot:

```sh
docker compose exec web python -c "import sqlite3; source=sqlite3.connect('/app/data/db.sqlite3'); target=sqlite3.connect('/app/data/backup.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose cp web:/app/data/backup.sqlite3 ./backup.sqlite3
```

Backups contain private code, account preferences, and password hashes. Store them outside public access. To restore, stop **both** services, replace `db.sqlite3` in the volume with the backup while preserving container-user ownership, then restart. Back up before upgrading.

## Hybrid search: BM25 + vectors + RRF

Enter a phrase such as `kill the process on port 8080` in the search field.

1. **SQLite FTS5 / BM25** searches the title, description, full code, and tags, weighted 4 / 2 / 1 / 3. Tokens use OR with prefix matching. User input cannot inject FTS operators. This is token-based retrieval, without Russian morphological analysis.
2. **FastEmbed / ONNX Runtime on CPU** encodes the query using `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` with 384 dimensions. The multilingual model supports Russian queries against English descriptions. A document combines its title, description, tags, and code; long inputs are truncated to the model window, while FTS still indexes the full code. A short description of a command's purpose improves semantic retrieval.
3. **Cosine similarity** compares normalized vectors within the current user's library after applying all filters. NumPy performs exact retrieval in batches of 256 vectors, without a separate vector server or ANN extension. This has linear complexity in the filtered library size; millions of entries would require a different vector index.
4. **Reciprocal Rank Fusion** combines up to 100 candidates per branch using `score(d) = sum(1 / (60 + rank(d)))`, with ranks starting at 1. Up to 200 candidates are returned in relevance order by default. Title/date sorting applies to the retrieved candidates. The default cosine threshold of 0.25 is a heuristic, not a confidence probability.

Vectors are stored in SQLite. The application does not run an LLM, execute saved commands, or send snippets/query text to an external inference API. The background indexer downloads the model from Hugging Face once and stores it in the shared data volume. The first download requires internet access, disk space, and potentially several minutes. Web workers only load local model files; downloads never happen inside HTTP requests. Each Gunicorn worker and the indexer keep a separate model instance in memory. The first semantic request includes model loading; up to 128 query vectors are cached in each worker's memory.

### Index maintenance

`docker compose up --build -d` starts `web` and `search-indexer`. The indexer waits for migrations and a successful web healthcheck, then polls for changed documents every three seconds. Inference runs outside write transactions; results are saved only if the document has not changed during inference. The keyword index updates immediately with snippet and tag changes. If the model is unavailable or inference fails, keyword search remains available and the interface reports the semantic search status.

```sh
docker compose logs -f search-indexer
# Repair documents after bulk imports/QuerySet.update() and recompute all vectors:
docker compose exec web python manage.py index_search --rebuild
```

For local development, use the same `SECRET_KEY` and `DATA_DIR` environment as the web process:

```sh
python manage.py migrate
python manage.py index_search          # Download the model and index existing snippets.
python manage.py index_search --watch  # Keep running in a separate terminal.
```

`SEARCH_SEMANTIC_ENABLED=false` disables semantic search. `SEARCH_THREADS=2` limits ONNX threads per process. Actual latency depends on CPU, input length, library size, and warm-up; a fixed 20 ms is not guaranteed. After changing the model or embedding algorithm, recompute all vectors with `index_search --rebuild` to avoid mixing embedding spaces. The model is fixed in settings in this version.

In a six-snippet development smoke test, the Russian equivalents of “kill the process on port 8080” and “free the occupied port” ranked `lsof -ti:8080 | xargs kill -9` first. Warm query encoding took around 3–4 ms; loading the model and encoding the corpus took around 600 ms. This is a local smoke test, not a load benchmark or latency guarantee.

## Repository structure

- `config/`: settings, routes, and WSGI entry point.
- `snippets/`: models, forms, views, search, indexer commands, migrations, and tests.
- `templates/`: library, editor, settings, registration, and login pages.
- `locale/`: Django translation catalogs.
- `static/`: styles, JavaScript, translation assets, icons, and PWA resources.
- `Dockerfile`, `compose.yaml`: deployment with persistent SQLite storage.

References: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [SQLite FTS5](https://www.sqlite.org/fts5.html), [FastEmbed models](https://qdrant.github.io/fastembed/examples/Supported_Models/).

## Appearance

Open **Settings → Appearance** and select **System**, **Light**, or **Dark**. System is the default and follows device appearance changes automatically. The preference is saved in this browser. The three-position control supports keyboard navigation and reduced-motion preferences.

## Read-only API

In **Settings → API keys**, create a named key with a 30-day, 90-day, or one-year lifetime. Copy it immediately: the full key is shown only once. Only its SHA-256 digest and identifying prefix are stored. Each account can have up to 10 active keys. Revoke a key from the same panel to prevent further requests.

Use HTTPS in production. Send the key in the `Authorization` header, never in a URL. Browser sessions do not authenticate API requests. Keys can only search and read their owner's snippets; they cannot modify data.

```sh
# Set SNIPPET_STACK_API_KEY securely in your environment first.
curl --get 'https://your-server.example/api/v1/snippets/' \
  --header "Authorization: Bearer $SNIPPET_STACK_API_KEY" \
  --data-urlencode 'q=free port 8080' \
  --data-urlencode 'language=shell'

curl 'https://your-server.example/api/v1/snippets/42/' \
  --header "Authorization: Bearer $SNIPPET_STACK_API_KEY"
```

`GET /api/v1/snippets/` lists or searches snippets with the same BM25 + vector + RRF ranking and keyword fallback as the web UI.

| Parameter | Meaning |
| --- | --- |
| `q` | Optional query, up to 200 characters; omit to list snippets |
| `language` | Exact snippet language identifier, such as `shell` or `python` |
| `tag` | Tag name, up to 32 characters |
| `favorite` | `true` or `false`; omit for both |
| `sort` | `relevance` (default), `updated`, or `title` |
| `page` | Page number, starting at 1 |
| `page_size` | Results per page, 1–50; default 20 |

The response contains `count`, `page`, `page_size`, `next_page`, `previous_page`, `semantic_status`, and `results`. Each result includes `id`, `title`, `description`, full `code`, `language`, `favorite`, `tags`, `created_at`, and `updated_at`. Search counts refer to retrieved candidates (up to 200), not the entire library. `GET /api/v1/snippets/{id}/` returns one such object. Unknown IDs and other users' snippets both return 404.

Errors use `{"error": {"code": "…", "message": "…"}}`: 400 for invalid parameters, 401 for invalid/expired/revoked keys, 404 for missing records/pages, 405 for unsupported methods, and 429 for rate limits. Each key allows 60 requests per fixed 60-second window, shared across web workers through the database. Successful authenticated responses include `X-RateLimit-Limit` and `X-RateLimit-Remaining`; 429 includes `Retry-After` in seconds. Responses are marked `Cache-Control: no-store`. No additional environment variables or services are required.

After updating an existing installation, run migrations (the Docker entrypoint does this automatically):

```sh
python manage.py migrate
```

## Encrypted export and import

Open **Settings → Export & import**. Choose a separate archive password of at least 12 characters and download the `.ssbackup` file. It contains only your snippets, their tags, favorites, and creation/update dates. Account credentials, API keys, preferences, and derived search indexes are excluded. Keep the password separately: there is no password recovery for archives.

Upload the file with its password to restore into the currently signed-in account, including on another Snippet Stack installation. Import adds entries, never overwrites or deletes existing ones, and skips duplicates matching title, description, code, language, favorite status, and tags (dates do not affect matching). All rows are validated before an atomic database transaction; wrong passwords, altered files, unsupported formats, and invalid records leave your library unchanged. Keyword search updates immediately; the background indexer rebuilds vectors.

The portable v1 format uses AES-256-GCM with authenticated version/salt/nonce headers, random 16-byte salts and 12-byte nonces, and Argon2id password derivation (64 MiB, 3 passes, 4 lanes). Parameters are fixed by the version, not supplied by uploaded files. The cryptographic primitives come from [cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/). Archives are not compressed and contain UTF-8 JSON, never pickle or executable content. Each operation supports up to 2,000 snippets and a 10 MiB encrypted archive. Larger libraries need the database backup procedure above.

Encryption/decryption occurs on the server: use HTTPS for remote access. Passwords and plaintext exports are not deliberately persisted to disk or the database; uploaded ciphertext may use Django's temporary upload storage. Endpoints require a signed-in browser session, POST, and CSRF protection; read-only API keys cannot export or import. No new environment variables are needed. If your reverse proxy limits request bodies, allow at least 11 MiB for multipart uploads. Rebuild the Docker image to install the new cryptography dependency.
