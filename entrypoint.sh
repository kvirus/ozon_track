#!/bin/sh
set -e

if [ "${HEADLESS:-true}" = "false" ]; then
    exec xvfb-run -a --server-args="-screen 0 1366x900x24" "$@"
fi

exec "$@"
