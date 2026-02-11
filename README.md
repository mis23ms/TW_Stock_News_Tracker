# TW_Stock_News_Tracker
TW_Stock_News_Tracker
# 台股新聞追蹤（財報/營收/法說/EPS）

目標：每週自動追蹤台股清單的「財報/營收/法說會/EPS」相關新聞，輸出：
- 可直接貼到 NotebookLM 的「URL 文字清單」
- 每檔 3 則新聞的詳細報告
- 追加月營收摘要（單月 + 累計）

TW_Stock_News_Tracker/
├─ README.md
├─ index.md                      # GitHub Pages 首頁（自動更新）
├─ reports/                      # 每次執行產出的報告（自動新增/更新）
│  ├─ 2026-02-11.md
│  └─ 2026-02-18.md
├─ config/
│  └─ tw_stocks.json             # 追蹤股票清單（你維護）
├─ scripts/
│  └─ tw_news_tracker.py         # 主程式（Actions 會跑這支）
└─ .github/
   └─ workflows/
      └─ tw-news-tracker.yml     # 排程與自動 commit

每個檔案在做什麼（README 用）

config/tw_stocks.json：股票清單（證券代號、證券名稱、industry…）

scripts/tw_news_tracker.py：

抓 Google News RSS（7 天內、每檔 3 則、include+exclude）

抓月營收（應該從公開 OpenAPI）

產生 reports/YYYY-MM-DD.md

更新 index.md 指向最新報告

.github/workflows/tw-news-tracker.yml：每週六中午跑，跑完 commit 回 repo

reports/：歷史報告存放處

index.md：Pages 顯示的首頁

## 資料來源
- 新聞：Google News RSS（XML）
- 月營收：TWSE OpenAPI（公開發行公司每月營業收入彙總表）

## 輸出
- `reports/YYYY-MM-DD.md`
- `index.md`（最新報告入口 + 近期報告清單）

報告格式會包含：

- `## 📋 Copy URLs for NotebookLM`：純 URL 文字（方便全選貼上）
- `## 📊 詳細報告`：分股票列出營收摘要與新聞

## 設定
- 股票清單：`config/tw_stocks.json`
- 每檔新聞數：預設 3 則
- 時間範圍：預設 7 天
- include 關鍵字：財報、營收、法說會、EPS
- exclude：技術分析/K線/籌碼…（程式內可調）

## GitHub Actions
排程：每週六（台北 12:00）自動跑一次，也可手動 `Run workflow`。
