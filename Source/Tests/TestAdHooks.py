import re
import struct
import unittest
import zipfile
from pathlib import Path


class clAdHookTests(unittest.TestCase):
    def test_learnings_hooks_match_supplied_ipa_class_methods(self):
        pRoot = Path(__file__).resolve().parents[2]
        pInput = pRoot / "com.oakever.gemcoloring-1.23.0-Decrypted.ipa"
        if not pInput.exists():
            self.skipTest("Colorever 1.23.0 IPA is required for binary integration verification")
        with zipfile.ZipFile(pInput) as stArchive:
            byImage = stArchive.read("Payload/Colorever.app/Frameworks/UnityFramework.framework/UnityFramework")
        self.assertEqual(struct.unpack_from("<I", byImage)[0], 0xFEEDFACF)
        aSegments = []
        uClassList = 0
        uClassListSize = 0
        uOffset = 32
        for _ in range(struct.unpack_from("<I", byImage, 16)[0]):
            uCommand, uSize = struct.unpack_from("<II", byImage, uOffset)
            if uCommand == 25:
                uAddress, uLength, uFile = struct.unpack_from("<QQQ", byImage, uOffset + 24)
                aSegments.append((uAddress, uLength, uFile))
                uSections = struct.unpack_from("<I", byImage, uOffset + 64)[0]
                for uIndex in range(uSections):
                    uSection = uOffset + 72 + uIndex * 80
                    if byImage[uSection:uSection + 16].rstrip(b"\0") == b"__objc_classlist":
                        uClassListSize = struct.unpack_from("<Q", byImage, uSection + 40)[0]
                        uClassList = struct.unpack_from("<I", byImage, uSection + 48)[0]
            uOffset += uSize

        def file_offset(uAddress):
            return next(uFile + uAddress - uBase for uBase, uSize, uFile in aSegments if uBase <= uAddress < uBase + uSize)

        def pointer(uAddress):
            return struct.unpack_from("<Q", byImage, file_offset(uAddress))[0] & 0xFFFFFFFF

        def string(uAddress):
            uFile = file_offset(uAddress)
            return byImage[uFile:byImage.index(b"\0", uFile)].decode("utf-8")

        uMetaclass = 0
        for uOffset in range(uClassList, uClassList + uClassListSize, 8):
            uClass = struct.unpack_from("<Q", byImage, uOffset)[0] & 0xFFFFFFFF
            uData = pointer(uClass + 32) & ~7
            if string(pointer(uData + 24)) == "_TtC15LearningsAdsKit8MeeviiAd":
                uMetaclass = pointer(uClass)
                break
        self.assertNotEqual(uMetaclass, 0)
        uMethods = pointer((pointer(uMetaclass + 32) & ~7) + 32)
        uFlags, uCount = struct.unpack_from("<II", byImage, file_offset(uMethods))
        self.assertTrue(uFlags & 0x80000000)
        aMethods = {}
        for uIndex in range(uCount):
            uEntry = uMethods + 8 + 12 * uIndex
            iName, iTypes = struct.unpack_from("<ii", byImage, file_offset(uEntry))
            aMethods[string(pointer(uEntry + iName))] = string(uEntry + 4 + iTypes)
        strSource = (pRoot / "Source/Mod/AdDisabler.m").read_text()
        self.assertIn('objc_getMetaClass("_TtC15LearningsAdsKit8MeeviiAd")', strSource)
        strHooks = strSource.split("static void InstallLearningsHooks(void)")[1].split("static void ImageAdded")[0]
        aHooks = re.findall(r'Replace\(clTarget, "([^"]+)", \(IMP\)\w+, "([^"]+)"\)', strHooks)
        self.assertEqual(len(aHooks), 6)
        for strSelector, strEncoding in aHooks:
            with self.subTest(selector=strSelector):
                self.assertEqual(aMethods.get(strSelector), strEncoding)


if __name__ == "__main__":
    unittest.main()
