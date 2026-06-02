"""Build the self-evaluation report PDF from the Markdown source.

Pipeline: Markdown  --(python-markdown)-->  styled HTML  --(Edge headless)-->  PDF.
Edge's --print-to-pdf uses the system fonts, so CJK (Microsoft JhengHei) renders
correctly with no extra font install.

    python submission/build_pdf.py
"""

import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
MD = HERE / "自我評估報告.md"
HTML = HERE / "自我評估報告.html"
PDF = HERE / "Self_Evaluation_Report.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft JhengHei", "Noto Sans CJK TC", "PingFang TC", sans-serif;
  font-size: 11pt; line-height: 1.6; color: #1a1a1a; max-width: 100%;
}
h1 { font-size: 21pt; color: #1a3a5c; border-bottom: 3px solid #1a3a5c;
     padding-bottom: 8px; margin-top: 0; }
h2 { font-size: 15pt; color: #1a3a5c; border-bottom: 1px solid #c5d3e0;
     padding-bottom: 4px; margin-top: 26px; }
h3 { font-size: 12.5pt; color: #2c5777; margin-top: 18px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th, td { border: 1px solid #b8c4d0; padding: 5px 9px; text-align: left;
         vertical-align: top; }
th { background: #e8eef4; color: #1a3a5c; font-weight: 600; }
tr:nth-child(even) td { background: #f6f9fc; }
code { background: #eef1f4; padding: 1px 5px; border-radius: 3px;
       font-family: Consolas, "Courier New", monospace; font-size: 9.5pt; }
pre { background: #2b2b2b; color: #e6e6e6; padding: 12px 14px; border-radius: 6px;
      overflow-x: auto; font-size: 9pt; line-height: 1.45; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { border-left: 4px solid #7aa3c9; background: #f0f5fa; margin: 12px 0;
             padding: 8px 14px; color: #33485c; font-size: 10pt; }
hr { border: none; border-top: 1px solid #d0d8e0; margin: 22px 0; }
strong { color: #15324a; }
"""


def find_edge() -> str:
    for c in EDGE_CANDIDATES:
        if Path(c).exists():
            return c
    sys.exit("[ERROR] 找不到 Microsoft Edge,無法輸出 PDF。")


def main() -> None:
    md_text = MD.read_text(encoding="utf-8")
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    html = (f"<!DOCTYPE html><html lang='zh-Hant'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    HTML.write_text(html, encoding="utf-8")
    print(f"[OK] HTML -> {HTML.name}")

    edge = find_edge()
    if PDF.exists():
        PDF.unlink()
    subprocess.run([
        edge, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={PDF}", HTML.as_uri(),
    ], check=True, timeout=120)

    if PDF.exists() and PDF.stat().st_size > 0:
        print(f"[OK] PDF  -> {PDF.name}  ({PDF.stat().st_size // 1024} KB)")
    else:
        sys.exit("[ERROR] PDF 未產生。")


if __name__ == "__main__":
    main()
