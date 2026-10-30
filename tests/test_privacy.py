import importlib.util,json,tempfile,unittest
import subprocess,os
from unittest.mock import patch
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('privacy_check',Path(__file__).parents[1]/'tools/privacy_check.py')
privacy=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(privacy)

class PrivacyTests(unittest.TestCase):
    def setUp(self): self.policy={'identity':{'name':'ReleaseIdentity','email':'release'+'@'+'users.noreply.github.com'}}
    def test_home_paths_and_credentials_are_blocked(self):
        self.assertTrue(privacy.inspect_text('C:'+'/'+'Users'+'/'+'example'+'/file',self.policy))
        self.assertTrue(privacy.inspect_text('gh'+'p_'+'x'*30,self.policy))
        self.assertTrue(privacy.inspect_text('unapproved'+'@'+'example.test',self.policy))
    def test_private_rules_are_separate_from_public_code(self):
        self.assertTrue(privacy.inspect_text('secondary-identity-example',self.policy,{'blocked_terms':['secondary-identity-example']}))
        self.assertFalse(privacy.inspect_text('Ordinary SFX Vault source',self.policy))
    def test_default_deny_ignore_contains_only_exact_exceptions(self):
        rules=privacy.ignore_rules(['.gitignore','source/main.py','publication-files.txt'])
        self.assertIn('/*\n',rules); self.assertIn('/source/*\n',rules); self.assertIn('!/source/main.py\n',rules)
        self.assertNotIn('!/source/*.py',rules)
    def test_duplicate_traversal_and_symlink_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'valid.py').write_text('test')
            for value in ('valid.py\nvalid.py\n','../outside.py\n','/outside.py\n','missing.py\n'):
                (root/privacy.MANIFEST).write_text(value)
                with self.assertRaises(ValueError): privacy.manifest(root)
            (root/'private.env').write_text('example')
            (root/privacy.MANIFEST).write_text('private.env\n')
            with self.assertRaises(ValueError): privacy.manifest(root)
    def test_unexpected_binary_or_image_metadata_requires_review(self):
        self.assertTrue(privacy.inspect_bytes(bytes([255,254]),'file.py',self.policy))
        import struct
        png=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',3)+b'tEXt'+b'abc'+b'\0'*4
        self.assertTrue(privacy.png_metadata(png))
    def test_actual_index_and_effective_identity_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args): return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
            git('init','--initial-branch=main')
            identity={'name':'ReleaseIdentity','email':'release'+'@'+'users.noreply.github.com'}
            for key,value in [('user.name',identity['name']),('user.email',identity['email']),('user.useConfigOnly','true'),('commit.gpgsign','false'),('core.hooksPath','.githooks'),('core.autocrlf','false')]:git('config','--local',key,value)
            entries=['.gitignore','publication-files.txt','publication-policy.json','main.py']
            (root/'publication-files.txt').write_text('\n'.join(entries)+'\n')
            (root/'publication-policy.json').write_text(json.dumps({'identity':identity,'repository':'example/project'}))
            private={'blocked_terms':['secondary-identity-example'],'binary_blocked_terms':['secondary-identity-example']}
            (root/'.privacy-local.json').write_text(json.dumps(private))
            (root/'.gitignore').write_text(privacy.ignore_rules(entries)); (root/'main.py').write_text('print("example")\n')
            git('add','--pathspec-from-file=publication-files.txt')
            with patch.object(privacy,'ROOT',root):
                self.assertTrue(privacy.audit_source(True,True)['passed'])
                (root/'.privacy-local.json').unlink()
                self.assertFalse(privacy.audit_source(True,True)['passed'])
                (root/'.privacy-local.json').write_text(json.dumps(private))
                (root/'unexpected.env').write_text('example')
                git('add','--force','unexpected.env')
                self.assertFalse(privacy.audit_source(True,True)['passed'])
                git('rm','--cached','unexpected.env')
                with patch.dict(os.environ,{'GIT_AUTHOR_EMAIL':'other'+'@'+'example.test'}):
                    self.assertFalse(privacy.audit_source(True,True)['passed'])
                (root/'main.py').write_text('changed after staging')
                self.assertFalse(privacy.audit_source(True,True)['passed'])
