#pragma once
#include <stddef.h>
#include <stdint.h>

struct alignas(16) stRuntimeContext
{
    uint64_t aRegisters[31];
    uint64_t uFlags;
    uint8_t aVectorRegisters[512];
    uint64_t uNextAddress;
    uint64_t uHookId;
};

static_assert(offsetof(stRuntimeContext, uFlags) == 248);
static_assert(offsetof(stRuntimeContext, aVectorRegisters) == 256);
static_assert(offsetof(stRuntimeContext, uNextAddress) == 768);
static_assert(offsetof(stRuntimeContext, uHookId) == 776);
static_assert(sizeof(stRuntimeContext) == 784);

extern "C" __attribute__((visibility("default"))) void OmegaGameplayHook(stRuntimeContext *pstContext, uint32_t uHookId, uintptr_t uImageBase);
extern "C" __attribute__((visibility("default"))) void OmegaProtectionHook(stRuntimeContext *pstContext, uint32_t uHookId, uintptr_t uImageBase);
