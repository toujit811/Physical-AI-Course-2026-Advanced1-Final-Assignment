import hashlib
import json
from pathlib import Path
import unittest


class PortManifestTests(unittest.TestCase):
    def test_manifest_covers_every_integrated_module_with_its_actual_hash(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'manifests/code-port.json').read_text())
        hashes = {r['integrated_path']: r['integrated_sha256'] for r in manifest['modules']}
        hashes.update({r['path']: r['sha256'] for r in manifest['new_modules']})
        actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (root / 'src/go2_ppo').glob('*.py')}
        self.assertEqual(hashes, actual)
