import hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sfx_vault.updates import GitHubClient,LocalTestClient,Release,UpdateError,download,verify_installer,version_tuple,repository

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.payload=b'MZ'+bytes(range(128))*100; self.sha=hashlib.sha256(self.payload).hexdigest()
        self.client=GitHubClient('TobiTired/SFX-Vault')
    def document(self,version='0.7.1'):
        return dict(tag_name='v'+version,draft=False,prerelease=False,body='Test notes',assets=[dict(name=f'SFX-Vault-Setup-{version}.exe',state='uploaded',size=len(self.payload),digest='sha256:'+self.sha,browser_download_url=f'https://github.com/TobiTired/SFX-Vault/releases/download/v{version}/SFX-Vault-Setup-{version}.exe')])
    def test_semantic_comparison(self):
        self.assertGreater(version_tuple('0.10.0'),version_tuple('0.9.9'))
        for invalid in ('1.0','0.7.1-beta','01.0.0','v0.7.1.0','../0.7.1'):
            with self.assertRaises(UpdateError): version_tuple(invalid)
        self.assertIsNone(self.client.parse(self.document('0.7.0'),'0.7.0'))
        self.assertIsNone(self.client.parse(self.document('0.6.0'),'0.7.0'))
    def test_valid_release_and_notes(self):
        release=self.client.parse(self.document(),'0.7.0'); self.assertEqual(release.version,'0.7.1'); self.assertEqual(release.notes,'Test notes')
    def test_drafts_prereleases_and_malformed_blocked(self):
        for doc in ({},[],self.document()|dict(draft=True),self.document()|dict(prerelease=True),self.document()|dict(body=[]),self.document()|dict(assets=[])):
            with self.assertRaises(UpdateError): self.client.parse(doc,'0.7.0')
    def test_checksum_sidecar_fallback(self):
        doc=self.document(); doc['assets'][0].pop('digest'); doc['assets'].append(dict(name='SHA256SUMS.txt',state='uploaded',browser_download_url='https://github.com/TobiTired/SFX-Vault/releases/download/v0.7.1/SHA256SUMS.txt'))
        with patch.object(self.client,'read',return_value=(self.sha+'  SFX-Vault-Setup-0.7.1.exe\n').encode()): self.assertEqual(self.client.parse(doc,'0.7.0').sha256,self.sha)
        with patch.object(self.client,'read',return_value=b'bad checksum'):
            with self.assertRaises(UpdateError): self.client.parse(doc,'0.7.0')
    def test_unexpected_repository_or_address_blocked(self):
        for url in ('http://github.com/x.exe','https://evil.example/x.exe','https://github.com/another/repo/releases/download/v0.7.1/SFX-Vault-Setup-0.7.1.exe'):
            doc=self.document(); doc['assets'][0]['browser_download_url']=url
            with self.assertRaises(UpdateError): self.client.parse(doc,'0.7.0')
        for value in ('https://github.com/owner/repo','owner/../repo','owner/repo?token=x'):
            with self.assertRaises(UpdateError): repository(value)
    def test_verified_download_progress_and_recheck(self):
        release=self.client.parse(self.document(),'0.7.0'); progress=[]
        with patch.object(self.client,'stream',return_value=io.BytesIO(self.payload)):
            path=download(self.client,release,lambda count,total:progress.append(count),cache=self.root)
        self.assertEqual(path.read_bytes(),self.payload); self.assertEqual(progress[-1],len(self.payload)); verify_installer(path,self.sha)
        path.write_bytes(b'MZtampered')
        with self.assertRaises(UpdateError): verify_installer(path,self.sha)
    def test_failed_truncated_or_corrupt_download_leaves_no_installer(self):
        for payload in (b'MZtruncated',self.payload[:-1]+b'x',self.payload+b'extra'):
            with patch.object(self.client,'stream',return_value=io.BytesIO(payload)):
                with self.assertRaises(UpdateError): download(self.client,self.client.parse(self.document(),'0.7.0'),cache=self.root)
            self.assertEqual(list(self.root.iterdir()),[])
    def test_cancellation_and_network_failures(self):
        with patch.object(self.client,'read',side_effect=OSError('offline')):
            with self.assertRaisesRegex(UpdateError,'Cannot check GitHub'): self.client.latest('0.7.0')
        with patch.object(self.client,'stream',return_value=io.BytesIO(self.payload)):
            with self.assertRaisesRegex(UpdateError,'cancelled'): download(self.client,self.client.parse(self.document(),'0.7.0'),cancelled=lambda:True,cache=self.root)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_local_test_feed_is_explicit_and_confined(self):
        installer=self.root/'test.exe'; installer.write_bytes(self.payload); manifest=self.root/'test-update.json'
        manifest.write_text(json.dumps(dict(version='0.7.1',installer='test.exe',sha256=self.sha,notes='Test only')))
        client=LocalTestClient(manifest); release=client.latest('0.7.0'); self.assertTrue(release.test)
        path=download(client,release,cache=self.root); self.assertEqual(path.read_bytes(),self.payload)
        manifest.write_text(json.dumps(dict(version='0.7.1',installer='../outside.exe',sha256=self.sha,notes='Test only')))
        with self.assertRaises(UpdateError): client.latest('0.7.0')
