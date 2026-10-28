#include "../Mod/RuntimeHooks.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

int main()
{
    for (uint32_t uHook = 0; uHook < 9; ++uHook)
    {
        stRuntimeContext stContext{};
        stContext.aRegisters[0] = 17;
        stContext.aRegisters[9] = 123;
        stContext.aRegisters[21] = 0x123456789ULL;
        stContext.uNextAddress = 0x1000;
        stContext.uFlags = 0xA0000000;
        OmegaGameplayHook(&stContext, uHook, 0);
        assert(stContext.uNextAddress == 0x1004);
        assert(stContext.aRegisters[0] == (uHook < 6 ? 999 : 17));
        assert(stContext.aRegisters[9] == (uHook < 6 ? 123 : 0x23456789));
        assert(stContext.uFlags == 0xA0000000);
    }
    alignas(16) uint8_t aVm[0x140]{};
    uint64_t aPc[] = {0, 0x100C0, 0x100C4, 0x100C8, ~uint64_t(0)};
    uint32_t aOpcodes[] = {0, 0x750A6528, 0x750A6529};
    for (uint64_t uPc : aPc)
        for (uint32_t uOpcode : aOpcodes)
        {
            memcpy(aVm + 0x108, &uPc, 8);
            uint32_t uFlag = 1;
            memcpy(aVm + 0x120, &uFlag, 4);
            stRuntimeContext stContext{};
            stContext.aRegisters[0] = uOpcode;
            stContext.aRegisters[1] = reinterpret_cast<uintptr_t>(aVm);
            stContext.aRegisters[30] = 0xCAFE;
            stContext.uNextAddress = 0xBEEF;
            OmegaProtectionHook(&stContext, 0, 0);
            memcpy(&uFlag, aVm + 0x120, 4);
            bool bSuppress = uPc == 0x100C4 && uOpcode == 0x750A6528;
            assert(stContext.uNextAddress == (bSuppress ? 0xCAFE : 0xBEEF));
            assert(uFlag == (bSuppress ? 0 : 1));
        }
    for (uint32_t uHook = 1; uHook < 4; ++uHook)
    {
        stRuntimeContext stContext{};
        stContext.aRegisters[0] = 123;
        stContext.aRegisters[30] = 0xABCD;
        OmegaProtectionHook(&stContext, uHook, 0);
        assert(stContext.uNextAddress == 0xABCD);
        assert(stContext.aRegisters[0] == (uHook == 3 ? 0 : 123));
    }
    stRuntimeContext stContext{};
    stContext.uNextAddress = 123;
    OmegaGameplayHook(&stContext, 99, 0);
    OmegaProtectionHook(&stContext, 99, 0);
    assert(stContext.uNextAddress == 123);
    OmegaProtectionHook(&stContext, 0, 0);
    assert(stContext.uNextAddress == 123);
    OmegaGameplayHook(nullptr, 0, 0);
    OmegaProtectionHook(nullptr, 0, 0);
    puts("C++ runtime handler checks passed");
}
