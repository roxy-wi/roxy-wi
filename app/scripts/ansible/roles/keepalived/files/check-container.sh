#!/bin/sh
# Keepalived supplies the timeout. Only inspect the configured rootful container.
if [ "$#" -ne 2 ]; then
    echo 'Expected a container engine and name' >&2
    exit 2
fi
case "$1" in
    docker|podman) ;;
    *) echo 'Unsupported container engine' >&2; exit 2 ;;
esac

state=$("$1" container inspect --format '{{.State.Running}} {{.State.Paused}} {{.State.Restarting}}' "$2") || exit 1
[ "$state" = 'true false false' ]
