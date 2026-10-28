#include "RuntimeHooks.h"

extern "C" void OmegaGameplayHook(stRuntimeContext *pstContext, uint32_t uHookId, uintptr_t uImageBase)
{
    (void)uImageBase;
    if (!pstContext || uHookId >= 9)
        return;
    pstContext->uNextAddress += 4;
    if (uHookId < 6)
        pstContext->aRegisters[0] = 999;
    else
        pstContext->aRegisters[9] = static_cast<uint32_t>(pstContext->aRegisters[21]);
}

extern "C" void OmegaProtectionHook(stRuntimeContext *pstContext, uint32_t uHookId, uintptr_t uImageBase)
{
    (void)uImageBase;
    if (!pstContext || uHookId > 3)
        return;
    if (uHookId == 0)
    {
        uintptr_t uVmContext = pstContext->aRegisters[1];
        if (!uVmContext || static_cast<uint32_t>(pstContext->aRegisters[0]) != 0x750A6528)
            return;
        if (*reinterpret_cast<const uint64_t *>(uVmContext + 0x108) != 0x100C4)
            return;
        *reinterpret_cast<uint32_t *>(uVmContext + 0x120) = 0;
    }
    if (uHookId == 3)
        pstContext->aRegisters[0] = 0;
    pstContext->uNextAddress = pstContext->aRegisters[30];
}
