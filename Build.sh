#!/usr/bin/env bash
set -euo pipefail
strRoot="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export THEOS="${THEOS:-$HOME/theos}"
if [[ ! -f "$THEOS/makefiles/common.mk" ]]; then
    printf 'Theos not found at %s. Set THEOS to your installation directory.\n' "$THEOS" >&2
    exit 1
fi
if [[ "$strRoot" == *" "* || "$THEOS" == *" "* ]]; then
    printf 'Theos requires project and toolchain paths without spaces.\n' >&2
    exit 1
fi
strConfig="$(python3 "$strRoot/Source/Tools/Package.py" config "$strRoot")"
mapfile -t aConfig <<< "$strConfig"
make -C "$strRoot/Source/Mod" FINALPACKAGE=1 \
    "MOD_NAME=${aConfig[0]}" "MOD_SDK=${aConfig[1]}" \
    "MOD_MIN_IOS=${aConfig[2]}" "MOD_CXX_STANDARD=${aConfig[3]}" "$@"
strOutput="$strRoot/Build/Release/${aConfig[0]}.dylib"
mkdir -p "$(dirname -- "$strOutput")"
cp "$strRoot/Source/Mod/.theos/obj/${aConfig[0]}.dylib" "$strOutput"
printf 'Built: %s\n' "$strOutput"
