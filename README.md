# kaoyan-ecdict-data

ECDICT (Free English to Chinese Dictionary Database) 数据子模块，为 Kaoyan-Tiku Lexicon Pipeline 及后续 Astra 全量 Lexicon Fusion 提供通用词典数据底座。

## 1. 职责边界与规范

### 本模块负责
- `word`：原始词条（严格保留大小写，支持大小写不敏感检索）
- `lemma`：词元 / 原形关联（以 `lemma.en.txt` 及 `exchange` 为准）
- `phonetic`：音标 / IPA
- `pos`：词性标注
- `definition`：英文释义
- `translation`：中文释义
- `tag`：考试及分级标签（zk, gk, cet4, cet6, ky, toefl, ielts 等）
- `bnc`：英国国家语料库（BNC）通用词频顺序（保存为一般语料频率，绝不能展示或重命名为“考研词频”）
- `frq`：当代语料库通用词频顺序（保存为一般语料频率，绝不能展示或重命名为“考研词频”）
- `exchange`：时态、单复数、分词等形态变形信息（保留原始字符串并生成结构化索引）
- 通用词典查询接口与高性能 SQLite 支持

### 本模块不负责
- 考研 `sentenceCount`（例句数）
- 考研 `occurrenceCount`（真题出现频次）
- 考研 `paperCount`（考查试卷数）
- 考研年份分布（`yearDistribution`）
- 考研题型分布（`questionTypeDistribution`）
- 真题上下文词义（`contextMeaning`）
- Personal PDF 与 Exam-point PDF 融合
- 前端展示与逻辑

---

## 2. 上游来源 (Upstream)

- **官方仓库**：[https://github.com/skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)
- **锁定 Commit Hash**：`bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`
- **核心文件**：
  - `ecdict.csv`：770,611 条词典记录，SHA-256: `1a6947e04785db63613a92e14903cdae7954f7e84860b10e68e5c7cbb3f9c3cf`
  - `lemma.en.txt`：84,487 组 Lemma-Form 映射，SHA-256: `e255b097404e3e0052060e2ddf6e15a1414f577071d63d51d2ca0ce9dacee0fc`
- **原始数据保护**：`raw/` 目录中的上游源文件保持 100% 原始状态，禁止手动修改。

---

## 3. 目录结构

```
kaoyan-ecdict-data/
├── README.md                 # 模块说明与使用指南
├── upstream/
│   └── metadata.json         # 上游锁定元数据（commit, url, license 等）
├── raw/
│   ├── ecdict.csv            # 原始 ECDICT CSV 文件（770,611 行）
│   └── lemma.en.txt          # 原始 Lemma 映射文件（84,487 行）
├── db/
│   └── ecdict.sqlite         # 高性能 SQLite 数据库（entries, lemma_lookup, word_forms）
├── indexes/
│   ├── lemma.jsonl           # 变体到词元映射索引（surface/form -> lemma）
│   └── forms.jsonl           # 词元到变体形式索引（lemma -> forms）
├── scripts/
│   ├── build.py              # 构建脚本（生成 SQLite、indexes、manifest）
│   └── validate.py           # 校验与审计脚本（验证完整性、覆盖率并生成 report）
├── manifests/
│   └── build.json            # 构建清单（记录输入 hash、大小、词条数等）
└── audit/
    └── report.json           # 审计检验报告（完整性、字段覆盖率、未解析统计等）
```

---

## 4. 数据格式与 Schema

### 4.1 Canonical Dictionary Record
从 `ecdict.csv` deterministic 转换而来：
```json
{
  "source": "ecdict",
  "word": "perceive",
  "phonetic": "pə'si:v",
  "definition": "become conscious of\nperceive by the senses",
  "translation": "vt. 察觉, 感知; 理解",
  "pos": null,
  "collins": 3,
  "oxford": 1,
  "tag": "zk gk cet4 cet6 ky toefl ielts",
  "bnc": 2841,
  "frq": 3410,
  "exchange": "d:perceived/p:perceived/3:perceives/i:perceiving",
  "detail": null,
  "audio": null
}
```

### 4.2 SQLite 数据表设计 (`db/ecdict.sqlite`)

1. **`entries` 表**：
   - 存储全部 770,611 条词条。
   - 包含索引：`idx_entries_word` (精确词查询), `idx_entries_word_lower` (不区分大小写查询)。
2. **`lemma_lookup` 表**：
   - 存储 `form` -> `lemma` 映射及来源（`lemma.en.txt` / `ecdict.exchange`）。
   - 包含索引：`idx_lemma_form`, `idx_lemma_form_lower`, `idx_lemma_lemma`。
3. **`word_forms` 表**：
   - 存储 `lemma` -> `(form_type, form)` 映射。
   - 包含索引：`idx_forms_lemma`, `idx_forms_lemma_lower`, `idx_forms_form`。

---

## 5. 构建与验证命令

### 重新构建
```bash
python scripts/build.py
```

### 执行审计与检验
```bash
python scripts/validate.py
```

---

## 6. 查询示例 (Python)

```python
import sqlite3

conn = sqlite3.connect("db/ecdict.sqlite")
cur = conn.cursor()

# 1. 精确查询
cur.execute("SELECT word, phonetic, translation FROM entries WHERE word = ?", ("perceive",))
print(cur.fetchone())

# 2. 大小写不敏感查询
cur.execute("SELECT word, translation FROM entries WHERE word_lower = ?", ("dna",))
print(cur.fetchall())

# 3. 变形查原形 (Form -> Lemma)
cur.execute("SELECT lemma, source FROM lemma_lookup WHERE form_lower = ?", ("perceived",))
print(cur.fetchall())

# 4. 原形查变形 (Lemma -> Forms)
cur.execute("SELECT form_type, form FROM word_forms WHERE lemma = ?", ("perceive",))
print(cur.fetchall())

# 5. 批量查询
cur.execute("SELECT word, translation FROM entries WHERE word IN ('give', 'take', 'perceive')")
print(cur.fetchall())
```
