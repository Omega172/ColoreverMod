import importlib.util
import io
import struct
import unittest
import zipfile
from pathlib import Path

pstSpec = importlib.util.spec_from_file_location("compressed_package", Path(__file__).parents[1] / "Tools/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


class clNonSeekable(io.BytesIO):
    def seek(self, *aArguments):
        raise io.UnsupportedOperation("not seekable")


class clCompressedCopyTests(unittest.TestCase):
    def test_compressed_records_survive_new_offsets_and_central_directory(self):
        for uMethod in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            for bDescriptor, bZip64 in ((False, False), (True, False), (False, True)):
                with self.subTest(method=uMethod, descriptor=bDescriptor, zip64=bZip64):
                    hInput = clNonSeekable() if bDescriptor else io.BytesIO()
                    strName = "Asset-" + chr(0x3A9) + ".bin"
                    stEntry = zipfile.ZipInfo(strName, (2025, 2, 3, 4, 5, 6))
                    stEntry.compress_type = uMethod
                    stEntry.external_attr = 0o100640 << 16
                    stEntry.extra = struct.pack("<HH4s", 0xCAFE, 4, b"test")
                    byData = b"unchanged asset data" * 100
                    with zipfile.ZipFile(hInput, "w") as z:
                        with z.open(stEntry, "w", force_zip64=bZip64) as h:
                            h.write(byData)
                    byOriginal = hInput.getvalue()
                    hOutput = io.BytesIO()
                    with zipfile.ZipFile(io.BytesIO(byOriginal)) as zInput, zipfile.ZipFile(hOutput, "w") as zOutput:
                        zOutput.writestr("Prefix.txt", b"changed header offset")
                        uStart = zOutput.start_dir
                        mod.copy_compressed_entry(zInput, zOutput, zInput.getinfo(strName), zInput.start_dir)
                        uEnd = zOutput.start_dir
                        zOutput.writestr("Suffix.txt", b"new file")
                        uOriginalEnd = zInput.start_dir
                    byOutput = hOutput.getvalue()
                    self.assertEqual(byOutput[uStart:uEnd], byOriginal[:uOriginalEnd])
                    with zipfile.ZipFile(io.BytesIO(byOutput)) as z:
                        self.assertIsNone(z.testzip())
                        self.assertEqual(z.read(strName), byData)
                        self.assertEqual(z.getinfo(strName).compress_type, uMethod)
                        self.assertEqual(z.getinfo(strName).external_attr, stEntry.external_attr)
                        self.assertEqual(z.read("Suffix.txt"), b"new file")

    def test_invalid_local_header_and_bounds_are_rejected(self):
        hInput = io.BytesIO()
        with zipfile.ZipFile(hInput, "w") as z:
            z.writestr("Asset", b"data")
        byInput = hInput.getvalue()
        for byArchive, uEnd in ((byInput, 1), (b"BAD!" + byInput[4:], len(byInput))):
            with zipfile.ZipFile(io.BytesIO(byArchive)) as zInput, zipfile.ZipFile(io.BytesIO(), "w") as zOutput:
                with self.assertRaises(ValueError):
                    mod.copy_compressed_entry(zInput, zOutput, zInput.getinfo("Asset"), uEnd)


if __name__ == "__main__":
    unittest.main()
