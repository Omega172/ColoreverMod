import argparse
import contextlib
import copy
import hashlib
import json
import re
import shutil
import struct
import sys
import tempfile
import urllib.parse
import urllib.request
import plistlib
import zipfile
from pathlib import Path, PurePosixPath


def load_config(pRoot):
    stConfig = json.loads((pRoot / "Project.json").read_text(encoding="utf-8-sig"))
    aExpected = {"ProjectName", "SdkVersion", "MinimumIOSVersion", "CxxStandard"}
    if set(stConfig) != aExpected:
        raise ValueError("Project.json must contain only: " + ", ".join(sorted(aExpected)))
    if not isinstance(stConfig["ProjectName"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", stConfig["ProjectName"]):
        raise ValueError("ProjectName must start with a letter and use letters, numbers or underscores")
    for strKey in ("SdkVersion", "MinimumIOSVersion"):
        if not isinstance(stConfig[strKey], str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", stConfig[strKey]):
            raise ValueError(strKey + " must be a version string, such as 16.5")
    if stConfig["CxxStandard"] not in ("c++20", "c++2a", "c++23", "c++2b", "c++26", "c++2c"):
        raise ValueError("CxxStandard must select C++20 or later, supported by your compiler")
    return stConfig


def commands(byData):
    if len(byData) < 32 or byData[:4] != bytes.fromhex("cffaedfe"):
        raise ValueError("Expected a little-endian 64-bit Mach-O image")
    if struct.unpack_from("<I", byData, 4)[0] != 0x0100000C:
        raise ValueError("Expected arm64")
    uCount, uSize = struct.unpack_from("<II", byData, 16)
    uEnd = 32 + uSize
    if uEnd > len(byData) or uCount > uSize // 8:
        raise ValueError("Invalid load-command bounds")
    uOffset = 32
    aCommands = []
    for uIndex in range(uCount):
        if uOffset + 8 > uEnd:
            raise ValueError("Invalid load-command bounds")
        uCommand, uLength = struct.unpack_from("<II", byData, uOffset)
        if uLength < 8 or uLength % 8 or uOffset + uLength > uEnd:
            raise ValueError("Invalid load-command size")
        aCommands.append((uCommand, uOffset, uLength))
        uOffset += uLength
    if uOffset != uEnd:
        raise ValueError("Load-command size mismatch")
    return aCommands


def inject_thin(byData, strLoad):
    aCommands = commands(byData)
    if struct.unpack_from("<I", byData, 12)[0] != 2:
        raise ValueError("Expected a main executable")
    uFirstSection = len(byData)
    bSectionFound = False
    for uCommand, uOffset, uLength in aCommands:
        if uCommand in (0x21, 0x2C):
            if uLength < 24 or struct.unpack_from("<I", byData, uOffset + 16)[0]:
                raise ValueError("Encrypted or malformed executable; provide a decrypted IPA")
        if uCommand in (0xC, 0x80000018, 0x8000001F):
            if uLength < 24:
                raise ValueError("Malformed dylib load command")
            uName = struct.unpack_from("<I", byData, uOffset + 8)[0]
            if not 24 <= uName < uLength:
                raise ValueError("Invalid dylib name offset")
            if byData[uOffset + uName:uOffset + uLength].split(b"\0", 1)[0] == strLoad.encode():
                raise ValueError("This mod is already injected; provide the original decrypted IPA")
        if uCommand == 0x19:
            if uLength < 72:
                raise ValueError("Malformed segment")
            uSections = struct.unpack_from("<I", byData, uOffset + 64)[0]
            if uLength < 72 + uSections * 80:
                raise ValueError("Malformed segment sections")
            for uIndex in range(uSections):
                uSection = uOffset + 72 + uIndex * 80
                uSize = struct.unpack_from("<Q", byData, uSection + 40)[0]
                uFileOffset = struct.unpack_from("<I", byData, uSection + 48)[0]
                uFlags = struct.unpack_from("<I", byData, uSection + 64)[0] & 0xFF
                if uSize and uFlags not in (1, 0xC, 0x12):
                    if not uFileOffset or uFileOffset + uSize > len(byData):
                        raise ValueError("Invalid section file range")
                    uFirstSection = min(uFirstSection, uFileOffset)
                    bSectionFound = True
    if not bSectionFound:
        raise ValueError("No file-backed executable sections")
    byName = strLoad.encode() + b"\0"
    uNewSize = (24 + len(byName) + 7) & ~7
    uHeaderEnd = 32 + struct.unpack_from("<I", byData, 20)[0]
    if uHeaderEnd + uNewSize > uFirstSection:
        raise ValueError("Insufficient Mach-O header padding; binary data was not shifted")
    if any(byData[uHeaderEnd:uHeaderEnd + uNewSize]):
        raise ValueError("Header padding contains data")
    byCommand = struct.pack("<6I", 0xC, uNewSize, 24, 0, 0x10000, 0x10000) + byName
    byResult = bytearray(byData)
    byResult[uHeaderEnd:uHeaderEnd + uNewSize] = byCommand.ljust(uNewSize, b"\0")
    struct.pack_into("<II", byResult, 16, len(aCommands) + 1, uHeaderEnd - 32 + uNewSize)
    commands(byResult)
    if byResult[uFirstSection:] != byData[uFirstSection:]:
        raise ValueError("Executable section data changed")
    return bytes(byResult)


def inject(byData, strLoad):
    aFatFormats = {
        bytes.fromhex("cafebabe"): (">", False), bytes.fromhex("bebafeca"): ("<", False),
        bytes.fromhex("cafebabf"): (">", True), bytes.fromhex("bfbafeca"): ("<", True),
    }
    if byData[:4] not in aFatFormats:
        return inject_thin(byData, strLoad)
    strEndian, bFat64 = aFatFormats[byData[:4]]
    if len(byData) < 8:
        raise ValueError("Invalid universal Mach-O header")
    uCount = struct.unpack_from(strEndian + "I", byData, 4)[0]
    uStride = 32 if bFat64 else 20
    uHeaderEnd = 8 + uCount * uStride
    if not uCount or uCount > 64 or uHeaderEnd > len(byData):
        raise ValueError("Invalid universal Mach-O architecture table")
    aRanges = []
    aSlices = []
    for uIndex in range(uCount):
        uOffset = 8 + uIndex * uStride
        uCpu = struct.unpack_from(strEndian + "I", byData, uOffset)[0]
        uStart, uSize = struct.unpack_from(strEndian + ("QQ" if bFat64 else "II"), byData, uOffset + 8)
        if not uSize or uStart < uHeaderEnd or uStart + uSize > len(byData):
            raise ValueError("Invalid universal Mach-O slice range")
        if any(uStart < uOtherEnd and uOtherStart < uStart + uSize for uOtherStart, uOtherEnd in aRanges):
            raise ValueError("Overlapping universal Mach-O slices")
        aRanges.append((uStart, uStart + uSize))
        if uCpu == 0x0100000C:
            aSlices.append((uStart, uSize))
    if not aSlices:
        raise ValueError("IPA has no arm64 executable slice")
    byResult = bytearray(byData)
    for uStart, uSize in aSlices:
        byResult[uStart:uStart + uSize] = inject_thin(byData[uStart:uStart + uSize], strLoad)
    return bytes(byResult)


class clHttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, pstRequest, pstFile, iCode, strMessage, pstHeaders, strUrl):
        if urllib.parse.urlsplit(strUrl).scheme != "https":
            raise ValueError("IPA downloads must remain HTTPS after redirects")
        return super().redirect_request(pstRequest, pstFile, iCode, strMessage, pstHeaders, strUrl)


@contextlib.contextmanager
def input_ipa(pRoot, strInput):
    if strInput.startswith("https://"):
        pDownloads = pRoot / "Build/Downloads"
        pDownloads.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="Ipa-", dir=pDownloads) as strDirectory:
            pInput = Path(strDirectory) / "Input.ipa"
            pstOpener = urllib.request.build_opener(clHttpsRedirect())
            with pstOpener.open(strInput, timeout=60) as hSource, pInput.open("wb") as hOutput:
                shutil.copyfileobj(hSource, hOutput)
            yield pInput
        return
    if "://" in strInput:
        raise ValueError("Use a local IPA path or a direct HTTPS download URL")
    if strInput:
        pInput = Path(strInput).resolve()
    else:
        aInputs = list(pRoot.glob("*.[iI][pP][aA]"))
        if len(aInputs) != 1:
            raise ValueError("Pass an IPA path or HTTPS URL, or place exactly one IPA in the project root")
        pInput = aInputs[0].resolve()
    if not pInput.is_file():
        raise FileNotFoundError("Input IPA not found: " + str(pInput))
    yield pInput


def file_hash(pPath):
    with pPath.open("rb") as hInput:
        return hashlib.file_digest(hInput, "sha256").hexdigest()


def copy_compressed_entry(zInput, zOutput, stEntry, uEnd):
    uSize = uEnd - stEntry.header_offset
    zInput.fp.seek(stEntry.header_offset)
    byHeader = zInput.fp.read(30)
    if len(byHeader) != 30 or byHeader[:4] != b"PK\x03\x04":
        raise ValueError("Invalid ZIP local header")
    uName, uExtra = struct.unpack_from("<HH", byHeader, 26)
    if uSize < 30 + uName + uExtra + stEntry.compress_size or uEnd > zInput.start_dir:
        raise ValueError("Invalid ZIP entry bounds")
    stCopy = copy.copy(stEntry)
    stCopy.header_offset = zOutput.start_dir
    zOutput._writecheck(stCopy)
    zOutput.fp.seek(zOutput.start_dir)
    zInput.fp.seek(stEntry.header_offset)
    while uSize:
        byChunk = zInput.fp.read(min(uSize, 1024 * 1024))
        if not byChunk:
            raise ValueError("Truncated ZIP entry")
        zOutput.fp.write(byChunk)
        uSize -= len(byChunk)
    zOutput.start_dir = zOutput.fp.tell()
    zOutput._didModify = True
    zOutput.filelist.append(stCopy)
    zOutput.NameToInfo[stCopy.filename] = stCopy


def package(pRoot, strInput="", pstCustomize=None):
    stConfig = load_config(pRoot)
    strName = stConfig["ProjectName"]
    strLoad = "@executable_path/Frameworks/" + strName + ".dylib"
    pLibrary = pRoot / "Build/Release" / (strName + ".dylib")
    byLibrary = pLibrary.read_bytes()
    commands(byLibrary)
    if struct.unpack_from("<I", byLibrary, 12)[0] != 6:
        raise ValueError("Build output is not a dylib")
    pOutput = pLibrary.with_name(strName + "-NeedsSigning.ipa")
    with input_ipa(pRoot, strInput) as pInput:
        if pInput.resolve() == pOutput.resolve() or (pOutput.exists() and pInput.samefile(pOutput)):
            raise ValueError("Input and output IPA paths must be different")
        strBefore = file_hash(pInput)
        with zipfile.ZipFile(pInput) as zInput:
            aNames = zInput.namelist()
            aOffsets = sorted(stEntry.header_offset for stEntry in zInput.infolist())
            aEnds = dict(zip(aOffsets, aOffsets[1:] + [zInput.start_dir]))
            if len(aNames) != len(set(aNames)):
                raise ValueError("Duplicate ZIP entries")
            for strEntry in aNames:
                pEntry = PurePosixPath(strEntry)
                if pEntry.is_absolute() or ".." in pEntry.parts or "\\" in strEntry or (pEntry.parts and ":" in pEntry.parts[0]):
                    raise ValueError("Unsafe ZIP path")
            aPlists = [n for n in aNames if n.startswith("Payload/") and n.count("/") == 2 and n.endswith("/Info.plist")]
            if len(aPlists) != 1:
                raise ValueError("Expected one top-level app in Payload")
            strPlist = aPlists[0]
            byPlist = zInput.read(strPlist)
            stInfo = plistlib.loads(byPlist)
            strExecutableName = stInfo.get("CFBundleExecutable")
            if not isinstance(strExecutableName, str) or not strExecutableName or any(ch in strExecutableName for ch in ("/", "\\")) or strExecutableName in (".", ".."):
                raise ValueError("Invalid CFBundleExecutable")
            strApp = strPlist.rsplit("/", 1)[0]
            strExecutable = strApp + "/" + strExecutableName
            strLibrary = strApp + "/Frameworks/" + strName + ".dylib"
            if strLibrary in aNames:
                raise ValueError("Input already contains this mod library")
            byExecutable = inject(zInput.read(strExecutable), strLoad)
            aModified = {strExecutable: byExecutable}
            aAdded = {strLibrary: (byLibrary, 0o100755)}
            stDetails = {}
            if pstCustomize is not None:
                aCustomModified, aCustomAdded, stDetails = pstCustomize(zInput, strApp, stInfo, pRoot)
                if set(aModified) & set(aCustomModified) or set(aAdded) & set(aCustomAdded):
                    raise ValueError("Custom packaging collides with injected files")
                if any(n not in aNames or PurePosixPath(n).name == "Info.plist" for n in aCustomModified):
                    raise ValueError("Custom patches must target existing files and preserve Info.plist")
                for strEntry in aCustomAdded:
                    pEntry = PurePosixPath(strEntry)
                    if strEntry in aNames or not strEntry.startswith(strApp + "/") or ".." in pEntry.parts or "\\" in strEntry:
                        raise ValueError("Invalid custom added file")
                aModified.update(aCustomModified)
                aAdded.update(aCustomAdded)
            aRemoved = [n for n in aNames if "_CodeSignature" in PurePosixPath(n).parts or n.endswith("/embedded.mobileprovision")]
            with tempfile.TemporaryDirectory(prefix="Package-", dir=pOutput.parent) as strDirectory:
                pTemporary = Path(strDirectory) / pOutput.name
                with zipfile.ZipFile(pTemporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zOutput:
                    for stEntry in zInput.infolist():
                        if stEntry.filename in aRemoved:
                            continue
                        if stEntry.filename in aModified:
                            zOutput.writestr(copy.copy(stEntry), aModified[stEntry.filename])
                        else:
                            copy_compressed_entry(zInput, zOutput, stEntry, aEnds[stEntry.header_offset])
                    for strEntry, (byContent, uMode) in aAdded.items():
                        stAdded = zipfile.ZipInfo(strEntry)
                        stAdded.create_system = 3
                        stAdded.external_attr = uMode << 16
                        stAdded.compress_type = zipfile.ZIP_DEFLATED
                        zOutput.writestr(stAdded, byContent)
                with zipfile.ZipFile(pTemporary) as zOutput:
                    aExpected = (set(aNames) - set(aRemoved)) | set(aAdded)
                    if set(zOutput.namelist()) != aExpected or len(zOutput.namelist()) != len(aExpected):
                        raise ValueError("Unexpected output ZIP entries")
                    for strEntry, byContent in aModified.items():
                        if zOutput.read(strEntry) != byContent:
                            raise ValueError("Modified bytes failed verification: " + strEntry)
                    for strEntry, (byContent, uMode) in aAdded.items():
                        if zOutput.read(strEntry) != byContent:
                            raise ValueError("Added bytes failed verification: " + strEntry)
                    for strEntry in aNames:
                        if strEntry not in aModified and strEntry not in aRemoved:
                            with zInput.open(strEntry) as hBefore, zOutput.open(strEntry) as hAfter:
                                if hashlib.file_digest(hBefore, "sha256").digest() != hashlib.file_digest(hAfter, "sha256").digest():
                                    raise ValueError("Unexpected change to " + strEntry)
                if file_hash(pInput) != strBefore:
                    raise ValueError("Original IPA changed")
                pTemporary.replace(pOutput)
    stReport = {
        "project": strName, "input_sha256": strBefore, "output": str(pOutput),
        "bundle_identifier_preserved": stInfo.get("CFBundleIdentifier"),
        "info_plist_preserved": True, "library_sha256": hashlib.sha256(byLibrary).hexdigest(),
        "load_command": strLoad, "needs_signing": True,
        "verification": "Archive CRC, injected bytes, original IPA hash and every retained file verified",
    }
    stReport.update(stDetails)
    pOutput.with_name(strName + "-PackageReport.json").write_text(json.dumps(stReport, indent=2) + "\n", encoding="utf-8")
    return stReport


def main():
    pstParser = argparse.ArgumentParser(description="Build configuration and unsigned IPA packaging")
    pstParser.add_argument("mode", choices=("config", "package"))
    pstParser.add_argument("root", type=Path)
    pstParser.add_argument("input", nargs="?", default="")
    stArgs = pstParser.parse_args()
    pRoot = stArgs.root.resolve()
    if stArgs.mode == "config":
        stConfig = load_config(pRoot)
        print("\n".join(stConfig[k] for k in ("ProjectName", "SdkVersion", "MinimumIOSVersion", "CxxStandard")))
    else:
        print(json.dumps(package(pRoot, stArgs.input), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, struct.error) as stError:
        print("Error: " + str(stError), file=sys.stderr)
        sys.exit(1)
