#!/usr/bin/env bash
set -euo pipefail
: "${RUNNER_TEMP:?This helper runs inside GitHub Actions}"
export THEOS="${THEOS:-$RUNNER_TEMP/theos}"
printf 'THEOS=%s\n' "$THEOS" >> "${GITHUB_ENV:?GitHub environment output path is required}"
strConfig="$(python3 "$GITHUB_WORKSPACE/Source/Tools/Package.py" config "$GITHUB_WORKSPACE")"
mapfile -t aConfig <<< "$strConfig"
strSdk="${aConfig[1]}"
sudo apt-get update
sudo apt-get install -y build-essential fakeroot rsync curl perl zip unzip git libxml2 libtinfo6 ca-certificates xz-utils
if [[ ! -d "$THEOS/.git" ]]; then
    git clone --recursive https://github.com/theos/theos.git "$THEOS"
fi
if [[ ! -x "$THEOS/toolchain/linux/iphone/bin/clang" && ! -x "$THEOS/toolchain/linux/host/bin/clang" ]]; then
    strArchive="$RUNNER_TEMP/TheosToolchain.tar.xz"
    curl --fail --location --silent --show-error --retry 3 \
        "https://github.com/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-$(uname -m).tar.xz" \
        --output "$strArchive"
    mkdir -p "$THEOS/toolchain"
    tar -xJf "$strArchive" -C "$THEOS/toolchain"
fi
if [[ ! -d "$THEOS/sdks/iPhoneOS${strSdk}.sdk" ]]; then
    if ! "$THEOS/bin/install-sdk" "iPhoneOS${strSdk}" > "$RUNNER_TEMP/TheosSdk.log" 2>&1; then
        cat "$RUNNER_TEMP/TheosSdk.log"
        exit 1
    fi
fi
