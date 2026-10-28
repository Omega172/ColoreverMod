import importlib.util
import json
import struct
from pathlib import Path
from zipfile import ZipFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
import unicorn.arm64_const as arm

pRoot = Path(__file__).resolve().parents[2]
stSpec = importlib.util.spec_from_file_location('package', pRoot / 'Source/Mod/Package.py')
pMod = importlib.util.module_from_spec(stSpec)
stSpec.loader.exec_module(pMod)
byHandlers = (pRoot / 'Build/Release/ColoreverMod.dylib').read_bytes()
aSymbols = {}
for uCommand, uOffset, uSize in pMod.mod.commands(byHandlers):
    if uCommand != 2:
        continue
    uSymbols, uCount, uStrings, uLength = struct.unpack_from('<4I', byHandlers, uOffset + 8)
    for uIndex in range(uCount):
        uName, uType, uSection, uDescription, uAddress = struct.unpack_from('<IBBHQ', byHandlers, uSymbols + uIndex * 16)
        strName = byHandlers[uStrings + uName:uStrings + uLength].split(b'\0', 1)[0].decode()
        if strName in ('_OmegaGameplayHook', '_OmegaProtectionHook') and uType & 1 and uType & 0xE == 0xE:
            aSymbols[strName[1:]] = uAddress
assert len(aSymbols) == 2, 'Rebuild the iOS mod library before verifying its handlers'
with ZipFile(pRoot / 'com.oakever.gemcoloring-1.23.0-Decrypted.ipa') as pZip:
    byUnity, stGameplay = pMod.apply_powerups(pZip.read('Payload/Colorever.app/Frameworks/UnityFramework.framework/UnityFramework'))
    byAnortx, stProtection = pMod.apply_signing_compatibility(pZip.read('Payload/Colorever.app/Frameworks/anortx.framework/anortx'))
aRegisters = [getattr(arm, f'UC_ARM64_REG_X{i}') for i in range(29)] + [arm.UC_ARM64_REG_FP, arm.UC_ARM64_REG_LR]
aVectors = [getattr(arm, f'UC_ARM64_REG_Q{i}') for i in range(32)]
uCases = 0
uExecutions = 0


def verify(byImage, stLayout, uHook, uBase, bAvailable, uVmPc=0, uOpcode=0, bNull=False):
    global uCases, uExecutions
    bGameplay = stLayout['dispatcher'] == 'OmegaGameplayHook'
    stHook = stLayout['hooks'][uHook]
    uSite = int(stHook['file_offset'], 16)
    uCave = int(stLayout['cave'], 16)
    uDlsym = uBase + int(stLayout['dlsym_stub'], 16)
    uCache = uBase + int(stLayout['cache_address'], 16)
    uCode = uBase + 0x10000000
    uHandler = uCode + aSymbols[stLayout['dispatcher']]
    uStack = uBase + 0x20001800
    uVm = uBase + 0x20004000
    uObject = uBase + 0x20006000
    uReturn = uBase + 0x20008000
    bSuppress = not bGameplay and uHook == 0 and not bNull and uVmPc == 0x100C4 and uOpcode == 0x750A6528
    bReturn = bAvailable and not bGameplay and (uHook != 0 or bSuppress)
    uStop = uReturn if bReturn else uBase + uSite + 4
    pCpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    aPages = {uSite & ~0xFFF, int(stLayout['dlsym_stub'], 16) & ~0xFFF}
    aPages.update(range(uCave & ~0xFFF, (uCave + stLayout['code_size'] + 0xFFF) & ~0xFFF, 0x1000))
    for uPage in aPages:
        pCpu.mem_map(uBase + uPage, 0x1000)
        pCpu.mem_write(uBase + uPage, byImage[uPage:uPage + 0x1000])
    pCpu.mem_map(uCache & ~0xFFF, 0x1000)
    pCpu.mem_map(uCode, (len(byHandlers) + 0xFFF) & ~0xFFF)
    pCpu.mem_write(uCode, byHandlers)
    pCpu.mem_map(uBase + 0x20000000, 0x2000)
    for uAddress in [uVm, uObject, uReturn]:
        pCpu.mem_map(uAddress, 0x1000)
    aCounts = [0, 0]

    def on_code(pEngine, uAddress, uSize, pData):
        if uAddress == uDlsym:
            aCounts[0] += 1
            assert pEngine.reg_read(arm.UC_ARM64_REG_X0) == 0xFFFFFFFFFFFFFFFE
            uName = pEngine.reg_read(arm.UC_ARM64_REG_X1)
            assert pEngine.mem_read(uName, len(stLayout['dispatcher']) + 1) == stLayout['dispatcher'].encode() + b'\0'
            uLr = pEngine.reg_read(arm.UC_ARM64_REG_LR)
            for i in range(1, 19):
                pEngine.reg_write(aRegisters[i], 0xDEAD0000 + i)
            for uRegister in aVectors:
                pEngine.reg_write(uRegister, 0)
            pEngine.reg_write(arm.UC_ARM64_REG_NZCV, 0)
            pEngine.reg_write(arm.UC_ARM64_REG_X0, uHandler if bAvailable else 0)
            pEngine.reg_write(arm.UC_ARM64_REG_PC, uLr)
        elif uAddress == uHandler:
            aCounts[1] += 1
            assert pEngine.reg_read(arm.UC_ARM64_REG_X0) == uStack - 800
            assert pEngine.reg_read(arm.UC_ARM64_REG_X1) == uHook
            assert pEngine.reg_read(arm.UC_ARM64_REG_X2) == uBase

    def on_invalid(pEngine, uAccess, uAddress, uSize, uValue, pData):
        print(json.dumps({'dispatcher': stLayout['dispatcher'], 'hook': uHook, 'available': bAvailable, 'invalid_address': hex(uAddress), 'pc': hex(pEngine.reg_read(arm.UC_ARM64_REG_PC)), 'sp': hex(pEngine.reg_read(arm.UC_ARM64_REG_SP)), 'x9': hex(pEngine.reg_read(arm.UC_ARM64_REG_X9))}), flush=True)
        return False

    pCpu.hook_add(UC_HOOK_MEM_INVALID, on_invalid)
    pCpu.hook_add(UC_HOOK_CODE, on_code)
    for iPass in range(2):
        aBefore = [0xABC00000 + i for i in range(31)]
        aBefore[0] = uObject if bGameplay else (uOpcode if uHook == 0 else 0xFFFFFFFF)
        aBefore[1] = 0 if bNull else uVm
        if bGameplay and uHook < 6: aBefore[8] = uObject
        aBefore[19] = 100
        aBefore[21] = 0x123456789
        aBefore[30] = uReturn
        for uRegister, uValue in zip(aRegisters, aBefore):
            pCpu.reg_write(uRegister, uValue)
        pCpu.reg_write(arm.UC_ARM64_REG_SP, uStack)
        pCpu.reg_write(arm.UC_ARM64_REG_NZCV, 0xA0000000)
        aVectorValues = [(i + 1) << 96 | 0x123456789 for i in range(32)]
        for uRegister, uValue in zip(aVectors, aVectorValues):
            pCpu.reg_write(uRegister, uValue)
        pCpu.mem_write(uVm + 0x108, struct.pack('<Q', uVmPc))
        pCpu.mem_write(uVm + 0x120, struct.pack('<I', 1))
        for i, uValue in enumerate([17, 23, 31]):
            pCpu.mem_write(uObject + 0x10 + i * 4, struct.pack('<I', uValue))
        pCpu.emu_start(uBase + uSite, uStop, count=1000)
        assert pCpu.reg_read(arm.UC_ARM64_REG_PC) == uStop
        aExpected = list(aBefore)
        if bGameplay:
            if uHook < 6:
                aExpected[0] = 999 if bAvailable else [17, 23, 31][uHook % 3]
            else:
                aExpected[9] = ((aBefore[21] & 0xFFFFFFFF) - (0 if bAvailable else aBefore[19])) & 0xFFFFFFFF
        elif bAvailable and uHook == 3:
            aExpected[0] = 0
        for i, uRegister in enumerate(aRegisters):
            if i != 16:
                assert pCpu.reg_read(uRegister) == aExpected[i], (stLayout['dispatcher'], uHook, bAvailable, i, hex(pCpu.reg_read(uRegister)), hex(aExpected[i]))
        uStackDelta = 0 if bGameplay or bReturn else (0x30 if uHook in (0, 3) else 0x10)
        assert pCpu.reg_read(arm.UC_ARM64_REG_SP) == uStack - uStackDelta
        assert pCpu.reg_read(arm.UC_ARM64_REG_NZCV) == 0xA0000000
        assert [pCpu.reg_read(uRegister) for uRegister in aVectors] == aVectorValues
        assert int.from_bytes(pCpu.mem_read(uVm + 0x120, 4), 'little') == (0 if bAvailable and bSuppress else 1)
        assert int.from_bytes(pCpu.mem_read(uCache, 8), 'little') == (uHandler if bAvailable else 0)
        assert aCounts[0] == (1 if bAvailable else iPass + 1)
        assert aCounts[1] == (iPass + 1 if bAvailable else 0)
        uExecutions += 1
    uCases += 1


for uBase in [0, 0x100000000]:
    for bAvailable in [True, False]:
        for uHook in range(9):
            verify(byUnity, stGameplay, uHook, uBase, bAvailable)
        for uPc in [0, 0x100C0, 0x100C4, 0x100C8, 0xFFFFFFFFFFFFFFFF]:
            for uOpcode in [0, 0x750A6528, 0x750A6529]:
                verify(byAnortx, stProtection, 0, uBase, bAvailable, uPc, uOpcode)
        verify(byAnortx, stProtection, 0, uBase, bAvailable, 0x100C4, 0x750A6528, True)
        for uHook in range(1, 4):
            verify(byAnortx, stProtection, uHook, uBase, bAvailable)
stResult = {'cases_passed': uCases, 'executions_passed': uExecutions, 'checks': ['actual built iOS C++ handlers', 'signed trampoline routing', 'two ASLR bases', 'general registers except branch scratch x16', 'all SIMD registers and NZCV', 'stack restoration and fallback prologues', 'cold and cached dlsym resolution', 'missing-handler original-instruction fallback', 'VM predicate and completion flag', 'native validator returns zero']}
(pRoot / 'Build/Release/Colorever-CppHooks-Verification.json').write_text(json.dumps(stResult, indent=2) + '\n')
print(json.dumps(stResult))
