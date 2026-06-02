# Submission — 自我評估報告（Project 2）

老師要求 demo 時繳交一份 **PDF 自我評估報告**,內容須包含用官方測試 prompt /
測試腳本得到的測試結果。本資料夾即為該繳交物。

| 檔案 | 用途 |
|------|------|
| **`Self_Evaluation_Report.pdf`** | **← 要繳交的 PDF**（逐項對照測試須知、全部 PASS） |
| `自我評估報告.md` | PDF 的 Markdown 原稿（要改內容改這份） |
| `自我評估報告.html` | 中間產物（由 .md 產生,可忽略） |
| `build_pdf.py` | 重新產生 PDF 的腳本 |

## 重新產生 PDF

改完 `自我評估報告.md` 後執行:

```bash
.venv\Scripts\python.exe submission\build_pdf.py
```

流程:Markdown →（python-markdown）→ HTML →（Microsoft Edge headless）→ PDF。
用 Edge 列印,直接吃系統的微軟正黑體,中文不會缺字、不需額外裝字型。

> 繳交前記得在報告開頭「組員」欄填上姓名 / 學號,再重跑一次 `build_pdf.py`。
