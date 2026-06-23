# investment-advisor

NotionをSingle Source of Truth（正本）とする、個人用のAI投資レビューツールです。

SBI証券のポートフォリオCSVをNotionに取り込み、複数の視点を持つAIエージェントが週次でポートフォリオをレビューし、週次レポートをNotionページとして生成します。**自動売買は行わず、投資判断を断定しません。** AIの出力はあくまで意思決定支援であり、最終判断はユーザーが行う前提です。

## 特徴

- **Notion中心の運用** — 保有資産・投資方針・エージェント定義・レポートをすべてNotionのデータベースで管理します。
- **SBI証券CSVの取り込み** — Shift-JIS・複数セクション構成のSBI「ポートフォリオ一覧」CSVをパースし、Holdings DBへ反映します。手動管理の資産（`データソース = Manual`）は上書き・削除しません。
- **複数視点のAI投資委員会** — 「FIRE達成重視」「老後安全性重視」「投機チャンス探索」「リスク管理」の4エージェントが分析し、議長（Synthesizer）が意見の対立とアクション候補を統合します。
- **読み物型の週次レポート生成** — ポートフォリオ状況・FIRE目標との距離・保有銘柄関連ニュース・投資委員会（4エージェント）の見立てを、議長が一本の「投資読み物」として再編集し、Notionページに作成します。各エージェントの詳細分析は Agent Analysis Results DB を正本として保存し、レポート本文にはそのまま転記しません。
- **LLMプロバイダの切り替え** — Provider / Modelは設定で切り替え可能。初期候補はGemini、Claudeにも対応します。

## 必要環境

- Python 3.11 以上
- Notion インテグレーショントークンと、PRDで定義された各データベース
- LLM APIキー（Gemini もしくは Claude）

## セットアップ

```bash
# リポジトリを取得
git clone https://github.com/ka-zuu/investment-advisor.git
cd investment-advisor

# 仮想環境（任意）
python -m venv .venv
source .venv/bin/activate

# 依存パッケージのインストール（開発用ツールを含む）
pip install -e ".[dev]"

# 環境変数の設定
cp .env.example .env
# .env を編集して Notion トークン・LLM APIキー等を設定する
```

`.env` の主な設定項目は `.env.example` を参照してください。Notion DB の ID は空のままでも、初回実行時に DB 名から自動解決して `.env` に書き戻されます。

## 使い方

### 週次バッチの実行

PRD §12 の実行フロー（PRDスナップショット保存 → CSV取り込み → ポートフォリオ集計 → スナップショット保存 → ニュース収集 → エージェント分析 → レポート生成）を一括で実行します。

```bash
python -m investment_advisor.main
```

cron や systemd timer での定期実行には `scripts/run_weekly.sh` を利用できます。

```bash
# cron例: 毎週日曜 8:00 に実行
0 8 * * 0 /path/to/investment-advisor/scripts/run_weekly.sh
```

### SBI CSV のみを取り込む

未処理のSBI CSVの取り込みだけを単体で実行します。

```bash
python scripts/import_sbi_csv.py
```

## プロジェクト構成

```text
investment-advisor/
├─ src/investment_advisor/
│  ├─ main.py            # 週次バッチのエントリポイント（§12 実行フロー）
│  ├─ config.py          # .env 読み込み・Notion DB ID の自動解決
│  ├─ notion_client.py   # Notion API クライアント
│  ├─ prd_loader.py      # PRD スナップショット保存
│  ├─ sbi_csv/           # SBI CSV のパース・マッピング・取り込み
│  ├─ portfolio/         # ポートフォリオ集計・スナップショット・FIRE 差分
│  ├─ news/              # ニュース収集・要約（P1）
│  ├─ agents/            # エージェント実行・プロンプト・レポート生成
│  └─ utils/             # ロギング・金額計算ユーティリティ
├─ scripts/
│  ├─ run_weekly.sh      # 週次バッチ実行スクリプト
│  └─ import_sbi_csv.py  # SBI CSV 取り込みのみ実行
├─ docs/
│  ├─ prd.snapshot.md    # 実装が参照した時点の PRD 凍結コピー
│  └─ sbi_csv_spec.md    # SBI CSV 仕様の補助スナップショット
├─ tests/                # pytest テスト・匿名化フィクスチャ
├─ CLAUDE.md             # Claude Code 向け恒久ルール
└─ pyproject.toml
```

## テスト

```bash
python -m pytest tests/ -v
```

`main` への push と Pull Request では GitHub Actions（`.github/workflows/ci.yml`）が同じテストを実行します。

## 仕様・ドキュメント

最新仕様は **Notion の PRD が正本**です。リポジトリ内では仕様を二重管理せず、次の役割分担としています。

- `docs/prd.snapshot.md` — その実装が参照した PRD の凍結コピー。
- `docs/sbi_csv_spec.md` — SBI CSV 仕様の補助スナップショット。
- `CLAUDE.md` — Claude Code が起動時に読み込む恒久ルール（手動資産の保護・投資判断の断定禁止・秘密情報や本物CSVのコミット禁止）。

エージェントの役割・プロンプトは Notion の Agent DB を正本として管理します。

## 安全・運用上の注意

- 自動売買・証券口座への発注は行いません。
- AI の分析は根拠・反対意見・不確実性を含む意思決定支援であり、断定的な投資助言ではありません。最終判断はユーザーが行います。
- `.env` の API キー・Notion トークン、および本物の SBI 証券 CSV・個人情報は **Git にコミットしないでください**。テストでは匿名化したサンプルデータのみを使用します。
- `データソース = Manual` の Holdings レコードは CSV 取り込みで上書き・削除されません。

## ライセンス

個人用プロジェクトです。
