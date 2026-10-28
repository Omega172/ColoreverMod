import importlib.util
import json
import plistlib
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

stSpec = importlib.util.spec_from_file_location("mod_package", Path(__file__).parents[1] / "Tools/Package.py")
mod = importlib.util.module_from_spec(stSpec)
stSpec.loader.exec_module(mod)


def image(uCrypt=0, uFirst=0x400, uFileType=2):
    byData = bytearray(0x500)
    struct.pack_into("<8I", byData, 0, 0xFEEDFACF, 0x0100000C, 0, uFileType, 2, 176, 0, 0)
    struct.pack_into("<II16sQQQQiiII", byData, 32, 0x19, 152, b"__TEXT", 0x100000000, 0x1000, 0, len(byData), 7, 5, 1, 0)
    byData[104:120] = b"__text".ljust(16, b"\0")
    byData[120:136] = b"__TEXT".ljust(16, b"\0")
    struct.pack_into("<QQIIIIIIII", byData, 136, 0x100000000 + uFirst, 64, uFirst, 2, 0, 0, 0x80000400, 0, 0, 0)
    struct.pack_into("<6I", byData, 184, 0x2C, 24, uFirst, 64, uCrypt, 0)
    byData[uFirst:uFirst + 64] = bytes(range(64))
    return bytes(byData)


def universal(byArm, strEndian=">", bFat64=False):
    byOther = b"other architecture data"
    byMagic = bytes.fromhex({(">", False): "cafebabe", ("<", False): "bebafeca", (">", True): "cafebabf", ("<", True): "bfbafeca"}[(strEndian, bFat64)])
    byResult = bytearray(0x2000 + len(byOther))
    byResult[:8] = byMagic + struct.pack(strEndian + "I", 2)
    strFormat = "IIQQII" if bFat64 else "IIIII"
    aArm = (0x0100000C, 0, 0x1000, len(byArm), 12) + ((0,) if bFat64 else ())
    aOther = (0x01000007, 0, 0x2000, len(byOther), 12) + ((0,) if bFat64 else ())
    struct.pack_into(strEndian + strFormat, byResult, 8, *aArm)
    struct.pack_into(strEndian + strFormat, byResult, 8 + struct.calcsize(strEndian + strFormat), *aOther)
    byResult[0x1000:0x1000 + len(byArm)] = byArm
    byResult[0x2000:] = byOther
    return bytes(byResult)


class clPackageTests(unittest.TestCase):
    def setUp(self):
        self.m_stTemporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.m_stTemporary.cleanup)
        self.m_pRoot = Path(self.m_stTemporary.name)
        self.m_stConfig = {"ProjectName": "ExampleMod", "SdkVersion": "16.5", "MinimumIOSVersion": "15.0", "CxxStandard": "c++2b"}
        self.write_config()
        pRelease = self.m_pRoot / "Build/Release"
        pRelease.mkdir(parents=True)
        (pRelease / "ExampleMod.dylib").write_bytes(image(uFileType=6))
        self.m_pInput = self.m_pRoot / "Original.ipa"
        self.m_strApp = "Payload/Example.app/"
        self.m_byPlist = plistlib.dumps({"CFBundleIdentifier": "com.example.original", "CFBundleDisplayName": "Original Name", "CFBundleExecutable": "Example", "CFBundleVersion": "42", "CFBundleShortVersionString": "2.3"}, fmt=plistlib.FMT_BINARY)
        self.write_ipa()

    def write_config(self):
        (self.m_pRoot / "Project.json").write_text(json.dumps(self.m_stConfig), encoding="utf-8")

    def write_ipa(self, byExecutable=None, strExtra=None):
        with zipfile.ZipFile(self.m_pInput, "w") as z:
            z.writestr(self.m_strApp + "Info.plist", self.m_byPlist)
            z.writestr(self.m_strApp + "Example", image() if byExecutable is None else byExecutable)
            z.writestr(self.m_strApp + "Data/Keep.bin", b"unchanged app data")
            z.writestr(self.m_strApp + "_CodeSignature/CodeResources", b"old signature")
            z.writestr(self.m_strApp + "embedded.mobileprovision", b"old profile")
            if strExtra:
                z.writestr(strExtra, b"unsafe")

    def test_package_preserves_app_identity_and_original(self):
        byBefore = self.m_pInput.read_bytes()
        stReport = mod.package(self.m_pRoot, str(self.m_pInput))
        self.assertEqual(self.m_pInput.read_bytes(), byBefore)
        with zipfile.ZipFile(stReport["output"]) as z:
            self.assertEqual(z.read(self.m_strApp + "Info.plist"), self.m_byPlist)
            self.assertEqual(z.read(self.m_strApp + "Data/Keep.bin"), b"unchanged app data")
            self.assertIn(self.m_strApp + "Frameworks/ExampleMod.dylib", z.namelist())
            self.assertNotIn(self.m_strApp + "embedded.mobileprovision", z.namelist())
            self.assertNotIn(self.m_strApp + "_CodeSignature/CodeResources", z.namelist())
            self.assertIn(b"@executable_path/Frameworks/ExampleMod.dylib\0", z.read(self.m_strApp + "Example"))
        self.assertEqual(stReport["bundle_identifier_preserved"], "com.example.original")

    def test_repeated_package_overwrites_output(self):
        stReport = mod.package(self.m_pRoot)
        pOutput = Path(stReport["output"])
        pOutput.write_bytes(b"previous output")
        mod.package(self.m_pRoot)
        self.assertTrue(zipfile.is_zipfile(pOutput))

    def test_failure_preserves_previous_output(self):
        pOutput = Path(mod.package(self.m_pRoot)["output"])
        byPrevious = pOutput.read_bytes()
        self.write_ipa(image(uCrypt=1))
        with self.assertRaisesRegex(ValueError, "Encrypted"):
            mod.package(self.m_pRoot)
        self.assertEqual(pOutput.read_bytes(), byPrevious)

    def test_input_cannot_be_output(self):
        pOutput = Path(mod.package(self.m_pRoot)["output"])
        byBefore = pOutput.read_bytes()
        with self.assertRaisesRegex(ValueError, "must be different"):
            mod.package(self.m_pRoot, str(pOutput))
        self.assertEqual(pOutput.read_bytes(), byBefore)

    def test_invalid_names_and_app_fields_are_rejected(self):
        for strName in ("../Escape", "Has Space", "$(command)", "Name\nValue", ""):
            with self.subTest(strName=strName):
                self.m_stConfig["ProjectName"] = strName
                self.write_config()
                with self.assertRaises(ValueError):
                    mod.load_config(self.m_pRoot)
        self.m_stConfig["ProjectName"] = "ValidMod"
        self.m_stConfig["BundleIdentifier"] = "com.changed.app"
        self.write_config()
        with self.assertRaises(ValueError):
            mod.load_config(self.m_pRoot)

    def test_project_rename_only_changes_mod_artifacts(self):
        self.m_stConfig["ProjectName"] = "RenamedMod"
        self.write_config()
        (self.m_pRoot / "Build/Release/RenamedMod.dylib").write_bytes(image(uFileType=6))
        stReport = mod.package(self.m_pRoot)
        self.assertEqual(Path(stReport["output"]).name, "RenamedMod-NeedsSigning.ipa")
        with zipfile.ZipFile(stReport["output"]) as z:
            self.assertEqual(z.read(self.m_strApp + "Info.plist"), self.m_byPlist)
            self.assertIn(self.m_strApp + "Frameworks/RenamedMod.dylib", z.namelist())

    def test_thin_injection_preserves_executable_sections(self):
        byOriginal = image()
        byResult = mod.inject(byOriginal, "@executable_path/Frameworks/ExampleMod.dylib")
        self.assertEqual(byResult[0x400:], byOriginal[0x400:])
        self.assertEqual(len(byResult), len(byOriginal))
        with self.assertRaisesRegex(ValueError, "already injected"):
            mod.inject(byResult, "@executable_path/Frameworks/ExampleMod.dylib")

    def test_universal_formats_preserve_other_architectures(self):
        for strEndian in (">", "<"):
            for bFat64 in (False, True):
                with self.subTest(strEndian=strEndian, bFat64=bFat64):
                    byOriginal = universal(image(), strEndian, bFat64)
                    byResult = mod.inject(byOriginal, "@executable_path/Frameworks/ExampleMod.dylib")
                    self.assertEqual(byOriginal[:0x1000], byResult[:0x1000])
                    self.assertEqual(byOriginal[0x2000:], byResult[0x2000:])
                    self.assertNotEqual(byOriginal[0x1000:0x1500], byResult[0x1000:0x1500])

    def test_encrypted_and_insufficient_padding_rejected(self):
        for byBad in (image(uCrypt=1), image(uFirst=0x100)):
            with self.assertRaises(ValueError):
                mod.inject(byBad, "@executable_path/Frameworks/ExampleMod.dylib")

    def test_bad_load_command_and_slice_bounds_rejected(self):
        byBad = bytearray(image())
        struct.pack_into("<I", byBad, 36, 0xFFFF)
        with self.assertRaises(ValueError):
            mod.inject(bytes(byBad), "example")
        byFat = bytearray(universal(image()))
        struct.pack_into(">I", byFat, 16, len(byFat) + 1)
        with self.assertRaises(ValueError):
            mod.inject(bytes(byFat), "example")

    def test_unsafe_archive_rejected(self):
        self.write_ipa(strExtra="../Escape")
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
            mod.package(self.m_pRoot)

    def test_app_customization_preserves_metadata(self):
        def customize(zInput, strApp, stInfo, pRoot):
            return {strApp + "/Data/Keep.bin": b"app patch"}, {strApp + "/Logo.png": (b"logo", 0o100644)}, {"customized": True}
        stReport = mod.package(self.m_pRoot, str(self.m_pInput), customize)
        self.assertTrue(stReport["customized"])
        with zipfile.ZipFile(stReport["output"]) as z:
            self.assertEqual(z.read(self.m_strApp + "Info.plist"), self.m_byPlist)
            self.assertEqual(z.read(self.m_strApp + "Data/Keep.bin"), b"app patch")
            self.assertEqual(z.read(self.m_strApp + "Logo.png"), b"logo")

    def test_app_customization_cannot_change_identity(self):
        def customize(zInput, strApp, stInfo, pRoot):
            return {strApp + "/Info.plist": b"replacement metadata"}, {}, {}
        with self.assertRaisesRegex(ValueError, "preserve Info.plist"):
            mod.package(self.m_pRoot, str(self.m_pInput), customize)

    def test_bad_customization_preserves_previous_output(self):
        pOutput = Path(mod.package(self.m_pRoot)["output"])
        byBefore = pOutput.read_bytes()
        for strName in ("../Outside", self.m_strApp + "../Outside", self.m_strApp + "Frameworks/ExampleMod.dylib"):
            with self.subTest(strName=strName):
                def customize(zInput, strApp, stInfo, pRoot):
                    return {}, {strName: (b"unexpected", 0o100644)}, {}
                with self.assertRaises(ValueError):
                    mod.package(self.m_pRoot, str(self.m_pInput), customize)
                self.assertEqual(pOutput.read_bytes(), byBefore)

    def test_http_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            with mod.input_ipa(self.m_pRoot, "http://example.invalid/app.ipa"):
                self.fail("HTTP source accepted")


if __name__ == "__main__":
    unittest.main()
