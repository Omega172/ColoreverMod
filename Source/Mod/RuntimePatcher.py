import hashlib
import os
import struct
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

def branch(uFrom, uTo, bLink=False):
    iDelta = uTo - uFrom
    if iDelta % 4 or not -(1 << 27) <= iDelta < (1 << 27):
        raise ValueError("Invalid arm64 branch range")
    return struct.pack("<I", (0x94000000 if bLink else 0x14000000) | ((iDelta // 4) & 0x3FFFFFF))


def image_info(byData):
    if byData[:4] != bytes.fromhex("cffaedfe"):
        raise ValueError("Expected arm64 Mach-O")
    aSections = []
    uOffset = 32
    stSymbols = None
    stIndirect = None
    for uIndex in range(struct.unpack_from("<I", byData, 16)[0]):
        uCommand, uSize = struct.unpack_from("<II", byData, uOffset)
        if uCommand == 2:
            stSymbols = struct.unpack_from("<4I", byData, uOffset + 8)
        if uCommand == 0xB:
            stIndirect = struct.unpack_from("<II", byData, uOffset + 56)
        if uCommand == 0x19:
            if byData[uOffset + 8:uOffset + 24].split(b"\0")[0] == b"__TEXT":
                if struct.unpack_from("<Q", byData, uOffset + 24)[0] != 0 or not struct.unpack_from("<I", byData, uOffset + 60)[0] & 4:
                    raise ValueError("Expected executable __TEXT at image base")
            for uSection in range(struct.unpack_from("<I", byData, uOffset + 64)[0]):
                uPosition = uOffset + 72 + 80 * uSection
                strName = byData[uPosition:uPosition + 16].split(b"\0")[0].decode()
                uAddress, uLength, uFileOffset = struct.unpack_from("<QQI", byData, uPosition + 32)
                uFlags, uFirst, uStride = struct.unpack_from("<III", byData, uPosition + 64)
                aSections.append((strName, uAddress, uLength, uFileOffset, uFlags, uFirst, uStride))
        uOffset += uSize
    if not stSymbols or not stIndirect:
        raise ValueError("Missing dynamic symbol metadata")
    uSymOffset, uSymCount, uStrings, uStringSize = stSymbols
    uIndirectOffset, uIndirectCount = stIndirect
    uStub = None
    for strName, uAddress, uLength, uFileOffset, uFlags, uFirst, uStride in aSections:
        if strName != "__stubs" or not uStride:
            continue
        for uIndex in range(uLength // uStride):
            uSymbol = struct.unpack_from("<I", byData, uIndirectOffset + 4 * (uFirst + uIndex))[0]
            if uSymbol >= uSymCount:
                continue
            uString = struct.unpack_from("<I", byData, uSymOffset + 16 * uSymbol)[0]
            if byData[uStrings + uString:uStrings + uStringSize].split(b"\0", 1)[0] == b"_dlsym":
                uStub = uAddress + uIndex * uStride
    if uStub is None:
        raise ValueError("No existing dlsym import stub")
    uCave = (32 + struct.unpack_from("<I", byData, 20)[0] + 15) & ~15
    uFirstData = min(s[3] for s in aSections if s[2] and s[3] and s[4] & 0xFF not in (1, 0xC, 0x12))
    return uCave, uFirstData, uStub


def read_object(byObject):
    if byObject[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", byObject, 18)[0] != 183:
        raise ValueError("Expected AArch64 ELF object")
    uHeaders = struct.unpack_from("<Q", byObject, 40)[0]
    uStride, uCount, uNames = struct.unpack_from("<HHH", byObject, 58)
    aHeaders = [struct.unpack_from("<IIQQQQIIQQ", byObject, uHeaders + i * uStride) for i in range(uCount)]
    stNames = aHeaders[uNames]
    byNames = byObject[stNames[4]:stNames[4] + stNames[5]]
    byCode = None
    aSymbols = {}
    for stHeader in aHeaders:
        strName = byNames[stHeader[0]:].split(b"\0", 1)[0].decode()
        if stHeader[1] in (4, 9) and stHeader[5]:
            raise ValueError("Unexpected assembly relocations")
        if strName == ".text":
            byCode = byObject[stHeader[4]:stHeader[4] + stHeader[5]]
        if stHeader[1] == 2:
            stStrings = aHeaders[stHeader[6]]
            byStrings = byObject[stStrings[4]:stStrings[4] + stStrings[5]]
            for uOffset in range(stHeader[4], stHeader[4] + stHeader[5], stHeader[9]):
                uName, uInfo, uOther, uSection, uValue, uSize = struct.unpack_from("<IBBHQQ", byObject, uOffset)
                aSymbols[byStrings[uName:].split(b"\0", 1)[0].decode()] = uValue
    if byCode is None:
        raise ValueError("Assembly object has no text section")
    return byCode, aSymbols


def compile_assembly(pSource, pObject):
    aPrefix = []
    if os.name == "nt":
        aPrefix = ["wsl", "--"]
        rTheos = subprocess.run(aPrefix + ["printenv", "THEOS"], capture_output=True, text=True)
        strTheos = rTheos.stdout.strip() or subprocess.check_output(aPrefix + ["printenv", "HOME"], text=True).strip() + "/theos"
        strSource = subprocess.check_output(aPrefix + ["wslpath", "-a", "-u", pSource.as_posix()], text=True).strip()
        strObject = subprocess.check_output(aPrefix + ["wslpath", "-a", "-u", pObject.as_posix()], text=True).strip()
    else:
        strTheos = os.environ.get("THEOS", str(Path.home() / "theos"))
        strSource, strObject = str(pSource), str(pObject)
    for strLocation in ("host", "iphone"):
        strCompiler = strTheos + "/toolchain/linux/" + strLocation + "/bin/clang"
        if subprocess.run(aPrefix + ["test", "-x", strCompiler], capture_output=True).returncode == 0:
            subprocess.run(aPrefix + [strCompiler, "-target", "aarch64-linux-gnu", "-c", strSource, "-o", strObject], check=True)
            return
    raise FileNotFoundError("No Theos clang found; set THEOS in the build environment")



def cache_slot(byData):
    uOffset = 32
    for _ in range(struct.unpack_from("<I", byData, 16)[0]):
        uCommand, uSize = struct.unpack_from("<II", byData, uOffset)
        if uCommand == 0x19 and byData[uOffset + 8:uOffset + 24].split(b"\0", 1)[0] == b"__DATA":
            uVm, uVmSize, uFile, uFileSize, iMaximum, iInitial, uSections = struct.unpack_from("<QQQQiiI", byData, uOffset + 24)
            if not iInitial & 2:
                raise ValueError("Handler cache segment is not writable")
            aRanges = []
            for iSection in range(uSections):
                uAddress, uLength = struct.unpack_from("<QQ", byData, uOffset + 72 + iSection * 80 + 32)
                aRanges.append((uAddress, uAddress + uLength))
            uCursor = uVm
            for uStart, uEnd in sorted(aRanges) + [(uVm + uFileSize, uVm + uFileSize)]:
                uCandidate = (uCursor + 7) & ~7
                if uCandidate + 8 <= min(uStart, uVm + uFileSize):
                    uPosition = uFile + uCandidate - uVm
                    if byData[uPosition:uPosition + 8] == bytes(8):
                        return uCandidate, uPosition
                uCursor = max(uCursor, uEnd)
        uOffset += uSize
    raise ValueError("No verified writable handler-cache padding")


def assembly(uCave, aHooks, strDispatcher):
    aLines = [".text", ".p2align 2", ".Lblob:"]
    for uHook, (strName, uSite, strOriginal) in enumerate(aHooks):
        uInstruction = int.from_bytes(bytes.fromhex(strOriginal), "little")
        aLines += [f".global Hook{uHook}", f"Hook{uHook}:", "stp x16, x17, [sp, #-16]!", f"mov w16, #{uHook}", f"adr x17, .Lfallback{uHook}", "b .Lcommon", f".Lfallback{uHook}:", f".word {uInstruction}", f".global Resume{uHook}", f"Resume{uHook}:", "b ."]
    aLines += [".Lcommon:", "sub sp, sp, #784"]
    for uRegister in range(0, 30, 2):
        aLines += [f"stp x{uRegister}, x{uRegister + 1}, [sp, #{uRegister * 8}]"]
    aLines += ["str x30, [sp, #240]", "mrs x9, nzcv", "str x9, [sp, #248]"]
    for uRegister in range(0, 32, 2):
        aLines += [f"stp q{uRegister}, q{uRegister + 1}, [sp, #{256 + uRegister * 16}]"]
    aLines += ["str x17, [sp, #768]", "str x16, [sp, #776]", "ldr x9, [sp, #784]", "ldr x10, [sp, #792]", "stp x9, x10, [sp, #128]", ".global CachePage", "CachePage:", ".word 0x90000009", ".global CacheOffset", "CacheOffset:", "add x9, x9, #0", "ldr x3, [x9]", "cbnz x3, .Linvoke", "mov x0, #-2", "adr x1, .Lname", ".global DispatcherCall", "DispatcherCall:", "bl .", "cbz x0, .Lrestore", "mov x3, x0", ".global StoreCachePage", "StoreCachePage:", ".word 0x90000009", ".global StoreCacheOffset", "StoreCacheOffset:", "add x9, x9, #0", "str x3, [x9]", ".Linvoke:", "mov x0, sp", "ldr w1, [sp, #776]", "adr x2, .Lblob", f"sub x2, x2, #{uCave >> 12}, lsl #12", f"sub x2, x2, #{uCave & 0xFFF}", "blr x3", ".Lrestore:"]
    for uRegister in range(0, 32, 2):
        aLines += [f"ldp q{uRegister}, q{uRegister + 1}, [sp, #{256 + uRegister * 16}]"]
    aLines += ["ldr x9, [sp, #248]", "msr nzcv, x9"]
    for uRegister in range(0, 30, 2):
        aLines += [f"ldp x{uRegister}, x{uRegister + 1}, [sp, #{uRegister * 8}]"]
    aLines += ["ldr x30, [sp, #240]", "ldr x16, [sp, #768]", "add sp, sp, #800", "br x16", ".Lname:", f'.asciz "{strDispatcher}"', ".p2align 2"]
    return "\n".join(aLines) + "\n"


@lru_cache(maxsize=4)
def trampoline(uCave, uDlsym, uCache, aHooks, strDispatcher):
    with tempfile.TemporaryDirectory(prefix="ColoreverHooks-") as strTemporary:
        pSource, pObject = Path(strTemporary) / "Trampoline.s", Path(strTemporary) / "Trampoline.o"
        pSource.write_text(assembly(uCave, aHooks, strDispatcher))
        compile_assembly(pSource, pObject)
        byCode, aSymbols = read_object(pObject.read_bytes())
    byCode = bytearray(byCode)
    uCall = aSymbols["DispatcherCall"]
    byCode[uCall:uCall + 4] = branch(uCave + uCall, uDlsym, True)
    for strPrefix in ("", "Store"):
        uPage = aSymbols[strPrefix + "CachePage"]
        iPages = (uCache >> 12) - ((uCave + uPage) >> 12)
        if not -(1 << 20) <= iPages < (1 << 20):
            raise ValueError("Handler cache exceeds ADRP range")
        uImmediate = iPages & 0x1FFFFF
        struct.pack_into("<I", byCode, uPage, 0x90000009 | ((uImmediate & 3) << 29) | ((uImmediate >> 2) << 5))
        struct.pack_into("<I", byCode, aSymbols[strPrefix + "CacheOffset"], 0x91000129 | ((uCache & 0xFFF) << 10))
    for uHook, (_, uSite, _) in enumerate(aHooks):
        uResume = aSymbols[f"Resume{uHook}"]
        byCode[uResume:uResume + 4] = branch(uCave + uResume, uSite + 4)
    return bytes(byCode), aSymbols


def apply_runtime_hooks(byData, aHooks, strDispatcher):
    for strFeature, uSite, strExpected in aHooks:
        if byData[uSite:uSite + 4].hex() != strExpected:
            raise ValueError("Unexpected runtime hook instruction: " + strFeature)
    uCave, uFirstData, uDlsym = image_info(byData)
    uCache, uCacheFile = cache_slot(byData)
    byCode, aSymbols = trampoline(uCave, uDlsym, uCache, tuple(aHooks), strDispatcher)
    if uCave + len(byCode) > uFirstData or any(byData[uCave:uCave + len(byCode)]):
        raise ValueError("Insufficient zero-filled executable header padding")
    byOutput = bytearray(byData)
    aReport = []
    for uHook, (strFeature, uSite, strExpected) in enumerate(aHooks):
        uEntry = uCave + aSymbols[f"Hook{uHook}"]
        byRedirect = branch(uSite, uEntry)
        byOutput[uSite:uSite + 4] = byRedirect
        aReport.append({"feature": strFeature, "hook_id": uHook, "file_offset": hex(uSite), "trampoline": hex(uEntry), "fallback": hex(uCave + aSymbols[f"Resume{uHook}"] - 4), "before": strExpected, "after": byRedirect.hex()})
    byOutput[uCave:uCave + len(byCode)] = byCode
    return bytes(byOutput), {"dispatcher": strDispatcher, "cave": hex(uCave), "code_size": len(byCode), "cache_address": hex(uCache), "cache_file_offset": hex(uCacheFile), "dlsym_stub": hex(uDlsym), "hooks": aReport, "original_sha256": hashlib.sha256(byData).hexdigest(), "patched_sha256": hashlib.sha256(byOutput).hexdigest()}
