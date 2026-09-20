# Baby Buddy on a Raspberry Pi

Runs this repository on Raspberry Pi OS (Bookworm or newer, 64-bit
recommended) with gunicorn behind nginx and an SQLite database. A Pi 3 or
newer is plenty for a household.

## Install

On the Pi:

```bash
git clone --branch fix/local-bugs https://github.com/<your-fork>/babybuddy.git
sudo REPO=https://github.com/<your-fork>/babybuddy.git BRANCH=fix/local-bugs \
     bash babybuddy/deploy/pi/install.sh
```

The script installs system packages, creates a `babybuddy` service user,
clones the app to `/opt/babybuddy/app`, builds a virtualenv from
`requirements.txt`, generates a `SECRET_KEY`, migrates the database and
enables the `babybuddy` systemd service plus an nginx site on port 80.

It then prints the URL. First login is `admin` / `admin`; change the password
straight away (user menu, top right).

Optional variables for the first run:

| variable    | default                                | purpose                        |
| ----------- | -------------------------------------- | ------------------------------ |
| `HOSTNAMES` | `<hostname>.local,<hostname>,<LAN IP>` | `ALLOWED_HOSTS` / CSRF origins |
| `TIME_ZONE` | the Pi's `/etc/timezone`               | default timezone for new users |
| `APP_DIR`   | `/opt/babybuddy/app`                   | install location               |

## Configure

All settings live in `/etc/babybuddy/babybuddy.env` (see
`babybuddy.env.example` here and `docs/configuration/`). After editing:

```bash
sudo systemctl restart babybuddy
```

## Update

Re-run the install script with the same `REPO`/`BRANCH`; it fetches, installs
any new requirements, migrates and restarts. The env file is kept.

## Operate

```bash
journalctl -u babybuddy -f        # application log
sudo systemctl status babybuddy   # service state
```

Back up `/opt/babybuddy/app/data/db.sqlite3` and `/opt/babybuddy/app/media/`
(pictures). Copying them onto a fresh install restores everything.

## HTTPS

If you put the Pi behind a TLS terminator (or add certbot to nginx), set the
three commented `SECURE_*` / `*_COOKIE_SECURE` lines in the env file and change
`CSRF_TRUSTED_ORIGINS` to the `https://` origin.
