import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

pstSpec = importlib.util.spec_from_file_location("progress_package", Path(__file__).parents[1] / "Mod/Package.py")
mod = importlib.util.module_from_spec(pstSpec)
pstSpec.loader.exec_module(mod)


class clPackagingProgressTests(unittest.TestCase):
    def setUp(self):
        self.m_hTemporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.m_hTemporary.cleanup)
        self.m_pRoot = Path(self.m_hTemporary.name)
        (self.m_pRoot / "Build/Release").mkdir(parents=True)

    def test_duplicate_packaging_is_rejected(self):
        import fcntl

        with (self.m_pRoot / "Build/Release/.Packaging.lock").open("a") as hLock:
            fcntl.flock(hLock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(mod, "package") as hPackage, self.assertRaisesRegex(ValueError, "already running"):
                mod.package_with_progress(self.m_pRoot)
            hPackage.assert_not_called()

    def test_lock_is_released_after_failure(self):
        with patch.object(mod, "package", side_effect=ValueError("test failure")):
            with self.assertRaisesRegex(ValueError, "test failure"):
                mod.package_with_progress(self.m_pRoot)
        with patch.object(mod, "package", return_value={"output": "test.ipa"}) as hPackage:
            self.assertEqual(mod.package_with_progress(self.m_pRoot, "input.ipa"), {"output": "test.ipa"})
            hPackage.assert_called_once_with(self.m_pRoot, "input.ipa")


if __name__ == "__main__":
    unittest.main()
