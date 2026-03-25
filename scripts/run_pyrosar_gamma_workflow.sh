#!/usr/bin/env bash

scene=""

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scene) scene="$2"; shift 2 ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

# Check if 'scene' is provided
if [[ -z "$scene" ]]; then
    echo "Error: --scene is a required parameter."
    exit 1
fi

echo ""
echo The input variables are:
echo scene : "$scene"

# run the cli with pixi
pixi run pyrosar-gamma-rtc-run-workflow --scene "$scene"