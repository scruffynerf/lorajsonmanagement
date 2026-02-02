import os
import unittest
from pathlib import Path
from lorajsonmanagement.core.hashing import compute_file_sha256, file_hashes

class TestHashing(unittest.TestCase):
    def setUp(self):
        self.test_file = Path("test_file.bin")
        with open(self.test_file, "wb") as f:
            f.write(b"Hello World")

    def tearDown(self):
        if self.test_file.exists():
            os.remove(self.test_file)

    def test_sha256(self):
        expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
        self.assertEqual(compute_file_sha256(str(self.test_file)), expected)

    def test_crc32(self):
        crc, _ = file_hashes(str(self.test_file))
        # "Hello World" CRC32 is 4a17b156
        self.assertEqual(crc.lower(), "4a17b156")

if __name__ == "__main__":
    unittest.main()
