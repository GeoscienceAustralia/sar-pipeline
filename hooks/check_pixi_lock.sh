#!/bin/bash
set -euo pipefail

LOCKFILE="pixi.lock"
MANIFEST="pyproject.toml"

if [[ ! -f "$LOCKFILE" || ! -f "$MANIFEST" ]]; then
  echo "Required files missing: $LOCKFILE or $MANIFEST" >&2
  exit 1
fi

# Capture the checksum of the lockfile before
BEFORE_HASH=$(sha256sum "$LOCKFILE" | cut -d ' ' -f1)

pixi install &> /dev/null

# Capture the checksum of the lockfile after
AFTER_HASH=$(sha256sum "$LOCKFILE" | cut -d ' ' -f1)

if [[ "$BEFORE_HASH" != "$AFTER_HASH" ]]; then
  echo "❗ $LOCKFILE was out of date and has been updated. Please commit the changes."
  exit 1
else
  echo "✅ $LOCKFILE is up to date."
  exit 0
fi