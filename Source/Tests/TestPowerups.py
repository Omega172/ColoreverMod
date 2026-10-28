import hashlib
import importlib.util
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

pstSpec = importlib.util.spec_from_file_location("powerups_package", Path(__file__).parents[1] / "Mod/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


class clPowerupGuardTests(unittest.TestCase):
    def test_unknown_binary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            mod.apply_powerups(b"unsupported binary")

    def test_wrong_game_or_version_is_rejected(self):
        class clArchive:
            def read(self, strName):
                raise AssertionError("Unsupported apps must be rejected before reading UnityFramework")

        pRoot = Path(__file__).resolve().parents[2]
        for stInfo in ({}, {"CFBundleIdentifier": "com.oakever.gemcoloring", "CFBundleShortVersionString": "1.24.0"}):
            with self.subTest(info=stInfo), self.assertRaisesRegex(ValueError, "requires Colorever"):
                mod.customize(clArchive(), "Payload/Example.app", stInfo, pRoot)


class clPowerupBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pInput = Path(__file__).resolve().parents[2] / "com.oakever.gemcoloring-1.23.0-Decrypted.ipa"
        if not pInput.exists():
            raise unittest.SkipTest("Colorever 1.23.0 IPA is required for binary integration verification")
        with zipfile.ZipFile(pInput) as stArchive:
            cls.s_byOriginal = stArchive.read("Payload/Colorever.app/Frameworks/UnityFramework.framework/UnityFramework")

    def test_only_nine_hook_sites_and_header_bridge_change(self):
        byPatched, stReport = mod.apply_powerups(self.s_byOriginal)
        self.assertEqual(stReport["dispatcher"], "OmegaGameplayHook")
        self.assertEqual(len(stReport["hooks"]), 9)
        self.assertEqual(len(byPatched), len(self.s_byOriginal))
        uCave = int(stReport["cave"], 16)
        aRanges = [(uCave, uCave + stReport["code_size"])]
        for stHook, (strFeature, uOffset, strBefore) in zip(stReport["hooks"], mod.A_POWERUP_PATCHES):
            self.assertEqual(self.s_byOriginal[uOffset:uOffset + 4].hex(), strBefore)
            self.assertEqual(byPatched[uOffset:uOffset + 4].hex(), stHook["after"])
            aRanges.append((uOffset, uOffset + 4))
        uCursor = 0
        for uStart, uEnd in sorted(aRanges):
            self.assertEqual(byPatched[uCursor:uStart], self.s_byOriginal[uCursor:uStart])
            uCursor = uEnd
        self.assertEqual(byPatched[uCursor:], self.s_byOriginal[uCursor:])
        uCache = int(stReport["cache_file_offset"], 16)
        self.assertEqual(byPatched[uCache:uCache + 8], bytes(8))

    def test_already_patched_binary_is_rejected(self):
        byPatched, _ = mod.apply_powerups(self.s_byOriginal)
        with self.assertRaisesRegex(ValueError, "does not match"):
            mod.apply_powerups(byPatched)

    def test_instruction_guard_is_independent_of_hash_guard(self):
        byChanged = bytearray(self.s_byOriginal)
        byChanged[mod.A_POWERUP_PATCHES[0][1]] ^= 1
        with patch.object(mod, "STR_UNITY_SHA256", hashlib.sha256(byChanged).hexdigest()):
            with self.assertRaisesRegex(ValueError, "Unexpected runtime hook"):
                mod.apply_powerups(byChanged)


if __name__ == "__main__":
    unittest.main()
