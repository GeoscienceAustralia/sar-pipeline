#!/bin/bash
set -euo pipefail

OUTFILE="environment.yml"
TMPFILE="$(mktemp)"

# Backup current environment.yml if it exists
cp "$OUTFILE" "$TMPFILE" 2>/dev/null || true

# Run the Pixi task that handles export and renaming
pixi run export-conda &> /dev/null

# Compare the before/after hashes
OLD_HASH=$(sha256sum "$TMPFILE" | cut -d ' ' -f1 2>/dev/null || echo "")
NEW_HASH=$(sha256sum "$OUTFILE" | cut -d ' ' -f1)

rm -f "$TMPFILE"

if [[ "$OLD_HASH" != "$NEW_HASH" ]]; then
  echo "❗ $OUTFILE was updated by 'pixi run export-conda'. Please commit the changes."
  exit 1
else
  echo "✅ $OUTFILE is up to date."
  exit 0
fi