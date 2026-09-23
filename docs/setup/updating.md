# Updating this installation

The helper applies the code already in your working directory. It never pulls, switches branches, discards local changes, or starts a server automatically. Run it manually when ready. Keep a separate verified backup of the previous deployed revision before changing code.

## Local Windows / SQLite

1. Save the previous deployed code and record its Git commit. Preserve uncommitted changes; do not use a hard reset to update.
2. Stop the app server and all workers so the database and uploaded files stay consistent.
3. Review the intended new checkout. Check prerequisites with the same Python and settings as your server:

   ```powershell
   .venv\Scripts\python.exe scripts/update_app.py --settings babybuddy.settings.development
   ```

4. Explicitly apply the current checkout:

   ```powershell
   .venv\Scripts\python.exe scripts/update_app.py --settings babybuddy.settings.development --apply --server-stopped
   ```

The helper makes a consistent SQLite backup, checks integrity, archives local media and current tracked/untracked nonignored source files, records the commit, installs hash-verified runtime requirements and npm lockfile dependencies, builds assets, checks Django, applies migrations, and collects static assets. Use your actual production settings module on a production server. `--skip-dependencies` is for an already prepared environment.

Backups default to `data/backups`; `--backup-dir` selects another local directory outside media. Keep backups private: they contain child data and may contain configuration secrets. Copy verified backups to your own protected backup storage. No cloud service is required. Environment-variable secrets and external secret-manager values are not copied; retain those separately.

5. Start the server normally and verify login, dashboard, a report, and a photo. Retain the backup.

## Recovery

Keep the server stopped if the update fails. The helper reports the backup directory and exits unsuccessfully; it does not claim to roll back.

Preserve the failed installation separately. Restore the **previous deployed source revision**, its matching dependency environment, the matching database backup, and local media to the locations in `manifest.json`. The helper archives the working tree when it runs, which may already contain new code; that is not automatically the previous release. Restore private configuration if necessary. Never overwrite a live SQLite database. Account for SQLite WAL/SHM sidecar files while all processes are stopped. Rebuild and collect static assets from the restored code, start, and verify the app. A care-data export is not a full database/media backup.

Practice restoration into a separate directory/database before relying on this procedure for real records.

## PostgreSQL, Docker, and remote media

The helper refuses unsupported backup configurations before applying changes. For PostgreSQL, stop writers, create a `pg_dump` backup using the deployment's credentials, and test `pg_restore` into a separate database. Back up media with its provider. Record container image/version, environment/secret configuration, and persistent volumes. Run checks, migrations, asset build, and static collection in the intended environment before starting writers. Restore matching database, media, and app versions together for recovery.

## Styles and scripts only

```powershell
node node_modules/gulp/bin/gulp.js build
.venv\Scripts\python.exe manage.py collectstatic --noinput --settings=babybuddy.settings.development
```

Use `gulp build`, not the watch/server default, for deployment. Change the offline service-worker cache version when the offline shell/bundles change. Regenerate JavaScript catalogs when new interface text is added.

## Runtime dependency lock

`requirements.txt` is the reviewed list of exact Python runtime versions. `requirements.lock` adds permitted release-file SHA-256 hashes and enables pip's `--require-hashes` mode. Install using `python -m pip install -r requirements.lock`, then run `python scripts/lock_requirements.py` and `python -m pip check`. The update helper and CI use these checks; a mismatched environment is not silently accepted by `--skip-dependencies`.

To change a dependency, deliberately edit its exact pin in `requirements.txt`, review its release/security notes, then run `python scripts/lock_requirements.py --refresh`. This fetches hashes from PyPI for those exact releases without choosing newer versions or installing anything. Install the lock into a clean environment, run the application tests, and commit both files together. The hash uses normalized line endings so Windows/Linux checkouts agree. CI exercises the existing Python-version matrix; local validation currently uses Windows/Python 3.14. Release hashes cover available platforms, but do not themselves prove runtime compatibility.

Pipenv remains available for development tasks. Its broad development-tool dependencies are separate from the application runtime lock; CI reapplies and verifies the runtime lock after installing developer tools. No new package manager is required. Do not use an unlocked `pipenv update` as a production update procedure.
