from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import time
import wave
from pathlib import Path

EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.opus', '.m4a', '.aif', '.aiff', '.wma', '.aac'}
CATEGORIES = ['Ambience', 'Movement', 'Doors', 'Vehicles', 'Combat', 'Human Sounds', 'Objects', 'Clothing & Fabric', 'Electronics', 'Fantasy', 'Music & Transitions', 'Uncategorized']
RULES = [
    {'category': 'Ambience / Rain', 'keywords': ['rain', 'storm', 'thunder'], 'tags': ['weather']},
    {'category': 'Ambience', 'keywords': ['bg', 'ambience', 'wind', 'forest', 'birds'], 'tags': []},
    {'category': 'Movement / Footsteps', 'keywords': ['footsteps', 'walking', 'barefoot', 'running', 'footstep'], 'tags': ['movement']},
    {'category': 'Doors', 'keywords': ['door', 'doors', 'knock', 'knocking'], 'tags': ['impact']},
    {'category': 'Vehicles', 'keywords': ['car', 'engine', 'truck'], 'tags': []},
    {'category': 'Combat', 'keywords': ['combat', 'gun', 'shot', 'sword', 'gunshot', 'explosion'], 'tags': []},
    {'category': 'Human Sounds', 'keywords': ['people', 'breath', 'whisper', 'laugh'], 'tags': []},
    {'category': 'Clothing & Fabric', 'keywords': ['fabric', 'cloth', 'clothing'], 'tags': []},
    {'category': 'Electronics', 'keywords': ['beep', 'computer', 'electronic'], 'tags': []},
    {'category': 'Fantasy', 'keywords': ['magic', 'ghost', 'spell'], 'tags': []},
    {'category': 'Objects', 'keywords': ['object', 'glass', 'bottle', 'paper', 'keyboard', 'keys', 'drawer'], 'tags': []},
    {'category': 'Music & Transitions', 'keywords': ['music', 'transition', 'sting'], 'tags': []},
]

def suggested_name(path):
    name = re.sub(r'[-_]+', ' ', Path(path).stem)
    name = re.sub(r'\b\d{5,}\b', '', name)
    name = re.sub(r'^\s*\d{1,4}\s+(?=[A-Za-z])', '', name)
    name = re.sub(r'\s+\(?\d{1,3}\)?\s*$', '', name)
    name = re.sub(r'\b(?:freesound|pixabay|download)\b', '', name, flags=re.I)
    name = ' '.join(name.split()).title() or Path(path).stem
    name = re.sub(r'\b(Barefoot Walking|Footsteps|Walking|Running) (Hardwood|Wooden|Concrete|Gravel|Metal|Grass|Snow)\b', r'\1 – \2', name)
    return name

def classify(path, metadata, rules):
    words = set(re.findall(r'[^\W_]+', str(path).lower() + ' ' + metadata.lower()))
    ranked = []
    for rule in rules:
        hits = words.intersection(k.lower() for k in rule['keywords'])
        if hits:
            ranked.append((len(hits), rule, hits))
    if not ranked:
        return 'Uncategorized', '', 0.0
    count, rule, hits = max(ranked, key=lambda r: r[0])
    tied = {r['category'].split(' / ')[0] for n, r, _ in ranked if n == count}
    if len(tied) > 1:
        return 'Uncategorized', ', '.join(sorted(set().union(*(h for _, _, h in ranked)))), .2
    tags = sorted(hits | set(rule.get('tags', [])) | (words & {'wood', 'wooden', 'window', 'hardwood', 'metal'}))
    return rule['category'], ', '.join(tags), min(.85, .4 + count * .15)

def inspect_audio(path, hash_file=True, require_valid=False):
    p = Path(path)
    before = p.stat()
    digest = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            if hash_file: digest.update(block)
    duration, metadata = 0.0, ''
    try:
        from mutagen import File
        audio = File(p, easy=True)
        if audio is not None:
            duration = float(audio.info.length)
            metadata = json.dumps(dict(audio.tags or {}), ensure_ascii=False)
    except Exception:
        pass
    if not duration and p.suffix.lower() == '.wav':
        with wave.open(str(p), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
    if require_valid and duration <= 0:
        raise OSError('Audio is empty, incomplete, or has no readable duration; it will be retried.')
    if require_valid and p.suffix.lower() == '.wav':
        with p.open('rb') as stream: header = stream.read(12)
        if header[:4] == b'RIFF' and int.from_bytes(header[4:8], 'little') + 8 > before.st_size:
            raise OSError('WAV transfer is incomplete: RIFF length exceeds the readable file size.')
    after = p.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise OSError('File changed while being read; retry after transfer finishes.')
    return dict(path=str(p.resolve()), original=p.name, format=p.suffix[1:].upper(), size=after.st_size, mtime=after.st_mtime_ns, duration=duration, metadata=metadata, sha=digest.hexdigest() if hash_file else '')

class Catalog:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.create_function('has_tag', 2, lambda value, tag: int(tag.casefold() in {t.strip().casefold() for t in (value or '').split(',')}), deterministic=True)
        if self.db.execute('PRAGMA user_version').fetchone()[0] > 4:
            self.db.close()
            raise RuntimeError('This catalog was created by a newer SFX Vault. Use that version to open it.')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sounds (
          id INTEGER PRIMARY KEY, path TEXT UNIQUE COLLATE NOCASE, original TEXT,
          format TEXT, size INTEGER, mtime INTEGER, duration REAL, metadata TEXT,
          sha TEXT, display TEXT, suggestion TEXT, category TEXT, tags TEXT,
          confidence REAL, status TEXT, favorite INTEGER DEFAULT 0,
          missing INTEGER DEFAULT 0, added REAL, edited INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS sounds_sha ON sounds(sha);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        ''')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version < 2:
            # A SQLite backup includes committed WAL data and precedes schema changes.
            if self.db.execute('SELECT count(*) FROM sounds').fetchone()[0] and str(path) != ':memory:':
                backup_path = Path(str(path) + '.v01-backup.sqlite3')
                if not backup_path.exists():
                    backup = sqlite3.connect(str(backup_path))
                    try: self.db.backup(backup)
                    finally: backup.close()
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                columns = {r[1] for r in self.db.execute('PRAGMA table_info(sounds)')}
                if 'revision' not in columns:
                    self.db.execute('ALTER TABLE sounds ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
                self.db.execute('''CREATE TABLE IF NOT EXISTS organization (
                    sound_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending')''')
                self.db.execute('PRAGMA user_version=2')
        if version < 3:
            if version == 2 and self.db.execute('SELECT count(*) FROM sounds').fetchone()[0] and str(path) != ':memory:':
                backup_path = Path(str(path) + '.v02-backup.sqlite3')
                if not backup_path.exists():
                    backup = sqlite3.connect(str(backup_path))
                    try: self.db.backup(backup)
                    finally: backup.close()
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                columns = {r[1] for r in self.db.execute('PRAGMA table_info(sounds)')}
                for name, declaration in [('detected', 'REAL'), ('decision_at', 'REAL'), ('generation', 'INTEGER NOT NULL DEFAULT 0')]:
                    if name not in columns: self.db.execute(f'ALTER TABLE sounds ADD COLUMN {name} {declaration}')
                self.db.execute('''CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY, sound_id INTEGER NOT NULL, generation INTEGER NOT NULL,
                    path TEXT NOT NULL, original TEXT NOT NULL, detected REAL NOT NULL,
                    decided REAL, category TEXT NOT NULL, status TEXT NOT NULL, sha TEXT,
                    UNIQUE(sound_id,generation))''')
                self.db.execute('CREATE INDEX IF NOT EXISTS sounds_status ON sounds(status)')
                self.db.execute("UPDATE sounds SET detected=added WHERE status IN ('pending','rejected') AND detected IS NULL")
                self.db.execute("""INSERT OR IGNORE INTO import_history(sound_id,generation,path,original,detected,category,status,sha)
                    SELECT id,generation,path,original,coalesce(detected,added),category,status,sha
                    FROM sounds WHERE status IN ('pending','rejected')""")
                if not self.db.execute("SELECT 1 FROM settings WHERE key='import_folders'").fetchone():
                    folders = [dict(path=p, enabled=False, recursive=True) for p in self.setting('watched', [])]
                    self.db.execute('INSERT INTO settings VALUES (?,?)', ('import_folders', json.dumps(folders)))
                self.db.execute('PRAGMA user_version=3')
        if version < 4:
            if version == 3 and self.db.execute('SELECT count(*) FROM sounds').fetchone()[0] and str(path) != ':memory:':
                backup_path = Path(str(path) + '.v03-backup.sqlite3')
                if not backup_path.exists():
                    backup = sqlite3.connect(str(backup_path))
                    try: self.db.backup(backup)
                    finally: backup.close()
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('''CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE)''')
                self.db.execute('''CREATE TABLE IF NOT EXISTS collection_members (
                    collection_id INTEGER NOT NULL, sound_id INTEGER NOT NULL,
                    PRIMARY KEY(collection_id,sound_id))''')
                self.db.execute('CREATE INDEX IF NOT EXISTS collection_sound ON collection_members(sound_id)')
                self.db.execute('''CREATE TABLE IF NOT EXISTS sound_usage (
                    sound_id INTEGER PRIMARY KEY, last_used REAL NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0, last_action TEXT NOT NULL)''')
                self.db.execute('PRAGMA user_version=4')
    def close(self):
        self.db.close()
    def setting(self, key, default):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default
    def configure(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
    def register(self, data, status):
        old = self.db.execute('SELECT * FROM sounds WHERE path=?', (data['path'],)).fetchone()
        if old:
            with self.db:
                self.db.execute('UPDATE sounds SET original=:original,format=:format,size=:size,mtime=:mtime,duration=:duration,metadata=:metadata,sha=:sha,missing=0,revision=revision+1 WHERE path=:path', data)
            return
        name = suggested_name(data['path'])
        cat, tags, confidence = classify(data['path'], data['metadata'], self.setting('rules', RULES))
        values = dict(data, display=name, suggestion=name, category=cat, tags=tags, confidence=confidence, status=status, added=time.time())
        keys = ','.join(values)
        with self.db:
            self.db.execute(f'INSERT INTO sounds ({keys}) VALUES ({",".join(":"+k for k in values)})', values)
    def rows(self, search='', view='All Sounds', category='', filetype='', confidence='', filters=None):
        filters = filters or {}
        clauses, args = ['status=?'], ['pending' if view == 'Pending Review' else 'managed']
        if view == 'Favorites': clauses.append('favorite=1')
        if view == 'Uncategorized': clauses.append("category='Uncategorized'")
        if category:
            clauses.append('(category=? OR category LIKE ?)'); args += [category, category + ' /%']
        if filetype:
            clauses.append('format=?'); args.append(filetype)
        if confidence == 'Low (<50%)': clauses.append('confidence < .5')
        if confidence == 'Medium (50–74%)': clauses.append('confidence >= .5 AND confidence < .75')
        if confidence == 'High (75%+)': clauses.append('confidence >= .75')
        if view in ('Recently Used', 'Frequently Used'): clauses.append('u.use_count>0')
        if filters.get('category'):
            clauses.append('(category=? OR category LIKE ?)'); args += [filters['category'], filters['category'] + ' /%']
        if filters.get('subcategory'):
            clauses.append('(category LIKE ? OR category LIKE ?)'); args += ['% / ' + filters['subcategory'], '% / ' + filters['subcategory'] + ' /%']
        for tag in filters.get('tags', '').split(','):
            if tag.strip(): clauses.append('has_tag(tags,?)=1'); args.append(tag.strip())
        if filters.get('min_duration') is not None: clauses.append('duration>=?'); args.append(filters['min_duration'])
        if filters.get('max_duration') is not None: clauses.append('duration<=?'); args.append(filters['max_duration'])
        if filters.get('favorite') is not None: clauses.append('favorite=?'); args.append(int(filters['favorite']))
        if filters.get('collection') is not None:
            clauses.append('EXISTS (SELECT 1 FROM collection_members m WHERE m.sound_id=sounds.id AND m.collection_id=?)'); args.append(filters['collection'])
        for collection_id in filters.get('collections', []):
            clauses.append('EXISTS (SELECT 1 FROM collection_members m WHERE m.sound_id=sounds.id AND m.collection_id=?)'); args.append(collection_id)
        if filters.get('used'): clauses.append('u.use_count>0')
        if filters.get('availability') in ('available', 'missing'):
            clauses.append('missing=?'); args.append(int(filters['availability'] == 'missing'))
        for word in search.split():
            clauses.append("lower(display || ' ' || original || ' ' || category || ' ' || tags || ' ' || metadata) LIKE ?")
            args.append('%' + word.lower() + '%')
        order = 'u.use_count DESC,u.last_used DESC' if view == 'Frequently Used' or filters.get('sort') == 'Frequent first' else 'u.last_used DESC' if view == 'Recently Used' or filters.get('sort') == 'Recent use first' else 'coalesce(decision_at,added) DESC'
        return self.db.execute('SELECT sounds.*,coalesce(u.use_count,0) AS use_count,u.last_used,u.last_action FROM sounds LEFT JOIN sound_usage u ON u.sound_id=sounds.id WHERE ' + ' AND '.join(clauses) + ' ORDER BY ' + order, args).fetchall()
    def update(self, ident, **values):
        allowed = {'display', 'category', 'tags', 'favorite', 'status', 'edited'}
        if not values or not set(values) <= allowed: raise ValueError('Invalid update')
        with self.db:
            if set(values) & {'display', 'category', 'tags'}: values['edited'] = 1
            self.db.execute('UPDATE sounds SET '+','.join(k+'=?' for k in values)+',revision=revision+1 WHERE id=?', [*values.values(), ident])
    def duplicates(self, row):
        if not row['sha']: return []
        return self.db.execute("SELECT id,path,original,status FROM sounds WHERE sha=? AND id!=? AND status!='rejected'", (row['sha'], row['id'])).fetchall()

def in_import_scope(path, folders):
    path = Path(path).resolve()
    for entry in folders:
        root = Path(entry['path']).resolve()
        if path.parent == root or entry.get('recursive', True) and path.is_relative_to(root): return True
    return False

def scan(catalog, roots, pending=False, stable=None, exclude=(), guarded=None, only_existing=False):
    errors = []
    guarded = catalog.setting('import_folders', []) if guarded is None else guarded
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            errors.append(f'Unavailable folder (records retained): {root}')
            continue
        seen, complete = set(), True
        def walk_error(error):
            nonlocal complete
            complete = False
            errors.append(str(error))
        import os
        for folder, _, filenames in os.walk(base, onerror=walk_error):
            for filename in filenames:
                p = Path(folder) / filename
                if p.suffix.lower() not in EXTENSIONS: continue
                if not pending and any(p.resolve().is_relative_to(Path(folder_root).resolve()) for folder_root in exclude): continue
                path = str(p.resolve()); seen.add(path.casefold())
                try:
                    if only_existing:
                        existing = catalog.db.execute('SELECT status FROM sounds WHERE path=?', (path,)).fetchone()
                        if not existing or existing['status'] != 'managed': continue
                    if not pending and in_import_scope(p, guarded):
                        existing = catalog.db.execute('SELECT status FROM sounds WHERE path=?', (path,)).fetchone()
                        if not existing or existing['status'] != 'managed': continue
                    stat = p.stat()
                    if pending:
                        signature = (stat.st_size, stat.st_mtime_ns)
                        previous = stable.get(path) if stable is not None else None
                        if stable is not None: stable[path] = (signature, previous[1] if previous and previous[0] == signature else time.monotonic())
                        if previous is None or previous[0] != signature or time.monotonic() - previous[1] < 5: continue
                    old = catalog.db.execute('SELECT mtime,size,missing FROM sounds WHERE path=?', (path,)).fetchone()
                    if old and old['mtime'] == stat.st_mtime_ns and old['size'] == stat.st_size and not old['missing']: continue
                    catalog.register(inspect_audio(p), 'pending' if pending else 'managed')
                except Exception as exc:
                    complete = False
                    errors.append(f'{p}: {exc}')
        if complete and not pending and base.is_dir():
            with catalog.db:
                for row in catalog.db.execute('SELECT id,path FROM sounds').fetchall():
                    try: Path(row['path']).relative_to(base.resolve())
                    except ValueError: continue
                    if row['path'].casefold() not in seen:
                        catalog.db.execute('UPDATE sounds SET missing=1 WHERE id=?', (row['id'],))
    return errors
