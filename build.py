#!/usr/bin/env python3
"""Generate src/scripts/sync.sh from src/scripts/sync.py.

The orb packer inlines a whole file as the value of `command:`, and that value
has to be shell. So the shell wrapper carries the Python program inside a
heredoc. Keeping one source file and generating the wrapper stops the two
copies from drifting apart.

Run this before `circleci orb pack`.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY_PATH = os.path.join(HERE, "src", "scripts", "sync.py")
SH_PATH = os.path.join(HERE, "src", "scripts", "sync.sh")
MARKER = "ASYNTAI_SYNC_PY_EOF"

HEADER = """#!/usr/bin/env bash
# GENERATED FILE. Do not edit.
# Made by build.py from src/scripts/sync.py.
set -euo pipefail

KEY_VAR="${ASYNTAI_ORB_KEY_VAR:-ASYNTAI_API_KEY}"
ASYNTAI_API_KEY="${!KEY_VAR:-}"
export ASYNTAI_API_KEY

if [ -z "$ASYNTAI_API_KEY" ] && [ "${ASYNTAI_ORB_DRY_RUN:-false}" != "true" ]; then
  echo "Error: the environment variable $KEY_VAR is empty." >&2
  echo "Add your Asyntai API key to the CircleCI project settings or to a context." >&2
  exit 1
fi

PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Error: this step needs Python 3, and the image has neither python3 nor python." >&2
  echo "Run the step in an image that holds Python 3, for example cimg/python." >&2
  exit 1
fi

SCRIPT_FILE="$(mktemp -t asyntai-sync-XXXXXX.py)"
trap 'rm -f "$SCRIPT_FILE"' EXIT

cat > "$SCRIPT_FILE" <<'@@MARKER@@'
@@BODY@@
@@MARKER@@

ARGS=(
  --path "$ASYNTAI_ORB_PATH"
  --patterns "${ASYNTAI_ORB_PATTERNS:-*.md,*.mdx,*.txt}"
  --exclude "${ASYNTAI_ORB_EXCLUDE:-}"
  --title-prefix "${ASYNTAI_ORB_TITLE_PREFIX:-}"
  --website-id "${ASYNTAI_ORB_WEBSITE_ID:-}"
  --base-url "${ASYNTAI_ORB_BASE_URL:-https://asyntai.com}"
)

if [ "${ASYNTAI_ORB_PRUNE:-false}" = "true" ]; then
  ARGS+=(--prune)
fi

if [ "${ASYNTAI_ORB_DRY_RUN:-false}" = "true" ]; then
  ARGS+=(--dry-run)
fi

"$PYTHON_BIN" "$SCRIPT_FILE" "${ARGS[@]}"
"""


def main():
    with open(PY_PATH, "r", encoding="utf-8") as handle:
        body = handle.read().rstrip("\n")

    if MARKER in body:
        print("Error: sync.py contains the heredoc marker %s." % MARKER,
              file=sys.stderr)
        return 1

    text = HEADER.replace("@@MARKER@@", MARKER).replace("@@BODY@@", body)

    with open(SH_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)

    print("Wrote %s (%d bytes)." % (SH_PATH, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
