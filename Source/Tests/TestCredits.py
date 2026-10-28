import importlib.util
import json
import plistlib
import struct
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path
import TestPackage

pstSpec = importlib.util.spec_from_file_location("credits_package", Path(__file__).parents[1] / "Mod/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


class clCreditsTests(unittest.TestCase):
    def setUp(self):
        self.m_stSettings = patch.object(mod, "apply_settings_assets", return_value=({}, {}, {}))
        self.m_stSettings.start()
        self.addCleanup(self.m_stSettings.stop)
        self.m_stPowerups = patch.object(mod, "apply_powerups", return_value=(b"test UnityFramework", {"hooks": []}))
        self.m_stPowerups.start()
        self.addCleanup(self.m_stPowerups.stop)
        self.m_stSigning = patch.object(mod, "apply_signing_compatibility", return_value=(b"test anortx", {}))
        self.m_stSigning.start()
        self.addCleanup(self.m_stSigning.stop)
        self.m_stTemporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.m_stTemporary.cleanup)
        self.m_pRoot = Path(self.m_stTemporary.name)
        (self.m_pRoot / "Build/Release").mkdir(parents=True)
        (self.m_pRoot / "Source/Mod/Resources").mkdir(parents=True)
        stConfig = {"ProjectName": "ExampleMod", "SdkVersion": "16.5", "MinimumIOSVersion": "15.0", "CxxStandard": "c++2b"}
        (self.m_pRoot / "Project.json").write_text(json.dumps(stConfig))
        byLibrary = bytearray(TestPackage.image(uFileType=6))
        self.m_uSymbols = len(byLibrary)
        byStrings = b"\0_OmegaGameplayHook\0_OmegaProtectionHook\0"
        struct.pack_into("<II", byLibrary, 16, 3, 200)
        struct.pack_into("<6I", byLibrary, 208, 2, 24, self.m_uSymbols, 2, self.m_uSymbols + 32, len(byStrings))
        byLibrary.extend(struct.pack("<IBBHQ", 1, 0xF, 1, 0, 0x100000400))
        byLibrary.extend(struct.pack("<IBBHQ", len(b"\0_OmegaGameplayHook\0"), 0xF, 1, 0, 0x100000404))
        byLibrary.extend(byStrings)
        (self.m_pRoot / "Build/Release/ExampleMod.dylib").write_bytes(byLibrary)
        self.m_byLogo = (Path(__file__).parents[1] / "Mod/Resources/Omega172.png").read_bytes()
        (self.m_pRoot / "Source/Mod/Resources/Omega172.png").write_bytes(self.m_byLogo)
        self.m_byPlist = plistlib.dumps({"CFBundleIdentifier": "com.oakever.gemcoloring", "CFBundleShortVersionString": "1.23.0", "CFBundleDisplayName": "Original", "CFBundleExecutable": "Example", "CFBundleVersion": "12"}, fmt=plistlib.FMT_BINARY)
        self.m_pInput = self.m_pRoot / "Original.ipa"
        with zipfile.ZipFile(self.m_pInput, "w") as z:
            z.writestr("Payload/Example.app/Info.plist", self.m_byPlist)
            z.writestr("Payload/Example.app/Example", TestPackage.image())
            z.writestr("Payload/Example.app/Frameworks/UnityFramework.framework/UnityFramework", b"test UnityFramework")
            z.writestr("Payload/Example.app/Frameworks/anortx.framework/anortx", b"test anortx")

    def test_logo_is_packaged_without_changing_app_identity(self):
        stReport = mod.package(self.m_pRoot, str(self.m_pInput))
        with zipfile.ZipFile(stReport["output"]) as z:
            self.assertEqual(z.read("Payload/Example.app/Omega172.png"), self.m_byLogo)
            self.assertEqual(z.read("Payload/Example.app/Info.plist"), self.m_byPlist)
            self.assertEqual(z.getinfo("Payload/Example.app/Omega172.png").external_attr >> 16, 0o100644)
        self.assertEqual(stReport["branding"], "Mod by Omega172")

    def test_invalid_logo_is_rejected(self):
        (self.m_pRoot / "Source/Mod/Resources/Omega172.png").write_bytes(b"invalid")
        with self.assertRaisesRegex(ValueError, "Expected PNG"):
            mod.package(self.m_pRoot, str(self.m_pInput))

    def test_existing_logo_is_not_overwritten(self):
        with zipfile.ZipFile(self.m_pInput, "a") as z:
            z.writestr("Payload/Example.app/Omega172.png", b"existing app resource")
        with self.assertRaisesRegex(ValueError, "Invalid custom added file"):
            mod.package(self.m_pRoot, str(self.m_pInput))

    def test_missing_cpp_export_is_rejected(self):
        pLibrary = self.m_pRoot / "Build/Release/ExampleMod.dylib"
        byLibrary = bytearray(pLibrary.read_bytes())
        byLibrary[self.m_uSymbols + 4] = 0xE
        pLibrary.write_bytes(byLibrary)
        with self.assertRaisesRegex(ValueError, r"lacks C\+\+ runtime handlers"):
            mod.package(self.m_pRoot, str(self.m_pInput))


if __name__ == "__main__":
    unittest.main()
