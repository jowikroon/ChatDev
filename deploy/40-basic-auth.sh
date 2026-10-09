#!/bin/sh
# Generate the basic-auth file from CHATDEV_USER / CHATDEV_PASSWORD.
# Refuse to start without a password: the backend executes agent-written code.
set -eu
if [ -z "${CHATDEV_PASSWORD:-}" ]; then
  echo "CHATDEV_PASSWORD is not set; refusing to serve ChatDev without login" >&2
  exit 1
fi
umask 077
printf '%s:%s\n' "${CHATDEV_USER:-admin}" "$(cryptpw -m sha512 "$CHATDEV_PASSWORD")" > /etc/nginx/.htpasswd
chown nginx /etc/nginx/.htpasswd
