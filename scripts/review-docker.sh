#!/usr/bin/env bash
set -euo pipefail

CONTAINER_UID=10001
XAUTH_COPY="${XDG_RUNTIME_DIR:-/tmp}/lector-review.xauth"

if [ -z "${DISPLAY:-}" ]; then
    echo "review-docker: no hay pantalla X (DISPLAY vacía)" >&2
    exit 1
fi
case "$DISPLAY" in
    :*) ;;
    *)
        echo "review-docker: solo se admiten pantallas locales (DISPLAY=:N)" >&2
        exit 1
        ;;
esac
for cmd in xauth setfacl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "review-docker: falta $cmd; instale xauth y acl" >&2
        exit 1
    fi
done

DISPLAY_NUM="${DISPLAY#:}"
DISPLAY_NUM="${DISPLAY_NUM%%.*}"
SOCKET="/tmp/.X11-unix/X${DISPLAY_NUM}"
if [ ! -S "$SOCKET" ]; then
    echo "review-docker: no existe el socket $SOCKET" >&2
    exit 1
fi

cleanup() {
    setfacl -x "u:${CONTAINER_UID}" "$SOCKET" || true
    rm -f "$XAUTH_COPY" || true
}
trap cleanup EXIT

rm -f "$XAUTH_COPY"
(umask 077 && : > "$XAUTH_COPY")
xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f "$XAUTH_COPY" nmerge -
setfacl -m "u:${CONTAINER_UID}:r" "$XAUTH_COPY"

setfacl -m "u:${CONTAINER_UID}:rw" "$SOCKET"

cd "$(dirname "$0")/.."
set +e
LECTOR_XAUTH="$XAUTH_COPY" docker compose --profile review run --rm lector-review lector review "$@"
status=$?
set -e
exit "$status"
