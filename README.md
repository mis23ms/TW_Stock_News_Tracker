# TW_Stock_News_Tracker
TW_Stock_News_Tracker
下面是你可以直接覆蓋/貼進 `README.md` 的版本（已含檔案結構、怎麼跑、排程、Pages 設定、怎麼改股票清單）。

```md
# TW Stock News Tracker（台股新聞追蹤）

追蹤指定台股清單的「財報/營收/法說會/EPS」相關新聞，並輸出：
- **Copy URLs for NotebookLM**（純 URL 文字清單，方便直接貼到 NotebookLM）
- **詳細報告**（依股票分組、每檔 3 則新聞）
- **月營收摘要**（從公開 OpenAPI 取得，若抓不到會在 Actions log 印出原因）

GitHub Actions 會定期執行並自動更新 `reports/` 與 `index.md`，搭配 GitHub Pages 顯示。

---

## 專案檔案結構

```

TW_Stock_News_Tracker/
├─ README.md
├─ index.md                      # GitHub Pages 首頁（自動更新）
├─ reports/                      # 每次執行產出的報告（自動新增/更新）
│  ├─ 2026-02-11.md
│  └─ ...
├─ config/
│  └─ tw_stocks.json             # 追蹤股票清單（你維護）
├─ scripts/
│  └─ tw_news_tracker.py         # 主程式（Actions 會跑這支）
└─ .github/
└─ workflows/
└─ tw-news-tracker.yml     # 排程與自動 commit

````

---

## 追蹤內容

### 新聞來源
- 使用 **Google News RSS**（不需要瀏覽器，適合 GitHub Actions）

### 關鍵字篩選
- include：`財報、營收、法說會、EPS`
- 程式同時支援 include + exclude（讓結果更乾淨）

### 新聞數量與時間範圍
- 每檔股票：**3 則**
- 時間：**近 7 天**

---

## 如何更新股票清單

編輯 `config/tw_stocks.json`  
建議欄位格式（最少要有 `code`、`name`）：

```json
[
  {"industry":"半導體業","code":"2330","name":"台積電"},
  {"industry":"其他電子業","code":"2317","name":"鴻海"}
]
````

---

## 本機手動執行（可選）

> 平常不需要本機跑，Actions 會自動跑。你要測試才用。

```bash
pip install -r requirements.txt
python scripts/tw_news_tracker.py
```

輸出會更新：

* `reports/YYYY-MM-DD.md`
* `index.md`

---

## GitHub Actions 排程

排程設定在：`.github/workflows/tw-news-tracker.yml`

目前：**每週六 12:00（台灣時間）**自動執行，並把更新 commit 回 repo。

---

## GitHub Pages 設定

Settings → Pages

* Source：Deploy from a branch
* Branch：`main`
* Folder：`/(root)`

Pages 站點會顯示 `index.md`（最新報告入口）。

```

```

