"""License security: no fake Pro; Free always works; cryptographic verification."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensing import (LicenseError, activate_key, activation_ready, free_edition,
                       normalize_key, read_edition, remove_local_activation,
                       verify_receipt)


class FakeServer(io.BytesIO):
    pass


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode("ascii")
        self.payload = {"app":"gamegrave", "edition":"pro", "license_id":"abc-123",
                        "type":"lifetime", "schema":1}

    def make_signed(self, payload=None):
        obj = self.payload.copy() if payload is None else payload
        encoded = json.dumps(obj, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":")).encode()
        return {"payload":obj,
                "signature":base64.b64encode(self.private.sign(encoded)).decode("ascii")}

    def test_free_is_available_without_receipt_or_live_service(self):
        with tempfile.TemporaryDirectory() as d:
            edition = read_edition(Path(d)/"no-license.json")
            self.assertEqual(edition.name,"Free")
            self.assertFalse(edition.is_pro)
            self.assertFalse(activation_ready())
            self.assertIn('No key',free_edition().message)

    def test_signed_pro_receipt_verifies_offline(self):
        receipt = self.make_signed()
        self.assertTrue(verify_receipt(receipt,self.public).is_pro)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/"pro.json"
            f.write_text(json.dumps(receipt))
            self.assertTrue(read_edition(f,self.public).is_pro)

    def test_editing_edition_or_license_id_cannot_unlock_pro(self):
        proof = self.make_signed()
        for field,value in [('license_id','forged-id'),('edition','free'),('app','anotherapp')]:
            changed=json.loads(json.dumps(proof))
            changed['payload'][field]=value
            with self.subTest(field=field), self.assertRaises(LicenseError):
                verify_receipt(changed,self.public)

    def test_unsigned_false_key_and_extra_fields_fail(self):
        for item in ({'payload':self.payload,'signature':'fake'},
                     {'payload':{**self.payload, 'pro':True},'signature':self.make_signed()['signature']},
                     {'pro':True}):
            with self.subTest(item=item), self.assertRaises(LicenseError):
                verify_receipt(item,self.public)

    def test_pro_from_other_product_does_not_work(self):
        other = self.make_signed({**self.payload,'app':'otherproduct'})
        with self.assertRaises(LicenseError):
            verify_receipt(other,self.public)

    def test_bad_receipts_and_oversized_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pro.json'
            for contents in ('{bad-json', '{"pro":true}', 'a'*9000):
                p.write_text(contents)
                with self.subTest(contents=contents[:8]):
                    self.assertEqual(read_edition(p,self.public).name,'Free')

    def test_preview_activation_does_not_contact_web_or_write_key(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'proof.json'
            with self.assertRaisesRegex(LicenseError,'not available in this preview'):
                activate_key('GG-1234-5678-ABCD',destination=p,
                             opener=lambda req, timeout=10: (_ for _ in ()).throw(AssertionError('web call')))
            self.assertFalse(p.exists())

    def test_online_activation_checks_signed_response_and_never_saves_key(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'proof.json'
            payload = json.dumps(self.make_signed()).encode('utf-8')
            def server(request, timeout=10):
                body = json.loads(request.data.decode('utf-8'))
                self.assertEqual(body, {'product':'gamegrave','license_key':'GG-1234-5678-ABCD'})
                self.assertEqual(timeout,10)
                return FakeServer(payload)
            edition=activate_key('gg-1234-5678-abcd',url='https://license.example.test/activate',
                                 public_key=self.public,opener=server,destination=p)
            self.assertTrue(edition.is_pro)
            self.assertNotIn('GG-1234-5678-ABCD',p.read_text())
            self.assertTrue(read_edition(p,self.public).is_pro)
            remove_local_activation(p)
            self.assertEqual(read_edition(p,self.public).name,'Free')

    def test_forged_online_response_cannot_unlock_pro(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'proof.json'
            bogus={'payload':self.payload,'signature':base64.b64encode(b'0'*64).decode()}
            def server(req, timeout=10): return FakeServer(json.dumps(bogus).encode())
            with self.assertRaises(LicenseError):
                activate_key('GG-1234-5678-ABCD',url='https://license.example.test/activate',
                             public_key=self.public,opener=server,destination=p)
            self.assertFalse(p.exists())

    def test_key_format_and_https_only(self):
        self.assertEqual(normalize_key('  gg-1234-5678-abcd '),'GG-1234-5678-ABCD')
        for value in ('', 'x', 'a'*150, 'not valid /key'):
            with self.subTest(value=value),self.assertRaises(LicenseError):
                normalize_key(value)
        self.assertFalse(activation_ready('http://example.com',self.public))
        self.assertTrue(activation_ready('https://example.com',self.public))

    def test_installer_has_uninstaller_and_non_admin_install(self):
        script=(Path(__file__).parents[1]/'installer'/'GameGrave.iss').read_text()
        self.assertIn('PrivilegesRequired=lowest',script)
        self.assertIn('UninstallDisplayIcon=',script)
        self.assertIn('GameGrave.exe',script)
        self.assertIn('localappdata',script)


if __name__ == '__main__':
    unittest.main()
