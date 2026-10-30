"""Metadata-only organization. Preview reads the catalog without opening audio."""
import hashlib
import json
import sqlite3
from pathlib import Path
from .core import Catalog, RULES, suggested_name, classify

ENGINE_VERSION = 2
CONFIDENCES = ['All confidence', 'Low (<50%)', 'Medium (50–74%)', 'High (75%+)']

def confidence_matches(value, label):
    return (label == CONFIDENCES[0] or label == CONFIDENCES[1] and value < .5
            or label == CONFIDENCES[2] and .5 <= value < .75
            or label == CONFIDENCES[3] and value >= .75)

def tags(text):
    return list(dict.fromkeys(t.strip().lower() for t in text.split(',') if t.strip()))

def propose(row, rules):
    category, suggested_tags, confidence = classify(row['path'], row['metadata'], rules)
    proposed = dict(display=suggested_name(row['original']), category=category,
                    tags=suggested_tags, confidence=confidence)
    current = {key: row[key] for key in proposed}
    fingerprint = hashlib.sha256(json.dumps([ENGINE_VERSION, row['path'], row['original'],
        row['metadata'], rules], sort_keys=True).encode()).hexdigest()
    return dict(id=row['id'], original=row['original'], path=row['path'], revision=row['revision'],
                protected=bool(row['edited']), current=current, proposed=proposed,
                fingerprint=fingerprint, custom=False)

def preview(database):
    """A true read-only preview: no migrations, settings writes, or persisted proposals."""
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN')
        row = connection.execute("SELECT value FROM settings WHERE key='rules'").fetchone()
        rules = json.loads(row[0]) if row else RULES
        rows = connection.execute("SELECT * FROM sounds WHERE status='managed' ORDER BY id").fetchall()
        return [propose(dict(row), rules) for row in rows]
    finally: connection.close()

def stage(catalog, proposals):
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        for p in proposals:
            existing = catalog.db.execute('SELECT fingerprint,payload FROM organization WHERE sound_id=?', (p['id'],)).fetchone()
            if existing and existing['fingerprint'] == p['fingerprint']:
                # Keep review decisions and edited proposals until inputs/rules change.
                saved = json.loads(existing['payload'])
                if saved['revision'] != p['revision']:
                    state = catalog.db.execute('SELECT state FROM organization WHERE sound_id=?', (p['id'],)).fetchone()[0]
                    if state == 'pending':
                        if saved.get('custom'):
                            p['proposed'] = saved['proposed']; p['custom'] = True
                        catalog.db.execute('UPDATE organization SET payload=? WHERE sound_id=?', (json.dumps(p), p['id']))
                continue
            catalog.db.execute('INSERT OR REPLACE INTO organization VALUES (?,?,?,?)',
                (p['id'], p['fingerprint'], json.dumps(p), 'pending'))

def staged(catalog):
    return [json.loads(r[0]) for r in catalog.db.execute("SELECT payload FROM organization WHERE state='pending' ORDER BY sound_id")]

def decide(catalog, proposals, approve):
    applied, skipped = 0, 0
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        rules = catalog.setting('rules', RULES)
        for p in proposals:
            entry = catalog.db.execute("SELECT * FROM organization WHERE sound_id=? AND state='pending'", (p['id'],)).fetchone()
            if not entry or entry['fingerprint'] != p['fingerprint']:
                skipped += 1; continue
            if not approve:
                catalog.db.execute("UPDATE organization SET state='rejected' WHERE sound_id=?", (p['id'],))
                applied += 1; continue
            r = catalog.db.execute('SELECT * FROM sounds WHERE id=?', (p['id'],)).fetchone()
            if not r or r['status'] != 'managed' or r['edited'] or r['revision'] != p['revision'] or propose(r, rules)['fingerprint'] != p['fingerprint']:
                skipped += 1; continue
            values = p['proposed']
            catalog.db.execute('''UPDATE sounds SET display=?,suggestion=?,category=?,tags=?,confidence=?,
                edited=?,revision=revision+1 WHERE id=?''', (values['display'], values['display'],
                values['category'], values['tags'], values['confidence'], int(p['custom']), p['id']))
            catalog.db.execute("UPDATE organization SET state='approved',payload=? WHERE sound_id=?", (json.dumps(p), p['id']))
            applied += 1
    return applied, skipped

def bulk(catalog, ids, operation, value=''):
    """One transaction. Reset removes only generated fields; manual rows are protected."""
    if operation not in {'Category', 'Subcategory', 'Add tags', 'Remove tags', 'Favorite', 'Unfavorite', 'Reset automatic metadata'}:
        raise ValueError('Unknown bulk operation')
    count, skipped = 0, 0
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        for ident in set(ids):
            row = catalog.db.execute("SELECT * FROM sounds WHERE id=? AND status='managed'", (ident,)).fetchone()
            if not row: skipped += 1; continue
            if operation == 'Reset automatic metadata':
                if row['edited']: skipped += 1; continue
                catalog.db.execute("UPDATE sounds SET display=original,suggestion=original,category='Uncategorized',tags='',confidence=0,revision=revision+1 WHERE id=?", (ident,))
                catalog.db.execute('DELETE FROM organization WHERE sound_id=?', (ident,))
            elif operation in {'Favorite', 'Unfavorite'}:
                catalog.db.execute('UPDATE sounds SET favorite=?,revision=revision+1 WHERE id=?', (int(operation == 'Favorite'), ident))
            else:
                category, new_tags = row['category'], row['tags']
                if operation == 'Category': category = value.strip() or 'Uncategorized'
                if operation == 'Subcategory': category = row['category'].split(' / ')[0] + (' / ' + value.strip() if value.strip() else '')
                if operation == 'Add tags': new_tags = ', '.join(tags(new_tags + ',' + value))
                if operation == 'Remove tags': new_tags = ', '.join(t for t in tags(new_tags) if t not in tags(value))
                catalog.db.execute('UPDATE sounds SET category=?,tags=?,edited=1,revision=revision+1 WHERE id=?', (category, new_tags, ident))
            count += 1
    return count, skipped

def rename_category(catalog, old, new):
    old, new = old.strip(), new.strip()
    if not old or not new: raise ValueError('Both category names are required')
    if new.startswith(old + ' / '): raise ValueError('A category cannot be renamed into its own subcategory')
    def renamed(value):
        return new + value[len(old):] if value == old or value.startswith(old + ' / ') else value
    with catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        for row in catalog.db.execute('SELECT id,category FROM sounds').fetchall():
            category = renamed(row['category'])
            if category != row['category']:
                catalog.db.execute('UPDATE sounds SET category=?,edited=1,revision=revision+1 WHERE id=?', (category, row['id']))
        rules = catalog.setting('rules', RULES)
        for rule in rules: rule['category'] = renamed(rule['category'])
        categories = [renamed(c) for c in catalog.setting('categories', [])]
        categories.append(new)
        for key, value in [('rules', rules), ('categories', sorted(set(categories))), ('hidden_categories', sorted(set(catalog.setting('hidden_categories', []) + [old])))]:
            catalog.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
