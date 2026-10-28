import bz2
import hashlib
import importlib.util
import json
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

pstSpec = importlib.util.spec_from_file_location("settings_package", Path(__file__).parents[1] / "Mod/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


def delta_integer(iValue):
    return (abs(iValue) | ((1 << 63) if iValue < 0 else 0)).to_bytes(8, "little")


def asset_delta(aControl, byDiff, byExtra, uSize):
    byControl = bz2.compress(b"".join(delta_integer(iValue) for stControl in aControl for iValue in stControl))
    byDiff = bz2.compress(byDiff)
    return b"BSDIFF40" + b"".join(delta_integer(iValue) for iValue in (len(byControl), len(byDiff), uSize)) + byControl + byDiff + bz2.compress(byExtra)


class clSettingsDeltaTests(unittest.TestCase):
    def test_copy_insert_signed_seek_and_byte_differences(self):
        byDelta = asset_delta([(3, 1, -3), (3, 1, 0)], bytes([0, 1, 255, 0, 0, 0]), b"!?", 8)
        self.assertEqual(mod.apply_asset_delta(b"abcdef", byDelta), b"acb!abc?")

    def test_truncated_and_out_of_bounds_deltas_are_rejected(self):
        for byDelta in (b"bad", asset_delta([(4, 0, 0)], bytes(3), b"", 4), asset_delta([(0, 0, 1)], b"", b"", 1), asset_delta([(-1, 2, 0)], b"", b"xy", 1)):
            with self.subTest(delta=byDelta[:32]), self.assertRaises(ValueError):
                mod.apply_asset_delta(b"abc", byDelta)

    def test_seek_only_control_can_precede_a_copy(self):
        byDelta = asset_delta([(0, 0, 1), (2, 0, 0)], bytes(2), b"", 2)
        self.assertEqual(mod.apply_asset_delta(b"abc", byDelta), b"bc")


class clSettingsAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s_pRoot = Path(__file__).resolve().parents[2]
        cls.s_pInput = cls.s_pRoot / "com.oakever.gemcoloring-1.23.0-Decrypted.ipa"
        if not cls.s_pInput.exists():
            raise unittest.SkipTest("Colorever 1.23.0 IPA is required for settings asset verification")

    def test_asset_hash_manifest_dependencies_and_original_version_are_preserved(self):
        strFolder = "Payload/Colorever.app/Data/Raw/AssetBundle/"
        with zipfile.ZipFile(self.s_pInput) as zInput:
            stOriginal = json.loads(zInput.read(strFolder + "manifest.json"))
            aModified, aAdded, stReport = mod.apply_settings_assets(zInput, "Payload/Colorever.app", self.s_pRoot)
            byOriginal = zInput.read(strFolder + mod.STR_SETTINGS_BUNDLE)
        self.assertEqual(set(aModified), {strFolder + "manifest.json"})
        self.assertEqual(len(aAdded), 1)
        byBundle, uMode = aAdded[strFolder + stReport["bundle"]]
        self.assertEqual(hashlib.sha256(byBundle).hexdigest(), mod.STR_SETTINGS_PATCHED_SHA256)
        self.assertEqual(byBundle[:32], byOriginal[:32])
        self.assertEqual(uMode, 0o100644)
        self.assertEqual(stReport["message"], mod.STR_SETTINGS_MESSAGE)
        stManifest = json.loads(aModified[strFolder + "manifest.json"])
        for stBefore, stAfter in zip(stOriginal["BundleInfos"], stManifest["BundleInfos"]):
            stExpected = dict(stBefore)
            stExpected["DEP"] = [stReport["bundle"] if strName == mod.STR_SETTINGS_BUNDLE else strName for strName in stBefore.get("DEP", [])]
            if stBefore["N"] == "local_ui.ab":
                stExpected.update(BN=stReport["bundle"], S=len(byBundle), C=zlib.crc32(byBundle).to_bytes(4, "little").hex())
            self.assertEqual(stAfter, stExpected)
        for strKey in stOriginal.keys() - {"BundleInfos"}:
            self.assertEqual(stManifest[strKey], stOriginal[strKey])

    def test_wrong_bundle_and_corrupted_patch_are_rejected(self):
        with zipfile.ZipFile(self.s_pInput) as zInput:
            with patch.object(mod, "STR_SETTINGS_ORIGINAL_SHA256", "invalid"), self.assertRaisesRegex(ValueError, "does not match"):
                mod.apply_settings_assets(zInput, "Payload/Colorever.app", self.s_pRoot)
            with patch.object(mod, "STR_SETTINGS_PATCHED_SHA256", "invalid"), self.assertRaisesRegex(ValueError, "verification failed"):
                mod.apply_settings_assets(zInput, "Payload/Colorever.app", self.s_pRoot)


if __name__ == "__main__":
    unittest.main()
