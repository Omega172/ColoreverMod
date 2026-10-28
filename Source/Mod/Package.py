import bz2
import hashlib
import importlib.util
import json
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

pstSpec = importlib.util.spec_from_file_location("shared_package", Path(__file__).parents[1] / "Tools/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)
pstRuntimeSpec = importlib.util.spec_from_file_location("runtime_patcher", Path(__file__).with_name("RuntimePatcher.py"))
runtime = importlib.util.module_from_spec(pstRuntimeSpec)
pstRuntimeSpec.loader.exec_module(runtime)


STR_ANORTX_SHA256 = "b683b53d91678850ff80515bff81cdf6af62f3852fdcfca79cc5e2d7cebcd540"
A_PROTECTION_HOOKS = (
    ("VM byte-store handler", 0x1E15C, "f657bda9"),
    ("Self-kill helper", 0x3D6A4, "fd7bbfa9"),
    ("Native poison helper", 0x3F8DC, "fd7bbfa9"),
    ("Native validation", 0x4288C, "f657bda9"),
)
A_PROTECTION_PREFIXES = (
    (0x3D6A4, "fd7bbfa9fd03009152260094210180522627ff9720008052902bff9720008052fd7bc1a88d2bff17"),
    (0x3F8DC, "fd7bbfa9fd030091d1ffff9720010034"),
    (0x4288C, "f657bda9f44f01a9fd7b02a9fd830091"),
)


def apply_signing_compatibility(byImage):
    if hashlib.sha256(byImage).hexdigest() != STR_ANORTX_SHA256:
        raise ValueError("anortx does not match the inspected Colorever 1.23.0 build")
    for uOffset, strExpected in A_PROTECTION_PREFIXES:
        byExpected = bytes.fromhex(strExpected)
        if byImage[uOffset:uOffset + len(byExpected)] != byExpected:
            raise ValueError("Unexpected protection function instructions")
    byPatched, stReport = runtime.apply_runtime_hooks(byImage, A_PROTECTION_HOOKS, "OmegaProtectionHook")
    stReport["feature"] = "C++ runtime protection and file-write compatibility handlers"
    return byPatched, stReport


def exported_symbols(byLibrary):
    aExports = set()
    for uCommand, uOffset, uSize in mod.commands(byLibrary):
        if uCommand != 2:
            continue
        uSymbols, uCount, uStrings, uLength = struct.unpack_from("<4I", byLibrary, uOffset + 8)
        for uIndex in range(uCount):
            uName, uType, uSection, uDescription, uAddress = struct.unpack_from("<IBBHQ", byLibrary, uSymbols + uIndex * 16)
            if uType & 1 and uType & 0xE == 0xE:
                aExports.add(byLibrary[uStrings + uName:uStrings + uLength].split(b"\0", 1)[0].decode())
    return aExports


STR_UNITY_SHA256 = "9e9639d5f535ee0ca1aaa780b427bad1964ab6f4c0ebf2fe688e4317346a5382"
A_POWERUP_PATCHES = (
    ("Hint count", 0x31658E0, "001140b9"),
    ("Shuffle count", 0x31659AC, "001540b9"),
    ("Temporary expansion count", 0x3165A78, "001940b9"),
    ("Hint availability", 0x3165C90, "001140b9"),
    ("Shuffle availability", 0x3165CE4, "001540b9"),
    ("Temporary expansion availability", 0x3165D38, "001940b9"),
    ("Preserve hint inventory", 0x3166580, "a902134b"),
    ("Preserve shuffle inventory", 0x3166700, "a902134b"),
    ("Preserve temporary expansion inventory", 0x3166798, "a902134b"),
)


def apply_powerups(byImage):
    if hashlib.sha256(byImage).hexdigest() != STR_UNITY_SHA256:
        raise ValueError("UnityFramework does not match the inspected Colorever 1.23.0 build")
    return runtime.apply_runtime_hooks(byImage, A_POWERUP_PATCHES, "OmegaGameplayHook")


STR_SETTINGS_ORIGINAL_SHA256 = "c83bcb081535a7f5f2173b2135108e17faac3cd9ae4ccfa99156eaabe245805f"
STR_SETTINGS_PATCHED_SHA256 = "83260df69f4b17cecda78dfe3f4e8babd0a7d06714d00646a82e88611d74d693"
STR_SETTINGS_BUNDLE = "local_ui_1e99c94b80210a15e38fec7b0f3dce1a.ab"
STR_SETTINGS_MESSAGE = "I bypassed your fuck-ass VM-based protection ~ Omega172"


def delta_integer(byValue):
    if len(byValue) != 8:
        raise ValueError("Truncated settings asset delta")
    uValue = int.from_bytes(byValue, "little")
    return -(uValue & ((1 << 63) - 1)) if uValue >> 63 else uValue


def apply_asset_delta(byOriginal, byPatch):
    if byPatch[:8] != b"BSDIFF40" or len(byPatch) < 32:
        raise ValueError("Invalid settings asset delta")
    iControlLength, iDiffLength, iSize = (delta_integer(byPatch[uOffset:uOffset + 8]) for uOffset in (8, 16, 24))
    if min(iControlLength, iDiffLength, iSize) < 0 or iSize > 16 * 1024 * 1024 or 32 + iControlLength + iDiffLength > len(byPatch):
        raise ValueError("Invalid settings asset delta lengths")
    byControl = bz2.decompress(byPatch[32:32 + iControlLength])
    byDiff = bz2.decompress(byPatch[32 + iControlLength:32 + iControlLength + iDiffLength])
    byExtra = bz2.decompress(byPatch[32 + iControlLength + iDiffLength:])
    byResult = bytearray()
    iOld = uControl = uDiff = uExtra = 0
    while len(byResult) < iSize:
        iCopy, iExtra, iSeek = (delta_integer(byControl[uControl + uOffset:uControl + uOffset + 8]) for uOffset in (0, 8, 16))
        uControl += 24
        if min(iCopy, iExtra) < 0 or len(byResult) + iCopy + iExtra > iSize or uDiff + iCopy > len(byDiff) or uExtra + iExtra > len(byExtra):
            raise ValueError("Invalid settings asset delta control")
        byResult.extend((byDiff[uDiff + uIndex] + (byOriginal[iOld + uIndex] if 0 <= iOld + uIndex < len(byOriginal) else 0)) & 255 for uIndex in range(iCopy))
        byResult.extend(byExtra[uExtra:uExtra + iExtra])
        iOld += iCopy + iSeek
        uDiff += iCopy
        uExtra += iExtra
    if uControl != len(byControl) or uDiff != len(byDiff) or uExtra != len(byExtra):
        raise ValueError("Unused settings asset delta data")
    return bytes(byResult)


def apply_settings_assets(zInput, strApp, pRoot):
    strFolder = strApp + "/Data/Raw/AssetBundle/"
    byOriginal = zInput.read(strFolder + STR_SETTINGS_BUNDLE)
    if hashlib.sha256(byOriginal).hexdigest() != STR_SETTINGS_ORIGINAL_SHA256:
        raise ValueError("Settings bundle does not match the inspected Colorever 1.23.0 build")
    byPatched = apply_asset_delta(byOriginal, (pRoot / "Source/Mod/Resources/SettingsMessage.bsdiff").read_bytes())
    if hashlib.sha256(byPatched).hexdigest() != STR_SETTINGS_PATCHED_SHA256:
        raise ValueError("Patched settings bundle verification failed")
    strBundle = "local_ui_" + hashlib.md5(byPatched).hexdigest() + ".ab"
    strCrc = zlib.crc32(byPatched).to_bytes(4, "little").hex()
    stManifest = json.loads(zInput.read(strFolder + "manifest.json"))
    aEntries = [stEntry for stEntry in stManifest["BundleInfos"] if stEntry["N"] == "local_ui.ab"]
    if len(aEntries) != 1 or aEntries[0]["BN"] != STR_SETTINGS_BUNDLE or aEntries[0]["S"] != len(byOriginal) or aEntries[0]["C"] != zlib.crc32(byOriginal).to_bytes(4, "little").hex():
        raise ValueError("Unexpected settings bundle manifest")
    aEntries[0].update(BN=strBundle, S=len(byPatched), C=strCrc)
    for stEntry in stManifest["BundleInfos"]:
        stEntry["DEP"] = [strBundle if strName == STR_SETTINGS_BUNDLE else strName for strName in stEntry.get("DEP", [])]
    stReport = {"message": STR_SETTINGS_MESSAGE, "bundle": strBundle, "sha256": STR_SETTINGS_PATCHED_SHA256, "device_tested": False}
    return {strFolder + "manifest.json": json.dumps(stManifest, separators=(",", ":"), ensure_ascii=False).encode("utf-8")}, {strFolder + strBundle: (byPatched, 0o100644)}, stReport



def customize(zInput, strApp, stInfo, pRoot):
    byLogo = (pRoot / "Source/Mod/Resources/Omega172.png").read_bytes()
    if not byLogo.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise ValueError("Expected PNG logo")
    if stInfo.get("CFBundleIdentifier") != "com.oakever.gemcoloring" or stInfo.get("CFBundleShortVersionString") != "1.23.0":
        raise ValueError("This mod requires Colorever 1.23.0")
    strUnity = strApp + "/Frameworks/UnityFramework.framework/UnityFramework"
    byUnity, stGameplay = apply_powerups(zInput.read(strUnity))
    strProtection = strApp + "/Frameworks/anortx.framework/anortx"
    byProtection, stSigningPatch = apply_signing_compatibility(zInput.read(strProtection))
    aSettingsModified, aSettingsAdded, stSettings = apply_settings_assets(zInput, strApp, pRoot)
    stDetails = {
        "signing_compatibility_patch": stSigningPatch,
        "powerup_patches": stGameplay["hooks"],
        "gameplay_runtime_hooks": stGameplay,
        "powerup_count": 999,
        "unity_original_sha256": STR_UNITY_SHA256,
        "unity_patched_sha256": hashlib.sha256(byUnity).hexdigest(),
        "device_tested": False,
        "branding": "Mod by Omega172",
        "logo_sha256": hashlib.sha256(byLogo).hexdigest(),
        "settings_message": stSettings,
    }
    return {strUnity: byUnity, strProtection: byProtection, **aSettingsModified}, {strApp + "/Omega172.png": (byLogo, 0o100644), **aSettingsAdded}, stDetails


def package(pRoot, strInput=""):
    byLibrary = (pRoot / "Build/Release" / (mod.load_config(pRoot)["ProjectName"] + ".dylib")).read_bytes()
    aExports = exported_symbols(byLibrary)
    if not {"_OmegaGameplayHook", "_OmegaProtectionHook"} <= aExports:
        raise ValueError("Mod library lacks C++ runtime handlers; rebuild it first")
    return mod.package(pRoot, strInput, customize)


def package_with_progress(pRoot, strInput=""):
    import fcntl

    pOutput = pRoot / "Build/Release"
    pOutput.mkdir(parents=True, exist_ok=True)
    with (pOutput / ".Packaging.lock").open("a") as hLock:
        try:
            fcntl.flock(hLock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Packaging is already running for this project. Wait for it to finish before starting another build.") from None
        aExisting = set(pOutput.glob("Package-*"))
        dStart = time.monotonic()
        hFinished = threading.Event()

        def progress():
            while not hFinished.wait(10):
                uBytes = 0
                for pDirectory in set(pOutput.glob("Package-*")) - aExisting:
                    for pArchive in pDirectory.glob("*.ipa"):
                        try:
                            uBytes += pArchive.stat().st_size
                        except FileNotFoundError:
                            pass
                print(f"Packaging: {time.monotonic() - dStart:.0f}s elapsed, temporary IPA {uBytes / (1024 * 1024):.1f} MiB. Writing or verifying archive; please wait.", file=sys.stderr, flush=True)

        print("Packaging IPA: checking the input, writing the archive and verifying retained files. Large IPAs can take several minutes.", file=sys.stderr, flush=True)
        hProgress = threading.Thread(target=progress, daemon=True)
        hProgress.start()
        try:
            stReport = package(pRoot, strInput)
            print(f"Packaging verified in {time.monotonic() - dStart:.1f}s. Ready to sign: {stReport['output']}", file=sys.stderr, flush=True)
            return stReport
        finally:
            hFinished.set()
            hProgress.join()


if __name__ == "__main__":
    try:
        print(json.dumps(package_with_progress(Path(sys.argv[1]).resolve(), sys.argv[2] if len(sys.argv) > 2 else ""), indent=2))
    except (ValueError, OSError) as stError:
        print(f"Packaging failed: {stError}", file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Packaging cancelled.", file=sys.stderr, flush=True)
        sys.exit(130)
