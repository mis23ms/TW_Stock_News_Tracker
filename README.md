# TW_Stock_News_Tracker
TW_Stock_News_Tracker
# 台股新聞追蹤（財報/營收/法說/EPS）

目標：每週自動追蹤台股清單的「財報/營收/法說會/EPS」相關新聞，輸出：
- 可直接貼到 NotebookLM 的「URL 文字清單」
- 每檔 3 則新聞的詳細報告
- 追加月營收摘要（單月 + 累計）

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
