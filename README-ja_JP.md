# pdfhl

プログレッシブ（進歩的）で寛容なフレーズマッチングを行うPDFテキストハイライター。

**AIエージェント向けに設計されています** （codex や gemini-cli など）。
`pdfhl` は、LLMによるワークフローの中でそのまま利用できるように作られており、エージェントが検索やハイライト処理を、 **ワークフローを乱さず** 実行できることを重視しています。

もちろん手動でも `pdfhl` を実行できますが、主な目的は（学術論文の重要箇所のハイライトなど）エージェント主導の処理で信頼できる基盤を提供することです。

## 概要

`pdfhl`はPDF内のフレーズを検索し、マッチした箇所をハイライトします。その検索機能は、PDF特有の癖やフォーマットの差異に対して堅牢です。

- **プログレッシブフレーズマッチング**: 単語（サブワード）が改行や他のテキストによって区切られていてもフレーズを検出します。これは、チャンク（例：3→2→1サブワード）をマッチさせ、それらを連結することで機能します。
- **mt5ベースの分割（デフォルト）**: クエリは `google/mt5-base` の SentencePiece により多言語サブワードへ分割されます。日本語や混在言語テキストでの検索精度が向上します。カバレッジの最少サブワード数は 3 です。
- **寛容な正規化**: リガチャ（合字）、文字幅（例：`ﬁ`→`f` + `i`）、ハイフン、引用符を正規化します。
- **選択制御**: 文書内で最もコンパクト（最短）なマッチのみをハイライトするか、すべての可能なマッチをハイライトするかを選択できます。
- **安全な設計**: 入力PDFを上書きすることはなく、常に新しいファイルに書き込みます。

## インストール

推奨: GitHub から pipx でインストールします。

安定版タグ（v0.2.0）をインストール:

```bash
pipx install git+https://github.com/tos-kamiya/pdfhl@v0.3.0
```

タグではなく最新の main ブランチを使う場合:

```bash
pipx install --force git+https://github.com/tos-kamiya/pdfhl
```

要件: Python 3.10+。pipx は隔離された環境にインストールし、`pdfhl` CLI を PATH に公開します。後からアップグレードする場合は、同じ `pipx install` コマンドを `--force` 付きで再実行してください。

既定でサブワード分割に `google/mt5-base` を使用します。Python パッケージ `transformers` と `sentencepiece` は依存関係として自動インストールされます。オフライン環境では、あらかじめモデルを取得してローカルパスを `--mt5-model /path/to/mt5-base` で指定してください（後述）。

## クイックスタート

単一のフレーズをハイライトします。デフォルトでは、大文字と小文字を区別せず、最短のマッチを検索します。

```bash
pdfhl input.pdf --text "Deep Learning" -o output.pdf
```

フレーズのすべての出現箇所をハイライトします：

```bash
pdfhl input.pdf --text "Deep Learning" --all-matches -o output.pdf
```

ハイライトのスタイルを設定し、ラベルを追加します：

```bash
pdfhl input.pdf --text "evaluation metrics" --color "#FFEE00" --opacity 0.2 --label "Metrics" -o out.pdf
```

JSONレシピを介して一度に複数のハイライトを適用します：

```bash
pdfhl input.pdf --recipe recipe.json -o out.pdf
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

このように、利用者は対話的に少し修正しながら実行するだけで、ページ分割からハイライト適用までの処理が LLM によって誘導されます。

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
pdfhl PDF [--text TEXT | --recipe JSON] [options]
```

**モード**
- **単一アイテムモード**:
  - `--text TEXT` または `--pattern TEXT` (`--text`のエイリアス)
- **レシピモード**:
  - `--recipe path/to/recipe.json`

**共通オプション**
- `--ignore-case` / `--case-sensitive`
  - デフォルト：大文字と小文字を区別しません。
- `--shortest` / `--all-matches`
  - 選択を制御します。デフォルトは`--shortest`で、文書全体で最もスコアの高い（最もコンパクトな）単一のマッチを検索します。`--all-matches`は、見つかったすべての有効なマッチをハイライトします。
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

**分割（mt5）オプション**
- `--mt5-model PATH_OR_ID`
  - mt5 トークナイザーのモデルパスまたはHubのID。デフォルトは `google/mt5-base`。環境変数 `PDFHL_MT5_MODEL` でも指定可能。
- `--no-mt5`
  - mt5 による分割を無効化します。フォールバックとして単純なホワイトスペース分割を使用します。`PDFHL_USE_MT5=0` でも無効化可能。

注記
- 既定ではクエリは mt5 サブワードに分割され、サブワード間は `\s*` でマッチします（改行・空白欠落に寛容）。
- 最少カバレッジは 3 サブワードです。レシピでは `progressive_kmax`（既定 3）でチャンク長を調整できます。

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
    "selection": "shortest"
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
      "select_shortest": true
    }
  ]
}
```

**注釈**
- `page_index` は0ベース、 `page_number` は1ベースです。
- `start`/`end` は、ページの正規化されたテキストストリームへのインデックスです。

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

オフラインで mt5 を使う場合は、モデルディレクトリを事前に用意し（キャッシュをコピー等）、次のように指定してください：

```bash
pdfhl input.pdf --text "..." --mt5-model /path/to/google/mt5-base
```

## ライセンス

`pdfhl` は [MIT](https://spdx.org/licenses/MIT.html) ライセンスの条件の下で配布されています。
