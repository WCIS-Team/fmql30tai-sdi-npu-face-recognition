#!/bin/sh
# POSIX shell entry. Both entry points use the same Python 3.8 implementation.
set -eu
case "$0" in
    */*) SCRIPT_PARENT=${0%/*} ;;
    *) SCRIPT_PARENT=. ;;
esac
SCRIPT_DIR=$(CDPATH='' cd -- "$SCRIPT_PARENT" && pwd -P)
if [ -n "${PYTHON38:-}" ]; then
    PYTHON_BIN=$PYTHON38
elif command -v python3.8 >/dev/null 2>&1; then
    PYTHON_BIN=python3.8
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
else
    printf '%s\n' 'Python 3.8 is required. Set PYTHON38 to its executable path.' >&2
    exit 2
fi
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 8) else 1)'; then
    printf '%s\n' 'Please use Python 3.8.x; set PYTHON38=/path/to/python3.8 and retry.' >&2
    exit 2
fi
# Handle MSYS paths even when its automatic native-argument conversion is disabled.
SCRIPT_FILE=$("$PYTHON_BIN" -c 'import os,re,sys; p=sys.argv[1]; print(re.sub(r"^/([A-Za-z])/", lambda m:m.group(1)+":/", p) if os.name=="nt" else p)' "$SCRIPT_DIR/install_py38.py")
export PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON_BIN" -B -X utf8 "$SCRIPT_FILE" "$@"
