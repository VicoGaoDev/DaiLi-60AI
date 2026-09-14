#!/usr/bin/env python3
"""将 docs-api/*.md 构建为可托管的静态站点（输出到 docs-api/docs-api/）。"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs-api"

# 静态站部署子路径，默认 /docs-api。本地根目录预览可设 DOCS_BASE_PATH=
def _read_base_path() -> str:
    raw = os.environ.get("DOCS_BASE_PATH", "/docs-api").strip()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/")


BASE_PATH = _read_base_path()
SRC_FILES = [
    ("index", "README.md", "80AI API 生图接口文档", "GET"),
    ("01-get-generation-models", "01-get-generation-models.md", "查询生图模型列表", "GET"),
    ("02-get-task-scenes", "02-get-task-scenes.md", "查询任务场景配置", "GET"),
    ("03-create-task", "03-create-task.md", "创建同步生图任务", "POST"),
    ("04-async-task", "04-async-task.md", "异步生图任务", "POST"),
]

NAV = [(slug, title, method) for slug, _, title, method in SRC_FILES if slug != "index"]


def page_href(target: str, current: str) -> str:
    """生成页面链接。有 BASE_PATH 时用绝对子路径，避免 /docs-api 无尾斜杠时链到域名根。"""
    if BASE_PATH:
        if target == "index":
            return f"{BASE_PATH}/"
        return f"{BASE_PATH}/{target}/"
    if target == "index":
        return "./" if current == "index" else "../"
    if current == "index":
        return f"{target}/"
    if current == target:
        return "./"
    return f"../{target}/"


def slug_from_link(href: str) -> str | None:
    if href.endswith(".md"):
        return href.replace("./", "").replace(".md", "")
    return None


def inline_md(text: str) -> str:
    text = html.escape(text)
    allowed_tags = ("br", "strong", "em", "ul", "li", "table", "thead", "tbody", "tr", "th", "td")
    for tag in allowed_tags:
        text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        if tag != "br":
            text = text.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )
    return text


def parse_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return ""
    header = rows[0]
    body = rows[2:] if len(rows) > 1 and re.match(r"^:?-+:?$", rows[1][0]) else rows[1:]
    thead = "<thead><tr>" + "".join(f"<th>{inline_md(c)}</th>" for c in header) + "</tr></thead>"
    tbody_rows = []
    for row in body:
        if not any(cell.strip() for cell in row):
            continue
        tbody_rows.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in row) + "</tr>")
    tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
    return f'<div class="table-wrap"><table>{thead}{tbody}</table></div>'


def parse_codeblock(lines: list[str], lang: str) -> str:
    content = html.escape("\n".join(lines))
    lang_class = f' class="language-{lang}"' if lang else ""
    return f'<pre><code{lang_class}>{content}</code></pre>'


def md_to_html(md: str, current_slug: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            close_ul()
            lang = line[3:].strip()
            i += 1
            block: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(parse_codeblock(block, lang))
            i += 1
            continue

        if "|" in line and line.strip().startswith("|"):
            close_ul()
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(parse_table(table_lines))
            continue

        if line.startswith("# "):
            close_ul()
            i += 1
            continue

        if line.startswith("## "):
            close_ul()
            title = line[3:].strip()
            anchor = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-").lower() or "section"
            out.append(f'<h2 id="{anchor}">{inline_md(title)}</h2>')
            i += 1
            continue

        if line.startswith("### "):
            close_ul()
            title = line[4:].strip()
            anchor = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-").lower() or "section"
            out.append(f'<h3 id="{anchor}">{inline_md(title)}</h3>')
            i += 1
            continue

        if line.startswith("> "):
            close_ul()
            out.append(f'<blockquote>{inline_md(line[2:].strip())}</blockquote>')
            i += 1
            continue

        if re.match(r"^[-*] ", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = line[2:].strip()
            item_html = inline_md(item)
            for href_match in re.finditer(r'href="(\./[^"]+\.md)"', item_html):
                old = href_match.group(1)
                target = slug_from_link(old)
                if target:
                    dest = "index" if target == "README" else target
                    item_html = item_html.replace(
                        old, page_href(dest, current_slug), 1
                    )
            if target := re.search(r"\./([^)]+\.md)", item):
                slug = slug_from_link(target.group(0))
                if slug:
                    dest = "index" if slug == "README" else slug
                    item_html = re.sub(
                        r"\./[^)]+\.md",
                        page_href(dest, current_slug),
                        item_html,
                    )
            out.append(f"<li>{item_html}</li>")
            i += 1
            continue

        if not line.strip():
            close_ul()
            i += 1
            continue

        close_ul()
        para = inline_md(line.strip())
        para = re.sub(
            r'<a href="(\./[^"]+\.md)">',
            lambda m: (
                f'<a href="{page_href("index" if (s := slug_from_link(m.group(1))) == "README" else s, current_slug)}">'
                if slug_from_link(m.group(1))
                else m.group(0)
            ),
            para,
        )
        out.append(f"<p>{para}</p>")
        i += 1

    close_ul()
    return "\n".join(out)


def page_shell(
    slug: str, title: str, method: str | None, body_html: str, css: str, js: str
) -> str:
    home_href = page_href("index", slug)
    nav_items = []
    nav_items.append(
        f'<a class="nav-link{" active" if slug == "index" else ""}" href="{page_href("index", slug)}">概览</a>'
    )
    for nav_slug, nav_title, nav_method in NAV:
        active = " active" if slug == nav_slug else ""
        badge = f'<span class="method {nav_method.lower()}">{nav_method}</span>' if nav_method else ""
        nav_items.append(
            f'<a class="nav-link{active}" href="{page_href(nav_slug, slug)}">{badge}<span>{nav_title}</span></a>'
        )

    method_badge = ""
    if method and slug != "index":
        method_badge = f'<span class="page-method {method.lower()}">{method}</span>'

    base_tag = ""
    if BASE_PATH:
        base_tag = f'  <base href="{html.escape(BASE_PATH + "/", quote=True)}" />\n'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
{base_tag}  <title>{html.escape(title)} · 80AI API 文档</title>
  <style>{css}</style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <a class="brand" href="{home_href}">
        <div class="brand-title">80AI API</div>
        <div class="brand-sub">生图开放接口文档</div>
        <div class="brand-base">https://api.80ai.net</div>
      </a>
      <nav class="nav" aria-label="文档导航">{"".join(nav_items)}</nav>
    </aside>
    <main class="content">
      <header class="page-header">
        {method_badge}
        <h3 class="page-title">{html.escape(title)}</h3>
      </header>
      <article class="doc">{body_html}</article>
      <footer class="footer">80AI API</footer>
    </main>
  </div>
  <script>{js}</script>
</body>
</html>
"""


def site_assets() -> tuple[str, str]:
    css = """/* 80AI API docs */
:root {
  --bg: #f6f8fb;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --border: #e5e7eb;
  --accent: #f59e0b;
  --accent-soft: #fff7ed;
  --get: #10b981;
  --post: #3b82f6;
  --code-bg: #0f172a;
  --code-text: #e2e8f0;
  --radius: 12px;
  --shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
}
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 24px 18px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}
a.brand {
  display: block;
  text-decoration: none;
  color: inherit;
  border-radius: 10px;
  margin: -4px -6px 0;
  padding: 4px 6px;
}
a.brand:hover { background: #f3f4f6; }
.brand-title { font-size: 20px; font-weight: 700; }
.brand-sub { color: var(--muted); font-size: 13px; margin-top: 4px; }
.brand-base {
  margin-top: 12px;
  padding: 8px 10px;
  background: var(--accent-soft);
  border: 1px solid #fed7aa;
  border-radius: 8px;
  font-size: 12px;
  word-break: break-all;
}
.nav { display: flex; flex-direction: column; gap: 6px; margin-top: 24px; }
.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  color: var(--text);
  text-decoration: none;
  font-size: 14px;
}
.nav-link:hover { background: #f3f4f6; }
.nav-link.active { background: var(--accent-soft); color: #9a3412; font-weight: 600; }
.method {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 6px;
  color: #fff;
  flex-shrink: 0;
}
.method.get, .page-method.get { background: var(--get); }
.method.post, .page-method.post { background: var(--post); }
.page-method {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 8px;
  color: #fff;
  margin-bottom: 8px;
}
.content {
  flex: 1;
  min-width: 0;
  padding: 32px 40px 48px;
}
.page-title { margin: 0; font-size: 22px; line-height: 1.35; font-weight: 700; }
.doc { max-width: 920px; }
.doc h2 {
  font-size: 20px;
  margin-top: 36px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.doc h3 {
  font-size: 16px;
  font-weight: 600;
  margin-top: 24px;
  margin-bottom: 8px;
  color: var(--text);
}
.doc p { margin: 12px 0; }
.doc ul { padding-left: 22px; }
.doc li { margin: 6px 0; }
.doc blockquote {
  margin: 16px 0;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid var(--accent);
  border-radius: 0 8px 8px 0;
  color: #92400e;
}
.doc code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 6px;
}
.doc strong {
  font-weight: 700;
  color: #111827;
}
.doc table strong {
  font-weight: 700;
  color: #111827;
}
.doc table table {
  width: 100%;
  margin: 8px 0 12px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  table-layout: fixed;
}
.doc table table th,
.doc table table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.doc table table th:first-child,
.doc table table td:first-child {
  width: 220px;
}
.doc table table td:first-child code {
  word-break: break-all;
  white-space: normal;
}
.doc table table th {
  background: #f3f4f6;
  font-weight: 600;
  white-space: nowrap;
}
.doc table table tr:last-child td,
.doc table table tr:last-child th {
  border-bottom: none;
}
.doc table ul {
  margin: 8px 0 0;
  padding-left: 20px;
}
.doc table li {
  margin: 4px 0;
}
.doc pre {
  background: var(--code-bg);
  color: var(--code-text);
  padding: 16px 18px;
  border-radius: var(--radius);
  overflow-x: auto;
  box-shadow: var(--shadow);
  margin: 16px 0;
}
.doc pre code { background: transparent; padding: 0; color: inherit; font-size: 13px; }
.table-wrap { overflow-x: auto; margin: 16px 0; }
.doc table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  font-size: 14px;
}
.doc th, .doc td {
  border-bottom: 1px solid var(--border);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
}
.doc th { background: #f9fafb; font-weight: 600; }
.doc tr:last-child td { border-bottom: none; }
.footer {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 900px) {
  .layout { flex-direction: column; }
  .sidebar {
    width: 100%;
    height: auto;
    position: relative;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .content { padding: 20px 16px 32px; }
}
"""
    js = """document.querySelectorAll('.doc h2, .doc h3').forEach((heading) => {
  if (heading.id) return;
  const text = heading.textContent || '';
  const id = text.trim().toLowerCase().replace(/\\s+/g, '-').replace(/[^\\w\\u4e00-\\u9fff-]/g, '');
  if (id) heading.id = id;
});
"""
    return css, js


def cleanup_legacy_flat_html():
    for path in OUT.glob("*.html"):
        if path.name != "index.html":
            path.unlink()
    for slug, _, _, _ in SRC_FILES:
        if slug == "index":
            continue
        legacy = OUT / f"{slug}.html"
        if legacy.is_file():
            legacy.unlink()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    css, js = site_assets()
    cleanup_legacy_flat_html()
    for slug, filename, title, method in SRC_FILES:
        md_path = ROOT / filename
        md = md_path.read_text(encoding="utf-8")
        if slug == "index":
            md = re.sub(
                r"\./([^)]+\.md)",
                lambda m: (
                    f"{BASE_PATH}/{m.group(1).replace('.md', '')}/"
                    if BASE_PATH
                    else f"./{m.group(1).replace('.md', '')}/"
                ),
                md,
            )
        body = md_to_html(md, slug)
        page_method = None if slug == "index" else method
        html_doc = page_shell(slug, title, page_method, body, css, js)
        if slug == "index":
            out_path = OUT / "index.html"
        else:
            page_dir = OUT / slug
            page_dir.mkdir(parents=True, exist_ok=True)
            out_path = page_dir / "index.html"
        out_path.write_text(html_doc, encoding="utf-8")
        print(f"wrote {out_path}")
    print(f"\n静态站点已生成: {OUT}")
    print(f"部署子路径 BASE_PATH={BASE_PATH or '(相对路径，根目录部署)'}")
    print("样式与脚本已内联到 HTML，无需单独上传 assets/ 目录")
    if BASE_PATH:
        print(f"访问示例: {BASE_PATH}/ 、{BASE_PATH}/03-create-task/")
    else:
        print("访问示例: / 、/01-get-generation-models/ （无需 .html 后缀）")


if __name__ == "__main__":
    main()
