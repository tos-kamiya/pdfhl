# pdfhl

プログレッシブ（進歩的）で寛容なフレーズマッチングを行うPDFテキストハイライター。

**AIエージェント向けに設計されています** （codex や gemini-cli など）。
`pdfhl` は、LLMによるワークフローの中でそのまま利用できるように作られており、エージェントが検索やハイライト処理を、 **ワークフローを乱さず** 実行できることを重視しています。

もちろん手動でも `pdfhl-cli` を実行できますが、主な目的は（学術論文の重要箇所のハイライトなど）エージェント主導の処理で信頼できる基盤を提供することです。

## 概要

`pdfhl`はPDF内のフレーズを検索し、マッチした箇所をハイライトします。その検索機能は、PDF特有の癖やフォーマットの差異に対して堅牢です。

- **プログレッシブフレーズマッチング**: 単語（サブワード）が改行や他のテキストによって区切られていてもフレーズを検出します。これは、チャンク（例：3→2→1サブワード）をマッチさせ、それらを連結することで機能します。
- **mt5ベースの分割（デフォルト）**: クエリは `google/mt5-base` の SentencePiece により多言語サブワードへ分割されます。日本語や混在言語テキストでの検索精度が向上します。カバレッジの最少サブワード数は 3 です。
- **寛容な正規化**: リガチャ（合字）、文字幅（例：`ﬁ`→`f` + `i`）、ハイフン、引用符を正規化します。
- **選択制御**: 文書内で最もコンパクト（最短）なマッチのみをハイライトするか、すべての可能なマッチをハイライトするかを選択できます。
- **安全な設計**: 入力PDFを上書きすることはなく、常に新しいファイルに書き込みます。

## インストール

推奨: GitHub から pipx でインストールします。

安定版タグ（v0.3.0）をインストール:

```bash
pipx install git+https://github.com/tos-kamiya/pdfhl@v0.3.0
```

タグではなく最新の main ブランチを使う場合:

```bash
pipx install --force git+https://github.com/tos-kamiya/pdfhl
```

要件: Python 3.10+。上記コマンドでライブラリと `pdfhl-cli` 実行ファイルがインストールされます。

既定でサブワード分割に `google/mt5-base` を使用します。トークナイザー本体は初回実行時にダウンロードされ、キャッシュ後はオフラインでも利用可能です。環境変数 `PDFHL_MT5_MODEL` を設定すれば別のトークナイザーを使用可能です。

## クイックスタート

単一のフレーズをハイライトします。デフォルトでは、大文字と小文字を区別せず、最短のマッチを検索します。

```bash
pdfhl-cli input.pdf --text "Deep Learning" -o output.pdf
```

フレーズのすべての出現箇所をハイライトします：

```bash
pdfhl-cli input.pdf --text "Deep Learning" --all-matches -o output.pdf
```

ハイライトのスタイルを設定し、ラベルを追加します：

```bash
pdfhl-cli input.pdf --text "evaluation metrics" --color "#FFEE00" --opacity 0.2 --label "Metrics" -o out.pdf
```

JSONレシピを介して一度に複数のハイライトを適用します：

```bash
pdfhl-cli input.pdf --recipe recipe.json -o out.pdf
```

詳細は `examples/` を参照してください：
- `examples/simple-recipe-array.json`
- `examples/recipe-with-items-object.json`

## 利用例: 学術論文のハイライト

このツールの代表的な利用例のひとつは、**学術論文の重要な部分（アプローチ・実験・妥当性の脅威）をハイライト**して素早く確認できるようにすることです。

補助的なスクリプトとプロンプトを `extra-utils/` に用意しています：

* `extra-utils/pdftopages` — PDF をページごとのテキスト（Markdown）に分割します
* `extra-utils/prompt-paper-highlights.txt` — LLM に重要文を特定させるためのプロンプト

### 使い方（対話的）

codex や gemini-cli にプロンプトを入力し、必要に応じてファイル名を書き換えるだけで実行できます。

1. `extra-utils/prompt-paper-highlights.txt` の内容をコピーします。
2. 冒頭の `{file.pdf}` を実際のPDFファイル名に置き換えます。
3. それを codex や gemini-cli に貼り付けます。
4. `pdftopages` は、あらかじめ `$PATH` の通ったディレクトリに置くか、プロンプト内でスクリプトへのフルパスを指定してください。

このように、利用者は対話的に少し修正しながら実行するだけで、ページ分割からハイライト適用までの処理が LLM によって誘導されます（`pdfhl-cli` を呼び出すステップを含む）。

### 色分け規則

プロンプトでは以下の色分けを使用します：

* **青** = アプローチ
* **緑** = 実験
* **赤** = 妥当性の脅威

**実行例**

* [docs/icpc-2022-zhu.highlighted.pdf](docs/icpc-2022-zhu.highlighted.pdf)
* [docs/kbse-202405-kamiya.highlighted.pdf](docs/kbse-202405-kamiya.highlighted.pdf) (日本語)

## CLIリファレンス

```
pdfhl-cli PDF [--text TEXT | --recipe JSON] [options]
```

**モード**
- **単一アイテムモード**:
  - `--text TEXT` または `--pattern TEXT` (`--text`のエイリアス)
- **レシピモード**:
  - `--recipe path/to/recipe.json`

**共通オプション**
- `--ignore-case` / `--case-sensitive`
  - デフォルト：大文字と小文字を区別しません。
- `--shortest` / `--all-matches` / `--error-on-multiple`
  - `SelectionMode` を制御します。デフォルトは `--shortest`（最良のマッチ）。`--all-matches` はすべてをハイライトし、`--error-on-multiple` は複数マッチ時にエラーとします。
- `--dry-run`
  - 検索のみを行い、出力ファイルを書き込みません。
- `-o, --output PATH`
  - 出力PDFパス。デフォルトは `<input>.highlighted.pdf` です。
- `--label STR`
  - 注釈のタイトル/コンテンツラベル。
- `--color VAL`
  - 色を名前（`yellow|mint|violet|red|green|blue`）、16進数（`#RRGGBB`）、または`r,g,b`（各0..1）で指定します。
- `--opacity FLOAT`
  - ハイライトの不透明度（0..1）、デフォルトは `0.3` です。
- `--report json`
  - JSONレポートを標準出力に出力します。

注記
- 既定ではクエリは mt5 サブワードに分割され、サブワード間は `\s*` でマッチします（改行・空白欠落に寛容）。
- 最少カバレッジは 3 サブワードです。レシピでは `progressive_kmax`（既定 3）でチャンク長を調整できます。
- 初回実行時のみ `google/mt5-base` のダウンロードにネットワーク接続が必要です。キャッシュされた後はオフラインでも利用できます。

**出力ポリシー**
- 入力PDFは変更されません。このツールは入力パスへの上書きを拒否します。異なる `-o/--output` を指定してください。

**終了コード**
- `0`: OK
- `1`: 見つかりません（いずれかのレシピアイテムが0件のマッチだった場合）
- `2`: (未使用)
- `3`: エラー（オープン/セーブの失敗、無効なパス、上書き拒否など）

## JSONレシピフォーマット (`--recipe`)

トップレベルのアイテム配列、または `items: [...]` キーを持つオブジェクトを渡すことができます。すべての検索はプログレッシブマッチングアルゴリズムを使用します。

**トップレベル配列の例：**
```json
[
  {"text": "Introduction", "color": "mint"},
  {"text": "Threats to Validity", "color": "red", "select_shortest": false}
]
```

**`items` を持つオブジェクトの例：**
```json
{
  "items": [
    {"text": "Experiment", "color": "green", "label": "Experiment"},
    {"text": "Conclusion", "color": "violet", "opacity": 0.25}
  ]
}
```

**アイテムごとのフィールド：**
- `text` または `pattern` (string, 必須): 検索するフレーズ。
- `ignore_case` (bool, デフォルト `true`): 大文字と小文字を区別しない検索を実行するかどうか。
- `select_shortest` (bool, デフォルト `true`): `true`の場合、最良の単一マッチのみをハイライトします。`false`の場合、見つかったすべてのマッチをハイライトします（`--all-matches`と同等）。
- `label` (string | null): 注釈ラベル。
- `color` (string | null): 色名、16進数、または `r,g,b` の浮動小数点値。
- `opacity` (float | null): ハイライトの不透明度（0..1）。設定されていない場合はCLIのデフォルト値が使用されます。
- `progressive_kmax` (int, デフォルト `3`): (上級者向け) 検索チャンク内の最大単語数。
- `progressive_max_gap_chars` (int, デフォルト `200`): (上級者向け) マッチしたチャンク間のギャップで許容される最大文字数。

補足
- クエリの分割は mt5 サブワードに基づきます。カバレッジ判定はサブワード数で行い、既定の最少値は 3 です。

## JSONレポート (`--report json`)

**単一アイテムモードの出力：**
```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "matches": 1,
  "exit_code": 0,
  "dry_run": false,
  "hits": [
    {
      "page_index": 0,
      "page_number": 1,
      "start": 123,
      "end": 135,
      "rects": [[x0, y0, x1, y1], ...]
    }
  ],
  "context": {
    "query": "...",
    "ignore_case": true,
    "selection_mode": "best"
  }
}
```

**レシピモードの出力（集約）：**
```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "items": [
    {
      "index": 0,
      "query": "Introduction",
      "matches": 1,
      "hits": [
        {"page_index": 0, "page_number": 1, "start": 10, "end": 22, "rects": [[...]]}
      ],
      "progressive_search": true,
      "progressive_kmax": 3,
      "progressive_max_gap_chars": 200,
      "selection_mode": "best"
    }
  ]
}
```

**注釈**
- `page_index` は0ベース、 `page_number` は1ベースです。
- `start`/`end` は、ページの正規化されたテキストストリームへのインデックスです。

## ライブラリ API

`pdfhl` は Python から直接呼び出せる軽量な API を提供します。`examples/sample.pdf` という小さな PDF を同梱しているので、以下のコードをそのまま試せます。

単一のフレーズを 1 回の呼び出しでハイライトして保存:

```python
from pathlib import Path
from pdfhl import SelectionMode, highlight_text

outcome = highlight_text(
    Path("examples/sample.pdf"),
    "pdfhl sample document",
    output=Path("examples/sample.highlighted.pdf"),
    color="#ffeb3b",
    label="Example",
    selection_mode=SelectionMode.BEST,
)
print(outcome.highlight_count, outcome.segment_matches, outcome.saved_path)
```

`outcome.highlight_count` は実際にハイライトされる範囲の件数、`outcome.segment_matches` はプログレッシブ検索による生のセグメント数を表します。

同じ PDF に複数のクエリをバッチ適用:

```python
from pdfhl import PdfHighlighter, SelectionMode

with PdfHighlighter.open("examples/sample.pdf") as hl:
    single = hl.highlight_text("pdfhl sample document", selection_mode=SelectionMode.BEST, dry_run=True)  # dry-run なので PDF には反映されません
    multi = hl.highlight_text("progressive highlight example", color="violet", selection_mode=SelectionMode.ALL)
    summary = hl.save("examples/sample.highlighted.pdf")

print(single.highlight_count, single.segment_matches)
print(multi.highlight_count, multi.segment_matches)
```

`with` を使わずにライフサイクルを明示的に管理することもできます:

```python
from pdfhl import PdfHighlighter, SelectionMode

hl = PdfHighlighter.open("examples/sample.pdf")
try:
    hl.highlight_text("multiple times", color="#ff9800", label="Sample", selection_mode=SelectionMode.ALL)
    hl.highlight_text("pdfhl sample document", selection_mode=SelectionMode.SINGLE)
    outcome = hl.save("examples/sample.highlighted.pdf")
finally:
    hl.close()

print(outcome.highlight_count, outcome.segment_matches)
```

### `highlight_text` の引数

`pdfhl.highlight_text()` は `HighlightOutcome` を返し、次のトップレベル引数を受け取ります。

| パラメータ | 型 | 既定値 | 説明 |
|------------|----|--------|------|
| `pdf_path` | `str | Path` | — | 読み込む PDF のパス。 |
| `text` | `str` | — | 検索してハイライトする語句。 |
| `output` | `Path | None` | `None` | 出力 PDF のパス。未指定のときは `<input>.highlighted.pdf`。 |
| `dry_run` | `bool` | `False` | PDF を変更せず、マッチ結果だけ確認。 |

`PdfHighlighter.highlight_text()` も同じキーワード引数を受け取り、スタンドアロン関数は `**kwargs` として伝播します。

| キーワード | 型 | 既定値 | 説明 |
|-------------|----|--------|------|
| `color` | `str | Sequence[float] | None` | `"#ffeb3b"` | ハイライト色。`yellow`/`mint`/`violet`/`red`/`green`/`blue` のプリセット、`#RRGGBB`、または 0..1 の浮動小数 3 要素を指定可能。 |
| `label` | `str | None` | `None` | PDF ビューアに表示される注釈タイトル/本文。省略時は空欄。 |
| `selection_mode` | `SelectionMode` | `SelectionMode.BEST` | マッチ選択方法を指定します（`SINGLE` / `BEST` / `ALL`）。 |
| `ignore_case` | `bool` | `True` | 大文字小文字を無視して検索。 |
| `literal_whitespace` | `bool` | `False` | 正規表現生成時にクエリの空白をそのまま扱う。 |
| `regex` | `bool` | `False` | `text` を正規表現として解釈。 |
| `progressive` | `bool` | `True` | 寛容なプログレッシブ検索を使う（`False` でリテラル検索）。 |
| `progressive_kmax` | `int` | `3` | プログレッシブ検索での最大チャンク長。 |
| `progressive_max_gap_chars` | `int` | `200` | セグメント間の許容ギャップ（文字数）。 |
| `progressive_min_total_words` | `int` | `3` | プログレッシブ検索時に必要な最小サブワード数。 |
| `opacity` | `float` | `0.3` | ハイライトの不透明度 (0..1)。 |
| `dry_run` | `bool` | `False` | アノテーションを適用せずマッチだけ確認（スタンドアロン関数の `dry_run` と同等）。 |
| `page_filter` | `Callable[[PageInfo], bool] | None` | `None` | 検索対象のページを絞り込むフィルタ。 |

## 開発

### テストの実行

パッケージ自体をインストールせずにテストを実行できます。uv または標準の venv/pip のどちらでもOKです。

Option A — uv（推奨）:
```bash
# .venv/ に仮想環境を作成して有効化
uv venv
source .venv/bin/activate

# pytest のみインストール（テストは重い依存を避けています）
uv pip install pytest

# テスト実行
pytest -q
```

Option B — Python 標準 venv/pip:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip pytest
pytest -q
```

注記
- テストは純粋ロジック中心で、PyMuPDF や transformers が未インストールでも動作します。未インストール時の警告は無害です。
- 仮想環境をアクティベートせず、フルパス指定（例: `.venv/bin/pytest -q`）でも実行できます。

## ライセンス

`pdfhl` は [MIT](https://spdx.org/licenses/MIT.html) ライセンスの条件の下で配布されています。
