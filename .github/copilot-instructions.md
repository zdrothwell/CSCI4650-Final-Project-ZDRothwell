<!-- Copilot instructions for CSCI4650 Final Project: CloudGallery -->
# Copilot / AI Agent Instructions

This file contains concise, actionable guidance for AI coding agents working on this repository.

## Big picture
- Web app: a small Flask server (`app.py`) that renders templates in `templates/` and serves static CSS from `static/`.
- Auth: AWS Cognito is used for signup/login (see `app.py` and `deploy_all.py`). Agents should not hardcode credentials; use environment variables.
- Storage: Images are uploaded to an S3 bucket (`s3.upload_fileobj` in `app.py`); the app builds S3 URLs as `https://{S3_BUCKET}.s3.amazonaws.com/{key}`.
- Database: MySQL (RDS). `create_tables.sql` describes the `images` table (fields: `id, user_email, image_url, title, description, upload_date`). The app inserts into `images` during upload and reads for the gallery.

## Key files to inspect (quick hits)
- `app.py` — primary application code and the best single-file summary of routes and env vars.
- `create_tables.sql` — canonical DB schema for `images`.
- `deploy_all.py` — infra helper that creates S3, Cognito, RDS and writes `./config/*.json` (note: RDS creation is asynchronous).
- `setup_env.py` — helper that writes a sample `.env`. Running `python setup_env.py` writes a `.env` with placeholder values.
- `deploy.sh` — a simple deployment script (fetch + pip install + restart). It assumes UNIX tooling (not PowerShell); be careful on Windows.

## Environment & runtime
- The app reads these environment variables (defined in `app.py`):
  - `AWS_REGION`, `S3_BUCKET`
  - `RDS_HOST`, `RDS_USER`, `RDS_PASS`, `RDS_DB`
  - `COGNITO_POOL_ID`, `COGNITO_CLIENT_ID`
- Use `setup_env.py` to generate a starter `.env` and populate values before running locally.

Local run example:
```
python setup_env.py    # generates .env with sample placeholders
# edit .env or set env vars for your environment
python app.py
# then open http://localhost:5000
```

Notes:
- `requirements.txt` lists `flask`, `boto3`, `mysql-connector-python`, `python-dotenv`.
- `deploy_all.py` writes `./config/aws_config.json` and `./config/db_config.json`; those files are generated artifacts and should generally not be edited directly by agents unless updating generator logic.

## Typical data flows (examples)
- Upload flow (see `app.py` `/upload` POST):
  - Authenticated user in session uploads a file + metadata.
  - Server generates `unique_name = f"{uuid.uuid4()}_{file.filename}"` and calls `s3.upload_fileobj(file, S3_BUCKET, unique_name)`.
  - File URL saved: `https://{S3_BUCKET}.s3.amazonaws.com/{unique_name}`.
  - Insert into `images(user_email, image_url, title, description)`.

## Conventions & project-specific patterns
- Session-based auth: `session['username']` is set after successful Cognito `initiate_auth` and used for access control — check for `if 'username' not in session` before protected pages.
- Database access: `get_db()` returns a `mysql.connector` connection (no connection pooling). Close cursors and connections after use (the app already does this pattern).
- Config files in `./config` are produced by `deploy_all.py`; treat them as generated.
- Templates use Jinja2 and assume `images` rows provide `image_url`, `title`, `description`, `user_email`, and `upload_date`.

## Integration points & external dependencies
- AWS: S3, Cognito, RDS (MySQL). Tests or changes that touch infra should avoid making destructive AWS calls unless explicitly asked.
- Local development: env vars or `.env` (via `setup_env.py`). Do not commit credentials.

## Debugging & developer workflows
- To reproduce issues locally, ensure `.env` is populated and that `RDS_HOST` points to an accessible MySQL instance (the app expects a real DB).
- For infra provisioning, `deploy_all.py` creates the resources and writes configs; RDS provisioning is asynchronous — `deploy_all.py` will return before the instance is available. Agents should not assume immediate DB connectivity after running it.
- `deploy.sh` is a convenience script intended for Unix-like systems to restart the app; on Windows use PowerShell equivalents and ensure you stop any running Python processes first.

## Safety notes & small gotchas discovered
- `config/aws_config.json` and `config/db_config.json` may be empty placeholders in the repo; `deploy_all.py` populates them.
- The app builds public S3 URLs; if S3 bucket policy is private, the URL will not work. Consider signed URLs if privacy is required.
- Cognito exceptions are caught broadly; be careful when changing auth logic — `ClientError` is used in a few places.

## Examples for quick code edits
- Adding a new column to the `images` table: update `create_tables.sql`, then update `app.py` insert and template references.
- Changing S3 key format: update the `unique_name` generation in `/upload` and any code that constructs `file_url`.

## Where not to change things without approval
- `deploy_all.py` has infra creation logic. Modify only if the task explicitly requires infra changes.
- `config/*.json` are generated; change the generator (`deploy_all.py`) instead of editing the written files.

If anything above is unclear or you'd like me to surface more examples (e.g., exact lines in `app.py` to modify for X), tell me which area to expand and I'll iterate.
