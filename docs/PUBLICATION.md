# Publication privacy boundary

Only exact paths in publication-files.txt are proposed for source publication.
The default-deny .gitignore is generated from this manifest, not broad source globs.
Adding a path requires reviewing its contents and updating the manifest deliberately.
No local profiles, catalogs, source audio, logs, screenshots, planning notes, secrets,
shortcuts or build output belong in the source commit.

Configure repository-local user, author and committer names/emails using the public
identity in publication-policy.json. Set user.useConfigOnly=true and disable automatic
commit signing locally to avoid inheriting another project's signing identity.
Do not change global Git settings. GIT_AUTHOR_* and GIT_COMMITTER_* environment
overrides still take precedence; the audit checks effective identities, not just config.

Install core.hooksPath=.githooks. The pre-commit hook audits the actual index and
requires that its complete file tree exactly equals the manifest. Unreviewed staged
files, changed worktree bytes, unexpected Git entry types, unknown email addresses,
home-directory paths, credential patterns and image metadata block the check.
The pre-push hook intentionally blocks every push pending explicit human approval.
Hooks can be bypassed and are safeguards, not an access-control boundary.

```powershell
python tools/privacy_check.py --write-ignore
python tools/privacy_check.py --staged --identity --report .privacy/proposed-source.json
python tools/privacy_check.py --artifacts release/stable/0.7.0 --report .privacy/release.json
```

Private identity/cross-project deny rules belong only in .privacy-local.json, which
is excluded by default. Never publish that file or the .privacy reports: they can
themselves contain the identity relationships being protected. CI cannot know
private local identifiers unless they are supplied securely; generic CI checks do
not replace the local private-rule audit and human review.
The local identity audit refuses to pass if those private rules are missing.

The artifact check reads executable metadata and scans the unpacked distribution,
embedded Python code objects/filenames, bundled standard-library bytecode, image
metadata and release checksums. It does not independently extract the compressed
Inno payload. Review the matching unpacked build and release hashes together.
Generic third-party build paths and parser strings remain visible as reviewed
findings. publication-vendor-review.json binds each classification to exact file
or code-string hashes. Changed dependencies or new findings require fresh review;
there are no blanket vendor-directory exceptions. Known local identities and real
private-key bodies remain blockers. The vendor provenance record is local wheel
RECORD/installed-runtime evidence, not a publisher-signature guarantee.
Unsigned binaries have no publisher certificate identity; future code-signing
certificates may expose a legal identity and require a separate review.

Release automation builds and audits artifacts but does not upload or create a
release automatically. Source upload, artifacts and draft/public releases all remain
subject to explicit review. GitHub-side UI/API operations bypass local hooks; apply
the same allowlist and reviewed byte hashes to those routes.
