# -*- coding: utf-8 -*-
"""
ECDICT Data Submodule Validator & Auditor
Performs full validation across raw data, indexes, and SQLite database.
Generates audit/report.json.
"""
import os, sys, csv, json, sqlite3, time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, 'raw')
DB_DIR = os.path.join(BASE_DIR, 'db')
INDEXES_DIR = os.path.join(BASE_DIR, 'indexes')
MANIFESTS_DIR = os.path.join(BASE_DIR, 'manifests')
AUDIT_DIR = os.path.join(BASE_DIR, 'audit')

def main():
    t0 = time.time()
    print("=== Starting ECDICT Validation & Audit ===")
    
    csv_path = os.path.join(RAW_DIR, 'ecdict.csv')
    lemma_path = os.path.join(RAW_DIR, 'lemma.en.txt')
    sqlite_path = os.path.join(DB_DIR, 'ecdict.sqlite')
    lemma_jsonl_path = os.path.join(INDEXES_DIR, 'lemma.jsonl')
    forms_jsonl_path = os.path.join(INDEXES_DIR, 'forms.jsonl')
    build_manifest_path = os.path.join(MANIFESTS_DIR, 'build.json')
    report_path = os.path.join(AUDIT_DIR, 'report.json')
    
    # 1. Check file existence
    assert os.path.exists(csv_path), f"Missing {csv_path}"
    assert os.path.exists(lemma_path), f"Missing {lemma_path}"
    assert os.path.exists(sqlite_path), f"Missing {sqlite_path}"
    assert os.path.exists(lemma_jsonl_path), f"Missing {lemma_jsonl_path}"
    assert os.path.exists(forms_jsonl_path), f"Missing {forms_jsonl_path}"
    assert os.path.exists(build_manifest_path), f"Missing {build_manifest_path}"
    
    print("1. Validating raw/ecdict.csv parsing and fields...")
    csv_row_count = 0
    empty_word_count = 0
    duplicate_exact_count = 0
    duplicate_lower_count = 0
    malformed_exchange_count = 0
    malformed_exchange_samples = []
    
    empty_phonetic_count = 0
    empty_definition_count = 0
    empty_translation_count = 0
    has_pos_count = 0
    has_bnc_count = 0
    has_frq_count = 0
    
    seen_words = set()
    seen_words_lower = set()
    
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        header = next(reader)
        expected_header = ['word', 'phonetic', 'definition', 'translation', 'pos', 'collins', 'oxford', 'tag', 'bnc', 'frq', 'exchange', 'detail', 'audio']
        assert header == expected_header, f"Header mismatch: {header} vs {expected_header}"
        
        for row in reader:
            csv_row_count += 1
            w = row[0]
            if not w or not w.strip():
                empty_word_count += 1
            
            if w in seen_words:
                duplicate_exact_count += 1
            else:
                seen_words.add(w)
            
            w_lower = w.lower()
            if w_lower in seen_words_lower:
                duplicate_lower_count += 1
            else:
                seen_words_lower.add(w_lower)
            
            if len(row) <= 1 or not row[1].strip(): empty_phonetic_count += 1
            if len(row) <= 2 or not row[2].strip(): empty_definition_count += 1
            if len(row) <= 3 or not row[3].strip(): empty_translation_count += 1
            if len(row) > 4 and row[4].strip(): has_pos_count += 1
            if len(row) > 8 and row[8].strip(): has_bnc_count += 1
            if len(row) > 9 and row[9].strip(): has_frq_count += 1
            
            # Check exchange formatting
            if len(row) > 10 and row[10].strip():
                exchange = row[10].strip()
                for token in exchange.split('/'):
                    token = token.strip()
                    if not token: continue
                    if ':' not in token:
                        malformed_exchange_count += 1
                        if len(malformed_exchange_samples) < 10:
                            malformed_exchange_samples.append({'word': w, 'token': token})
                    else:
                        k, v = token.split(':', 1)
                        if not k.strip() or not v.strip():
                            malformed_exchange_count += 1
                            if len(malformed_exchange_samples) < 10:
                                malformed_exchange_samples.append({'word': w, 'token': token})
    
    print(f"  Raw CSV Rows: {csv_row_count}")
    print(f"  Empty Words: {empty_word_count}")
    print(f"  Duplicates (exact): {duplicate_exact_count}")
    print(f"  Duplicates (lower): {duplicate_lower_count}")
    print(f"  Malformed Exchanges: {malformed_exchange_count}")
    
    # 2. Check indexes/lemma.jsonl
    print("2. Validating indexes/lemma.jsonl...")
    lemma_mappings_count = 0
    with open(lemma_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                lemma_mappings_count += 1
    print(f"  Lemma Mappings in index: {lemma_mappings_count}")
    
    # 3. Check indexes/forms.jsonl
    print("3. Validating indexes/forms.jsonl...")
    forms_index_count = 0
    with open(forms_jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                forms_index_count += 1
    print(f"  Forms Index in index: {forms_index_count}")
    
    # 4. Check db/ecdict.sqlite
    print("4. Validating db/ecdict.sqlite...")
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    
    cur.execute("SELECT count(*) FROM entries;")
    sqlite_entries_count = cur.fetchone()[0]
    
    cur.execute("SELECT count(*) FROM lemma_lookup;")
    sqlite_lemma_count = cur.fetchone()[0]
    
    cur.execute("SELECT count(*) FROM word_forms;")
    sqlite_forms_count = cur.fetchone()[0]
    
    assert sqlite_entries_count == csv_row_count, f"Mismatch: SQLite entries {sqlite_entries_count} != CSV rows {csv_row_count}"
    assert sqlite_lemma_count == lemma_mappings_count, f"Mismatch: SQLite lemma_lookup {sqlite_lemma_count} != lemma.jsonl {lemma_mappings_count}"
    
    print(f"  SQLite entries count: {sqlite_entries_count} (Matches CSV: True)")
    print(f"  SQLite lemma_lookup count: {sqlite_lemma_count}")
    print(f"  SQLite word_forms count: {sqlite_forms_count}")
    
    # 5. Check unresolved lemmas (lemmas in lemma_lookup pointing to words not in entries)
    print("5. Checking unresolved lemmas...")
    cur.execute("""
        SELECT count(DISTINCT l.lemma)
        FROM lemma_lookup l
        LEFT JOIN entries e ON l.lemma = e.word
        WHERE e.word IS NULL;
    """)
    unresolved_lemmas_exact = cur.fetchone()[0]
    
    cur.execute("""
        SELECT count(DISTINCT l.lemma)
        FROM lemma_lookup l
        LEFT JOIN entries e ON l.form_lower = e.word_lower
        WHERE e.word_lower IS NULL;
    """)
    unresolved_forms_in_dict = cur.fetchone()[0]
    
    cur.execute("""
        SELECT count(DISTINCT l.lemma)
        FROM lemma_lookup l
        LEFT JOIN entries e ON lower(l.lemma) = e.word_lower
        WHERE e.word_lower IS NULL;
    """)
    unresolved_lemmas_case_insensitive = cur.fetchone()[0]
    
    print(f"  Unresolved lemmas (exact headword match): {unresolved_lemmas_exact}")
    print(f"  Unresolved lemmas (case-insensitive headword match): {unresolved_lemmas_case_insensitive}")
    
    # Sample unresolved lemmas
    cur.execute("""
        SELECT DISTINCT l.lemma
        FROM lemma_lookup l
        LEFT JOIN entries e ON lower(l.lemma) = e.word_lower
        WHERE e.word_lower IS NULL
        LIMIT 10;
    """)
    sample_unresolved_lemmas = [row[0] for row in cur.fetchall()]
    
    # 6. Verify SQLite Functional Capabilities
    print("6. Verifying SQLite query interface capabilities...")
    # Exact lookup
    cur.execute("SELECT word, translation FROM entries WHERE word = 'perceive';")
    exact_res = cur.fetchall()
    assert len(exact_res) == 1, f"Exact lookup failed: {exact_res}"
    
    # Case-insensitive lookup
    cur.execute("SELECT word, translation FROM entries WHERE word_lower = 'perceive';")
    case_res = cur.fetchall()
    assert len(case_res) >= 1, f"Case-insensitive lookup failed: {case_res}"
    
    # Form -> lemma lookup
    cur.execute("SELECT lemma, source FROM lemma_lookup WHERE form_lower = 'perceived';")
    form_res = cur.fetchall()
    assert any(r[0] == 'perceive' for r in form_res), f"Form->lemma lookup failed: {form_res}"
    
    # Lemma -> forms lookup
    cur.execute("SELECT form_type, form FROM word_forms WHERE lemma = 'perceive';")
    lemma_res = cur.fetchall()
    assert len(lemma_res) > 0, f"Lemma->forms lookup failed: {lemma_res}"
    
    # Batch lookup
    cur.execute("SELECT word FROM entries WHERE word IN ('give', 'take', 'perceive');")
    batch_res = cur.fetchall()
    assert len(batch_res) == 3, f"Batch lookup failed: {batch_res}"
    print("  All 5 query capabilities verified successfully.")
    
    conn.close()
    
    # 7. Check Manifest
    manifest = json.load(open(build_manifest_path, encoding='utf-8'))
    assert manifest['build']['dictionaryEntries'] == csv_row_count
    assert manifest['build']['lemmaMappings'] == lemma_mappings_count
    assert manifest['build']['formMappings'] == forms_index_count
    
    # 8. Compile Audit Report
    report = {
        "auditVersion": "ecdict-audit-1.0",
        "generatedAt": time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        "upstream": {
            "repository": manifest.get("upstreamRepository"),
            "commit": manifest.get("upstreamCommit"),
            "files": {
                "ecdict.csv": manifest["inputs"]["ecdict.csv"],
                "lemma.en.txt": manifest["inputs"]["lemma.en.txt"]
            }
        },
        "integrity": {
            "csvFullyParsed": True,
            "csvRowCount": csv_row_count,
            "emptyWordCount": empty_word_count,
            "duplicateWordExactCount": duplicate_exact_count,
            "duplicateWordLowerCount": duplicate_lower_count,
            "malformedExchangeCount": malformed_exchange_count,
            "malformedExchangeSamples": malformed_exchange_samples,
            "sqliteEntriesMatchesCsv": (sqlite_entries_count == csv_row_count),
            "sqliteLemmaMatchesIndex": (sqlite_lemma_count == lemma_mappings_count)
        },
        "counts": {
            "dictionaryEntries": csv_row_count,
            "lemmaMappings": lemma_mappings_count,
            "formsIndexLemmas": forms_index_count,
            "sqliteEntriesRows": sqlite_entries_count,
            "sqliteLemmaLookupRows": sqlite_lemma_count,
            "sqliteWordFormsRows": sqlite_forms_count,
            "unresolvedLemmasExact": unresolved_lemmas_exact,
            "unresolvedLemmasCaseInsensitive": unresolved_lemmas_case_insensitive,
            "sampleUnresolvedLemmas": sample_unresolved_lemmas
        },
        "coverage": {
            "phonetic": {
                "emptyCount": empty_phonetic_count,
                "presentCount": csv_row_count - empty_phonetic_count,
                "coverageRate": round((csv_row_count - empty_phonetic_count) / csv_row_count, 4)
            },
            "definition": {
                "emptyCount": empty_definition_count,
                "presentCount": csv_row_count - empty_definition_count,
                "coverageRate": round((csv_row_count - empty_definition_count) / csv_row_count, 4)
            },
            "translation": {
                "emptyCount": empty_translation_count,
                "presentCount": csv_row_count - empty_translation_count,
                "coverageRate": round((csv_row_count - empty_translation_count) / csv_row_count, 4)
            },
            "pos": {
                "presentCount": has_pos_count,
                "coverageRate": round(has_pos_count / csv_row_count, 4)
            },
            "bnc": {
                "presentCount": has_bnc_count,
                "coverageRate": round(has_bnc_count / csv_row_count, 4)
            },
            "frq": {
                "presentCount": has_frq_count,
                "coverageRate": round(has_frq_count / csv_row_count, 4)
            }
        },
        "queryVerification": {
            "exactWordLookup": True,
            "caseInsensitiveLookup": True,
            "formToLemmaLookup": True,
            "lemmaToFormsLookup": True,
            "batchLookup": True
        }
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  Audit report written to {report_path}.")
    
    elapsed = time.time() - t0
    print(f"=== ECDICT Validation Completed in {elapsed:.1f}s ===")

if __name__ == '__main__':
    main()
