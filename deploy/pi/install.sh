#!/usr/bin/env bash
# Install or update Baby Buddy on a Raspberry Pi (Raspberry Pi OS, 64-bit
# recommended). Safe to re-run: an existing install is updated in place.
#
#   sudo REPO=https://github.com/<you>/babybuddy.git BRANCH=fix/local-bugs \
#        bash deploy/pi/install.sh
#
# Override HOSTNAMES / TIME_ZONE below (or in /etc/babybuddy/babybuddy.env
# afterwards) to match your network.
set -euo pipefail

REPO="${REPO:-https://github.com/babybuddy/babybuddy.git}"
BRANCH="${BRANCH:-master}"
APP_DIR="${APP_DIR:-/opt/babybuddy/app}"
ENV_DIR=/etc/babybuddy
ENV_FILE="$ENV_DIR/babybuddy.env"
SERVICE_USER=babybuddy
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOSTNAMES="${HOSTNAMES:-$(hostname).local,$(hostname),${LAN_IP},localhost,127.0.0.1}"
TIME_ZONE="${TIME_ZONE:-$(cat /etc/timezone 2>/dev/null || echo UTC)}"

if [[ $EUID -ne 0 ]]; then
  echo "run with sudo" >&2
  exit 1
fi

echo "==> system packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  git python3 python3-venv python3-dev build-essential nginx \
  libjpeg-dev zlib1g-dev libopenjp2-7-dev libpq-dev

echo "==> service user and directories"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home /opt/babybuddy --shell /usr/sbin/nologin "$SERVICE_USER"
mkdir -p "$(dirname "$APP_DIR")" "$ENV_DIR"

echo "==> source ($REPO @ $BRANCH)"
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" checkout --quiet "$BRANCH"
  git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/data" "$APP_DIR/media"

echo "==> python environment"
[[ -x "$APP_DIR/.venv/bin/python" ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> environment file"
if [[ ! -f "$ENV_FILE" ]]; then
  SECRET_KEY="$("$APP_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"
  ORIGINS="$(echo "$HOSTNAMES" | tr ',' '\n' | sed 's#^#http://#' | paste -sd, -)"
  sed -e "s#^SECRET_KEY=.*#SECRET_KEY=$SECRET_KEY#" \
      -e "s#^ALLOWED_HOSTS=.*#ALLOWED_HOSTS=$HOSTNAMES#" \
      -e "s#^CSRF_TRUSTED_ORIGINS=.*#CSRF_TRUSTED_ORIGINS=$ORIGINS#" \
      -e "s#^TIME_ZONE=.*#TIME_ZONE=$TIME_ZONE#" \
      "$APP_DIR/deploy/pi/babybuddy.env.example" > "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  chown root:"$SERVICE_USER" "$ENV_FILE"
  echo "    wrote $ENV_FILE (ALLOWED_HOSTS=$HOSTNAMES)"
else
  echo "    keeping existing $ENV_FILE"
fi

echo "==> database"
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
cd "$APP_DIR"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py createcachetable
# Static assets are committed to the repo (static/) and served by WhiteNoise,
# so collectstatic is only needed after rebuilding the front end with gulp.

chown -R "$SERVICE_USER":"$SERVICE_USER" /opt/babybuddy
chmod 750 "$APP_DIR/data"

echo "==> services"
install -m 644 "$APP_DIR/deploy/pi/babybuddy.service" /etc/systemd/system/babybuddy.service
install -m 644 "$APP_DIR/deploy/pi/nginx-babybuddy.conf" /etc/nginx/sites-available/babybuddy
ln -sf /etc/nginx/sites-available/babybuddy /etc/nginx/sites-enabled/babybuddy
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --quiet babybuddy
systemctl restart babybuddy
systemctl reload nginx

echo
echo "Baby Buddy is up: http://$(hostname).local/  (or http://${LAN_IP}/)"
echo "First login is admin / admin. Change the password immediately (user menu)."
echo "Logs: journalctl -u babybuddy -f"
