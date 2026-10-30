"""Offline import polling and transactional review. Never writes audio files."""
import os
import time
from pathlib import Path
from .core import EXTENSIONS, RULES, inspect_audio, suggested_name, classify, in_import_scope

DEFAULT_OPTIONS = dict(enabled=True, interval=3, stable_seconds=5, duplicates=True, scan_startup=True)
TEMP_SUFFIXES = ('.part', '.partial', '.crdownload', '.download', '.tmp')

def options(catalog):
    return DEFAULT_OPTIONS | catalog.setting('import_options', {})

def pending_summary(catalog, detect_duplicates=True):
    rows = catalog.db.execute("SELECT id,confidence,sha FROM sounds WHERE status='pending'").fetchall()
    hashes = {r[0]: r[1] for r in catalog.db.execute("SELECT sha,count(*) FROM sounds WHERE sha!='' AND status!='rejected' GROUP BY sha HAVING count(*)>1")} if detect_duplicates else {}
    return dict(total=len(rows), high=sum(r['confidence'] >= .75 for r in rows),
                medium=sum(.5 <= r['confidence'] < .75 for r in rows),
                low=sum(r['confidence'] < .5 for r in rows),
                duplicates=sum(r['sha'] in hashes for r in rows))

def enqueue(catalog, data):
    """Recheck state under a write lock; preserve existing managed/manual metadata."""
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        old = catalog.db.execute('SELECT * FROM sounds WHERE path=?', (data['path'],)).fetchone()
        if old and (old['status'] == 'managed' or (old['size'], old['mtime']) == (data['size'], data['mtime']) or
                    old['sha'] and data['sha'] and old['sha'] == data['sha']):
            catalog.db.execute('''UPDATE sounds SET original=:original,format=:format,size=:size,mtime=:mtime,
                duration=:duration,metadata=:metadata,sha=:sha,missing=0,revision=revision+1 WHERE path=:path''', data)
            return False
        name = suggested_name(data['original'])
        category, tags, confidence = classify(data['path'], data['metadata'], catalog.setting('rules', RULES))
        detected = time.time()
        if old:
            generation = old['generation'] + 1
            catalog.db.execute("UPDATE import_history SET status='superseded',decided=? WHERE sound_id=? AND status='pending'", (detected, old['id']))
            if old['edited']:
                name, category, tags, confidence = old['display'], old['category'], old['tags'], old['confidence']
            values = data | dict(display=name, suggestion=suggested_name(data['original']), category=category,
                tags=tags, confidence=confidence, detected=detected, generation=generation)
            catalog.db.execute('''UPDATE sounds SET original=:original,format=:format,size=:size,mtime=:mtime,
                duration=:duration,metadata=:metadata,sha=:sha,display=:display,suggestion=:suggestion,
                category=:category,tags=:tags,confidence=:confidence,status='pending',detected=:detected,
                decision_at=NULL,generation=:generation,missing=0,revision=revision+1 WHERE path=:path''', values)
            ident = old['id']
        else:
            generation = 1
            values = data | dict(display=name, suggestion=name, category=category, tags=tags,
                confidence=confidence, status='pending', added=detected, detected=detected, generation=generation)
            cursor = catalog.db.execute(f'INSERT INTO sounds ({",".join(values)}) VALUES ({",".join(":"+k for k in values)})', values)
            ident = cursor.lastrowid
        catalog.db.execute('''INSERT INTO import_history(sound_id,generation,path,original,detected,category,status,sha)
            VALUES (?,?,?,?,?,?,?,?)''', (ident, generation, data['path'], data['original'], detected, category, 'pending', data['sha']))
        return True

def review_imports(catalog, snapshots, approve, duplicate_policy='skip'):
    """Explicit decision, atomic batch, revision-safe. Duplicate default is skip."""
    if duplicate_policy not in ('skip', 'keep'): raise ValueError('Choose skip or keep for exact duplicates')
    result = dict(approved=0, rejected=0, skipped=0, stale=0)
    detect = options(catalog)['duplicates']
    valid = set()
    if approve:
        # Run this operation in a worker: disconnected drives must not block the UI.
        for snapshot in snapshots:
            try:
                stat = Path(snapshot['path']).stat()
                if (stat.st_size, stat.st_mtime_ns) == (snapshot['size'], snapshot['mtime']) and not any(Path(snapshot['path'] + suffix).exists() for suffix in TEMP_SUFFIXES):
                    with open(snapshot['path'], 'rb') as stream: stream.read(1)
                    valid.add(snapshot['id'])
            except OSError: pass
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        for snapshot in snapshots:
            row = catalog.db.execute('SELECT * FROM sounds WHERE id=?', (snapshot['id'],)).fetchone()
            if not row or row['status'] != 'pending' or row['revision'] != snapshot['revision'] or approve and row['id'] not in valid:
                result['stale'] += 1; continue
            if approve and detect and not row['sha']:
                result['stale'] += 1; continue  # Wait for enabled duplicate checks to finish.
            duplicate = detect and catalog.duplicates(row)
            if approve and duplicate and duplicate_policy == 'skip':
                result['skipped'] += 1; continue
            now = time.time(); status = 'managed' if approve else 'rejected'
            catalog.db.execute('UPDATE sounds SET status=?,decision_at=?,revision=revision+1 WHERE id=?', (status, now, row['id']))
            catalog.db.execute('''INSERT INTO import_history(sound_id,generation,path,original,detected,decided,category,status,sha)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(sound_id,generation) DO UPDATE SET
                decided=excluded.decided,category=excluded.category,status=excluded.status,sha=excluded.sha''',
                (row['id'], row['generation'], row['path'], row['original'], row['detected'] or row['added'], now, row['category'], 'approved' if approve else 'rejected', row['sha']))
            result['approved' if approve else 'rejected'] += 1
    return result

def reconsider(catalog, ids=None):
    """An explicit request restores rejected records without changing audio."""
    count = 0
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        rows = catalog.db.execute("SELECT * FROM sounds WHERE status='rejected'").fetchall()
        selected = set(ids) if ids is not None else None
        for row in rows:
            if selected is not None and row['id'] not in selected: continue
            now = time.time(); generation = row['generation'] + 1
            catalog.db.execute("UPDATE sounds SET status='pending',detected=?,decision_at=NULL,generation=?,revision=revision+1 WHERE id=?", (now, generation, row['id']))
            catalog.db.execute('''INSERT INTO import_history(sound_id,generation,path,original,detected,category,status,sha)
                VALUES (?,?,?,?,?,?,?,?)''', (row['id'], generation, row['path'], row['original'], now, row['category'], 'pending', row['sha']))
            count += 1
    return count

class ImportMonitor:
    """Polling works on local and LAN paths; state is owned by one background worker."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.observed = {}
        self.initialized = set()
        self.ignored = {}
        self.failures = {}

    def poll(self, catalog, progress=lambda message: None, cancelled=lambda: False, folders_override=None, exclude_scopes=()):
        settings = options(catalog)
        if folders_override is not None: settings = settings | dict(enabled=True, scan_startup=True)
        result = dict(new=0, checked=0, waiting=0, errors=[], folders=[])
        if not settings['enabled']: return result
        folders = [f for f in (folders_override if folders_override is not None else catalog.setting('import_folders', [])) if f.get('enabled', True)]
        candidates, traversed = {}, set()
        for entry in folders:
            if cancelled(): return result
            root = Path(entry['path']); key = (str(root.resolve()).casefold(), bool(entry.get('recursive', True)))
            progress('Checking import folder: ' + str(root))
            if not root.is_dir():
                result['errors'].append('Import folder unavailable (records retained): ' + str(root))
                result['folders'].append((str(root), 'Unavailable')); continue
            root_paths = []
            complete = True
            def onerror(error):
                nonlocal complete
                complete = False; result['errors'].append(str(error))
            for folder, subdirs, filenames in os.walk(root, onerror=onerror, followlinks=False):
                if cancelled(): return result
                if not entry.get('recursive', True): subdirs[:] = []
                for name in filenames:
                    path = Path(folder) / name
                    if path.suffix.lower() not in EXTENSIONS: continue
                    if in_import_scope(path, exclude_scopes): continue
                    path = path.resolve(); normalized = str(path).casefold()
                    root_paths.append(normalized); candidates[normalized] = path
            if key not in self.initialized and not settings['scan_startup']:
                for normalized in root_paths:
                    try:
                        stat = candidates[normalized].stat()
                        self.ignored[normalized] = (stat.st_size, stat.st_mtime_ns)
                    except OSError: pass
            if complete:
                self.initialized.add(key)
            result['folders'].append((str(root), 'Watching' if complete else 'Read errors'))
            traversed.update(root_paths)
        # A disappearance resets the stability window; it does not remove catalog records.
        for key in set(self.observed) - traversed:
            self.observed.pop(key, None); self.failures.pop(key, None); self.ignored.pop(key, None)
        for index, (key, path) in enumerate(candidates.items(), 1):
            if cancelled(): break
            progress(f'Checking import audio {index}/{len(candidates)} · {path.name}')
            try:
                stat = path.stat(); signature = (stat.st_size, stat.st_mtime_ns)
                if folders_override is None and self.ignored.get(key) == signature: continue
                self.ignored.pop(key, None)
                row = catalog.db.execute('SELECT * FROM sounds WHERE path=?', (str(path),)).fetchone()
                if row and (row['size'], row['mtime']) == signature and (not settings['duplicates'] or row['sha']):
                    if row['missing']:
                        with catalog.db: catalog.db.execute('UPDATE sounds SET missing=0 WHERE id=?', (row['id'],))
                    continue
                now = self.clock(); previous = self.observed.get(key)
                if not previous or previous[0] != signature:
                    self.observed[key] = (signature, now); self.failures.pop(key, None); result['waiting'] += 1; continue
                if now - previous[1] < settings['stable_seconds']: result['waiting'] += 1; continue
                if any(Path(str(path) + suffix).exists() for suffix in TEMP_SUFFIXES): continue
                failed = self.failures.get(key)
                if failed and now - failed < 30: continue
                data = inspect_audio(path, hash_file=settings['duplicates'], require_valid=True)
                result['checked'] += 1
                result['new'] += int(enqueue(catalog, data))
                self.failures.pop(key, None)
            except Exception as exc:
                self.failures[key] = self.clock()
                result['errors'].append(f'{path}: {exc}')
        return result
