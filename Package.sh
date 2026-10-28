#!/usr/bin/env bash
set -euo pipefail
strRoot="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
strInput="${1:-}"
case "$strInput" in
    [A-Za-z]:/*|[A-Za-z]:\\*)
        strInput="$(wslpath -a -u "${strInput//\\//}")"
        ;;
esac
bash "$strRoot/Build.sh"
python3 "$strRoot/Source/Mod/Package.py" "$strRoot" "$strInput"
