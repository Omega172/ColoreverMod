import hashlib
import importlib.util
import struct
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

pstSpec = importlib.util.spec_from_file_location("signing_package", Path(__file__).parents[1] / "Mod/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


class clSigningTests(unittest.TestCase):
    def test_unknown_framework_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            mod.apply_signing_compatibility(b"unknown binary")

    def test_out_of_range_branches_are_rejected(self):
        for uTarget in (1, 1 << 27):
            with self.subTest(target=uTarget), self.assertRaisesRegex(ValueError, "branch range"):
                mod.runtime.branch(0, uTarget)


class clSigningBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pInput = Path(__file__).resolve().parents[2] / "com.oakever.gemcoloring-1.23.0-Decrypted.ipa"
        if not pInput.exists():
            raise unittest.SkipTest("Colorever 1.23.0 IPA is required for binary integration verification")
        with zipfile.ZipFile(pInput) as stArchive:
            cls.s_byOriginal = stArchive.read("Payload/Colorever.app/Frameworks/anortx.framework/anortx")

    def test_only_signed_bridges_and_header_padding_change(self):
        byPatched, stReport = mod.apply_signing_compatibility(self.s_byOriginal)
        self.assertEqual(stReport["dispatcher"], "OmegaProtectionHook")
        self.assertEqual(len(stReport["hooks"]), 4)
        aRanges = [(int(stReport["cave"], 16), int(stReport["cave"], 16) + stReport["code_size"])]
        for stHook in stReport["hooks"]:
            uSite = int(stHook["file_offset"], 16)
            uInstruction = struct.unpack_from("<I", byPatched, uSite)[0]
            self.assertEqual(uInstruction & 0xFC000000, 0x14000000)
            iDelta = uInstruction & 0x3FFFFFF
            if iDelta & 0x2000000:
                iDelta -= 0x4000000
            self.assertEqual(uSite + iDelta * 4, int(stHook["trampoline"], 16))
            aRanges.append((uSite, uSite + 4))
        uCursor = 0
        for uStart, uEnd in sorted(aRanges):
            self.assertEqual(byPatched[uCursor:uStart], self.s_byOriginal[uCursor:uStart])
            uCursor = uEnd
        self.assertEqual(byPatched[uCursor:], self.s_byOriginal[uCursor:])
        self.assertEqual(byPatched[0x60C00:0x60C34], self.s_byOriginal[0x60C00:0x60C34])
        self.assertEqual(stReport["patched_sha256"], hashlib.sha256(byPatched).hexdigest())
        uCache = int(stReport["cache_file_offset"], 16)
        self.assertEqual(byPatched[uCache:uCache + 8], bytes(8))

    def test_patched_framework_is_rejected(self):
        byPatched, _ = mod.apply_signing_compatibility(self.s_byOriginal)
        with self.assertRaisesRegex(ValueError, "does not match"):
            mod.apply_signing_compatibility(byPatched)

    def test_instruction_guard_is_independent_of_hash_guard(self):
        byChanged = bytearray(self.s_byOriginal)
        byChanged[mod.A_PROTECTION_HOOKS[0][1]] ^= 1
        with patch.object(mod, "STR_ANORTX_SHA256", hashlib.sha256(byChanged).hexdigest()):
            with self.assertRaisesRegex(ValueError, "Unexpected runtime hook"):
                mod.apply_signing_compatibility(byChanged)

    def test_nonempty_padding_is_rejected(self):
        byChanged = bytearray(self.s_byOriginal)
        uCave = mod.runtime.image_info(byChanged)[0]
        byChanged[uCave] = 1
        with patch.object(mod, "STR_ANORTX_SHA256", hashlib.sha256(byChanged).hexdigest()):
            with self.assertRaisesRegex(ValueError, "padding"):
                mod.apply_signing_compatibility(byChanged)

    def test_all_protection_prefix_guards_are_independent(self):
        for uOffset, strExpected in mod.A_PROTECTION_PREFIXES:
            byChanged = bytearray(self.s_byOriginal)
            byChanged[uOffset + 8] ^= 1
            with self.subTest(offset=uOffset), patch.object(mod, "STR_ANORTX_SHA256", hashlib.sha256(byChanged).hexdigest()):
                with self.assertRaisesRegex(ValueError, "Unexpected protection"):
                    mod.apply_signing_compatibility(byChanged)

    def test_cache_is_writable_padding_outside_sections(self):
        uCache, uFile = mod.runtime.cache_slot(self.s_byOriginal)
        self.assertEqual(uCache % 8, 0)
        self.assertEqual(self.s_byOriginal[uFile:uFile + 8], bytes(8))
        uOffset = 32
        bFound = False
        for _ in range(struct.unpack_from("<I", self.s_byOriginal, 16)[0]):
            uCommand, uSize = struct.unpack_from("<II", self.s_byOriginal, uOffset)
            if uCommand == 0x19:
                uVm, uVmSize, uPosition, uFileSize, iMaximum, iInitial, uCount = struct.unpack_from("<QQQQiiI", self.s_byOriginal, uOffset + 24)
                if uVm <= uCache < uVm + uVmSize:
                    self.assertEqual(self.s_byOriginal[uOffset + 8:uOffset + 24].split(b"\0", 1)[0], b"__DATA")
                    self.assertTrue(iInitial & 2)
                    self.assertLessEqual(uCache + 8, uVm + uFileSize)
                    for iSection in range(uCount):
                        uStart, uLength = struct.unpack_from("<QQ", self.s_byOriginal, uOffset + 72 + iSection * 80 + 32)
                        self.assertFalse(uStart < uCache + 8 and uCache < uStart + uLength)
                    bFound = True
            uOffset += uSize
        self.assertTrue(bFound)


if __name__ == "__main__":
    unittest.main()
