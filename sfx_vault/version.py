"""One version source, optionally supplied by a reproducible release build."""
import json
from pathlib import Path
VERSION='0.7.0'
DEFAULT_REPOSITORY='TobiTired/SFX-Vault'
TEST_EDITION=False
try:
    _build=json.loads(Path(__file__).with_name('build-info.json').read_text('utf-8'))
    VERSION=_build['version']; DEFAULT_REPOSITORY=_build.get('repository',''); TEST_EDITION=bool(_build.get('test',False))
except FileNotFoundError:
    pass
