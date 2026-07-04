#!/bin/sh
set -e

if [ "$(id -u)" != "0" ]; then
  exec gosu root "$@"
fi

exec "$@"
