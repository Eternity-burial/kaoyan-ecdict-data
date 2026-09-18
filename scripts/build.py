# -*- coding: utf-8 -*-
"""
ECDICT Data Submodule Builder
Reads raw/ecdict.csv and raw/lemma.en.txt, builds SQLite db, indexes, and manifest.
"""
import os, sys, csv, json, sqlite3, hashlib, datetime, time
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, 'raw')
DB_DIR = os.path.join(BASE_DIR, 'db')
INDEXES_DIR = os.path.join(BASE_DIR, 'indexes')
MANIFESTS_DIR = os.path.join(BASE_DIR, 'manifests')
UPSTREAM_DIR = os.path.join(BASE_DIR, 'upstream')

def compute_sha256_and_bytes(path):
    sha = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk: break
            sha.update(chunk)
    return sha.hexdigest(), size

def parse_int_or_none(v):
    if v is None: return None
    v = v.strip()
    if not v: return None
    try:
        return int(v)
    except ValueError:
        return None

def main():
    t0 = time.time()
    print("=== Starting ECDICT Data Build ===")
    
    csv_path = os.path.join(RAW_DIR, 'ecdict.csv')
    lemma_path = os.path.join(RAW_DIR, 'lemma.en.txt')
    sqlite_path = os.path.join(DB_DIR, 'ecdict.sqlite')
    lemma_jsonl_path = os.path.join(INDEXES_DIR, 'lemma.jsonl')
    forms_jsonl_path = os.path.join(INDEXES_DIR, 'forms.jsonl')
    build_manifest_path = os.path.join(MANIFESTS_DIR, 'build.json')
    
    assert os.path.exists(csv_path), f"Missing {csv_path}"
    assert os.path.exists(lemma_path), f"Missing {lemma_path}"
    
    print("1. Computing input hashes...")
    csv_sha256, csv_bytes = compute_sha256_and_bytes(csv_path)
    lemma_sha256, lemma_bytes = compute_sha256_and_bytes(lemma_path)
    print(f"  ecdict.csv: {csv_bytes} bytes, sha256={csv_sha256}")
    print(f"  lemma.en.txt: {lemma_bytes} bytes, sha256={lemma_sha256}")
    
    print("2. Initializing SQLite database...")
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)
    
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous = OFF;")
    cur.execute("PRAGMA journal_mode = MEMORY;")
    cur.execute("PRAGMA cache_size = 100000;")
    
    cur.execute("""
    CREATE TABLE entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL,
        word_lower TEXT NOT NULL,
        phonetic TEXT,
        definition TEXT,
        translation TEXT,
        pos TEXT,
        collins INTEGER,
        oxford INTEGER,
        tag TEXT,
        bnc INTEGER,
        frq INTEGER,
        exchange TEXT,
        detail TEXT,
        audio TEXT
    );
    """)
    
    cur.execute("""
    CREATE TABLE lemma_lookup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form TEXT NOT NULL,
        form_lower TEXT NOT NULL,
        lemma TEXT NOT NULL,
        source TEXT NOT NULL
    );
    """)
    
    cur.execute("""
    CREATE TABLE word_forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma TEXT NOT NULL,
        lemma_lower TEXT NOT NULL,
        form_type TEXT NOT NULL,
        form TEXT NOT NULL
    );
    """)
    
    print("3. Parsing raw/lemma.en.txt...")
    form_to_lemmas = defaultdict(lambda: defaultdict(set))
    lemma_to_forms = defaultdict(lambda: defaultdict(set))
    
    with open(lemma_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(';'): continue
            parts = line.split('->')
            if len(parts) != 2: continue
            lemma = parts[0].split('/')[0].strip()
            forms = [x.strip() for x in parts[1].split(',') if x.strip()]
            for form in forms:
                form_to_lemmas[form][lemma].add('lemma.en.txt')
                lemma_to_forms[lemma]['forms'].add(form)
    
    print(f"  Parsed {len(lemma_to_forms)} lemmas and {len(form_to_lemmas)} surface forms from lemma.en.txt")
    
    print("4. Parsing raw/ecdict.csv and populating entries...")
    entries_buffer = []
    total_entries = 0
    
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        header = next(reader)
        # Expected: ['word', 'phonetic', 'definition', 'translation', 'pos', 'collins', 'oxford', 'tag', 'bnc', 'frq', 'exchange', 'detail', 'audio']
        
        for row in reader:
            total_entries += 1
            word = row[0]
            word_lower = word.lower()
            phonetic = row[1] if len(row) > 1 and row[1].strip() else None
            definition = row[2] if len(row) > 2 and row[2].strip() else None
            translation = row[3] if len(row) > 3 and row[3].strip() else None
            pos = row[4] if len(row) > 4 and row[4].strip() else None
            collins = parse_int_or_none(row[5]) if len(row) > 5 else None
            oxford = parse_int_or_none(row[6]) if len(row) > 6 else None
            tag = row[7] if len(row) > 7 and row[7].strip() else None
            bnc = parse_int_or_none(row[8]) if len(row) > 8 else None
            frq = parse_int_or_none(row[9]) if len(row) > 9 else None
            exchange = row[10] if len(row) > 10 and row[10].strip() else None
            detail = row[11] if len(row) > 11 and row[11].strip() else None
            audio = row[12] if len(row) > 12 and row[12].strip() else None
            
            entries_buffer.append((
                word, word_lower, phonetic, definition, translation,
                pos, collins, oxford, tag, bnc, frq, exchange, detail, audio
            ))
            
            if len(entries_buffer) >= 20000:
                cur.executemany("""
                    INSERT INTO entries (
                        word, word_lower, phonetic, definition, translation,
                        pos, collins, oxford, tag, bnc, frq, exchange, detail, audio
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, entries_buffer)
                entries_buffer = []
            
            # Parse exchange
            if exchange:
                parts = exchange.split('/')
                tokens = {}
                for p in parts:
                    if ':' in p:
                        k, v = p.split(':', 1)
                        tokens[k.strip()] = v.strip()
                
                # If this word is an inflected form pointing to lemma: 0:lemma
                if '0' in tokens:
                    target_lemma = tokens['0']
                    rel = tokens.get('1', 'form')
                    form_to_lemmas[word][target_lemma].add('ecdict.exchange')
                    lemma_to_forms[target_lemma][rel].add(word)
                
                # If this word has inflectional forms: p, d, i, 3, s, r, t, f
                for tag_name in ('p', 'd', 'i', '3', 's', 'r', 't', 'f'):
                    if tag_name in tokens:
                        for inflected in tokens[tag_name].split(','):
                            inflected = inflected.strip()
                            if inflected:
                                form_to_lemmas[inflected][word].add('ecdict.exchange')
                                lemma_to_forms[word][tag_name].add(inflected)

    if entries_buffer:
        cur.executemany("""
            INSERT INTO entries (
                word, word_lower, phonetic, definition, translation,
                pos, collins, oxford, tag, bnc, frq, exchange, detail, audio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, entries_buffer)
        entries_buffer = []
    
    print(f"  Inserted {total_entries} dictionary entries into SQLite.")
    
    print("5. Writing indexes/lemma.jsonl and populating lemma_lookup in SQLite...")
    lemma_lookup_buffer = []
    total_lemma_mappings = 0
    
    with open(lemma_jsonl_path, 'w', encoding='utf-8') as f_out:
        for form in sorted(form_to_lemmas.keys()):
            form_lower = form.lower()
            for lemma in sorted(form_to_lemmas[form].keys()):
                sources = sorted(list(form_to_lemmas[form][lemma]))
                source_str = ','.join(sources)
                rec = {
                    'form': form,
                    'lemma': lemma,
                    'sources': sources
                }
                f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                total_lemma_mappings += 1
                
                lemma_lookup_buffer.append((form, form_lower, lemma, source_str))
                if len(lemma_lookup_buffer) >= 20000:
                    cur.executemany("""
                        INSERT INTO lemma_lookup (form, form_lower, lemma, source)
                        VALUES (?, ?, ?, ?)
                    """, lemma_lookup_buffer)
                    lemma_lookup_buffer = []
    
    if lemma_lookup_buffer:
        cur.executemany("""
            INSERT INTO lemma_lookup (form, form_lower, lemma, source)
            VALUES (?, ?, ?, ?)
        """, lemma_lookup_buffer)
        lemma_lookup_buffer = []
    print(f"  Generated {total_lemma_mappings} lemma mappings in indexes/lemma.jsonl.")
    
    print("6. Writing indexes/forms.jsonl and populating word_forms in SQLite...")
    forms_buffer = []
    total_form_entries = 0
    
    with open(forms_jsonl_path, 'w', encoding='utf-8') as f_out:
        for lemma in sorted(lemma_to_forms.keys()):
            lemma_lower = lemma.lower()
            forms_dict = {}
            for ftype in sorted(lemma_to_forms[lemma].keys()):
                forms_list = sorted(list(lemma_to_forms[lemma][ftype]))
                forms_dict[ftype] = forms_list
                for form in forms_list:
                    forms_buffer.append((lemma, lemma_lower, ftype, form))
                    if len(forms_buffer) >= 20000:
                        cur.executemany("""
                            INSERT INTO word_forms (lemma, lemma_lower, form_type, form)
                            VALUES (?, ?, ?, ?)
                        """, forms_buffer)
                        forms_buffer = []
            
            rec = {
                'lemma': lemma,
                'forms': forms_dict
            }
            f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            total_form_entries += 1
    
    if forms_buffer:
        cur.executemany("""
            INSERT INTO word_forms (lemma, lemma_lower, form_type, form)
            VALUES (?, ?, ?, ?)
        """, forms_buffer)
        forms_buffer = []
    print(f"  Generated {total_form_entries} form entries in indexes/forms.jsonl.")
    
    print("7. Creating indexes on SQLite database...")
    cur.execute("CREATE INDEX idx_entries_word ON entries(word);")
    cur.execute("CREATE INDEX idx_entries_word_lower ON entries(word_lower);")
    cur.execute("CREATE INDEX idx_lemma_form ON lemma_lookup(form);")
    cur.execute("CREATE INDEX idx_lemma_form_lower ON lemma_lookup(form_lower);")
    cur.execute("CREATE INDEX idx_lemma_lemma ON lemma_lookup(lemma);")
    cur.execute("CREATE INDEX idx_forms_lemma ON word_forms(lemma);")
    cur.execute("CREATE INDEX idx_forms_lemma_lower ON word_forms(lemma_lower);")
    cur.execute("CREATE INDEX idx_forms_form ON word_forms(form);")
    
    conn.commit()
    conn.close()
    print("  SQLite indices created successfully.")
    
    print("8. Writing manifests/build.json...")
    upstream_commit = "bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b"
    upstream_repo = "https://github.com/skywind3000/ECDICT"
    if os.path.exists(os.path.join(UPSTREAM_DIR, 'metadata.json')):
        try:
            up_meta = json.load(open(os.path.join(UPSTREAM_DIR, 'metadata.json'), encoding='utf-8'))
            upstream_commit = up_meta.get('upstreamCommit', upstream_commit)
            upstream_repo = up_meta.get('upstreamRepository', upstream_repo)
        except Exception:
            pass
    
    now_str = datetime.datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')
    manifest_data = {
        "source": "ECDICT",
        "upstreamRepository": upstream_repo,
        "upstreamCommit": upstream_commit,
        "inputs": {
            "ecdict.csv": {
                "sha256": csv_sha256,
                "bytes": csv_bytes
            },
            "lemma.en.txt": {
                "sha256": lemma_sha256,
                "bytes": lemma_bytes
            }
        },
        "build": {
            "dictionaryEntries": total_entries,
            "lemmaMappings": total_lemma_mappings,
            "formMappings": total_form_entries
        },
        "generatedAt": now_str
    }
    
    with open(build_manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
    print(f"  Wrote build manifest to {build_manifest_path}.")
    
    elapsed = time.time() - t0
    print(f"=== ECDICT Data Build Completed in {elapsed:.1f}s ===")

if __name__ == '__main__':
    main()
