#!/usr/bin/env bash
# Refresh code/ from the working app folders. Never copies the real API key.
# Usage: ./make_export.sh   (run again after any code change)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# folder that holds the working App Lab app folders (qec_lab/, quantum_music/)
SRC="${SRC:-$HOME/Downloads/ArduinoAppLab_0.12.0_Linux_x86-64}"
for app in qec_lab quantum_music; do
  rm -rf "$HERE/code/$app"
  mkdir -p "$HERE/code/$app"
  rsync -a --exclude '__pycache__' --exclude 'ibm_config.json' --exclude 'runs/' --exclude '.cache/' \
    "$SRC/$app/" "$HERE/code/$app/"
  cat > "$HERE/code/$app/python/ibm_config.example.json" <<'JSON'
{
  "token": "YOUR-IBM-QUANTUM-API-KEY",
  "instance": "crn:v1:bluemix:public:quantum-computing:..."
}
JSON
done
# safety check: no real key may leave this machine
if grep -rIl --exclude='*.example.json' -E '"token"\s*:\s*"[A-Za-z0-9_-]{30,}"' "$HERE" ; then
  echo "ERROR: something that looks like a real API token was found (files listed above)" >&2; exit 1
fi
echo "code/ refreshed: $(find "$HERE/code" -type f | wc -l) files, no API keys found"
