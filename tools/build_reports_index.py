#!/usr/bin/env python3
"""扫描投资日报 HTML，并生成供纯静态首页读取的索引。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_SUMMARY = "本期日报已归档，点击查看完整内容。"
SUMMARY_HEADINGS = ("核心结论", "核心观点", "摘要", "市场概览")
SKIP_SUMMARY_PREFIXES = ("统计口径", "实际记录区间", "生成文件", "免责声明")


class ReportParseError(ValueError):
    """表示单份日报缺少生成索引所必需的信息。"""


class ParsedDocument:
    """保存后续规则需要的结构化 HTML 内容。"""

    def __init__(self) -> None:
        self.title = ""
        self.meta: dict[str, str] = {}
        self.headings: list[tuple[int, str]] = []
        self.paragraphs: list[str] = []
        self.lists: list[str] = []
        self.tables: list[list[list[str]]] = []
        self.blocks: list[tuple[str, str]] = []
        self.text = ""


def normalize_text(value: str) -> str:
    """合并空白并清理首尾空格，避免格式缩进进入索引。"""

    return re.sub(r"\s+", " ", value).strip()


class ReportHTMLParser(HTMLParser):
    """只提取可见语义块，不执行脚本，也不读取 CSS 文本。"""

    BLOCK_TAGS = {"title", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.document = ParsedDocument()
        self._ignored_depth = 0
        self._active_tag: str | None = None
        self._active_parts: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "meta":
            name = attributes.get("name", "").strip().lower()
            content = normalize_text(attributes.get("content", ""))
            if name and content:
                self.document.meta[name] = content
        if tag in self.BLOCK_TAGS:
            self._active_tag = tag
            self._active_parts = []
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag in self.BLOCK_TAGS and self._active_tag == tag:
            self._store_block(tag, normalize_text("".join(self._active_parts)))
            self._active_tag = None
            self._active_parts = []
        if tag in {"td", "th"} and self._cell_parts is not None and self._row is not None:
            self._row.append(normalize_text("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.document.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._active_tag is not None:
            self._active_parts.append(data)
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def _store_block(self, tag: str, text: str) -> None:
        if not text:
            return
        self.document.blocks.append((tag, text))
        if tag == "title":
            self.document.title = text
        elif tag.startswith("h"):
            self.document.headings.append((int(tag[1]), text))
        elif tag == "p":
            self.document.paragraphs.append(text)
        elif tag == "li":
            self.document.lists.append(text)


def read_html(path: Path) -> str:
    """优先读取 UTF-8；旧文件仅在解码失败时回退到 GB18030。"""

    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("gb18030")


def extract_document(path: Path) -> ParsedDocument:
    parser = ReportHTMLParser()
    parser.feed(read_html(path))
    parser.close()
    parser.document.text = "\n".join(text for tag, text in parser.document.blocks if tag != "title")
    return parser.document


def normalize_date(value: str) -> str | None:
    """从候选文本中识别真实日历日期并返回 ISO 格式。"""

    patterns = (
        r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?!\d)",
        r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        candidate = "-".join((match.group(1), match.group(2).zfill(2), match.group(3).zfill(2)))
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
        except ValueError:
            continue
        return candidate
    return None


def extract_date(document: ParsedDocument, path: Path) -> str:
    candidates = [
        document.meta.get("report:date", ""),
        path.stem,
        document.title,
        *(text for _, text in document.headings[:3]),
        *document.paragraphs[:3],
    ]
    for candidate in candidates:
        parsed = normalize_date(candidate)
        if parsed:
            return parsed
    raise ReportParseError(f"无法识别日期：{path.name}")


def clean_title(value: str, date: str) -> str:
    value = value.replace(date, " ")
    value = re.sub(r"(?<!\d)20\d{6}(?!\d)", " ", value)
    value = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", value)
    return normalize_text(value.strip(" _-|｜—:："))


def extract_title(document: ParsedDocument, path: Path, date: str) -> str:
    candidates = [
        document.meta.get("report:title", ""),
        document.title,
        *(text for level, text in document.headings if level == 1),
        path.stem,
    ]
    for candidate in candidates:
        title = clean_title(candidate, date)
        if title:
            return title
    raise ReportParseError(f"无法识别标题：{path.name}")


def truncate_summary(value: str, limit: int = 180) -> str:
    value = normalize_text(value)
    if len(value) <= limit:
        return value
    excerpt = value[:limit]
    sentence_end = max(excerpt.rfind("。"), excerpt.rfind("；"))
    if sentence_end >= limit // 2:
        return excerpt[: sentence_end + 1]
    return excerpt.rstrip("，、；： ") + "……"


def extract_summary(document: ParsedDocument) -> tuple[str, list[str]]:
    explicit = document.meta.get("report:summary") or document.meta.get("description")
    if explicit:
        return truncate_summary(explicit), []

    for index, (tag, text) in enumerate(document.blocks):
        if not tag.startswith("h") or not any(keyword in text for keyword in SUMMARY_HEADINGS):
            continue
        fragments: list[str] = []
        for next_tag, next_text in document.blocks[index + 1 :]:
            if next_tag.startswith("h"):
                break
            if next_tag in {"p", "li"} and next_text:
                fragments.append(next_text)
            if len("".join(fragments)) >= 180:
                break
        if fragments:
            return truncate_summary(" ".join(fragments)), []

    for paragraph in document.paragraphs:
        if len(paragraph) < 12 or paragraph.startswith(SKIP_SUMMARY_PREFIXES):
            continue
        return truncate_summary(paragraph), []
    return DEFAULT_SUMMARY, ["未识别摘要，已使用默认文字"]


def stable_report_id(date: str, content: bytes) -> str:
    return f"{date.replace('-', '')}-{hashlib.sha256(content).hexdigest()[:10]}"


def parse_report(path: Path, root: Path, entities: dict[str, Any], overrides: dict[str, Any]) -> dict:
    """把单份 HTML 转换为首页索引使用的统一记录。"""

    document = extract_document(path)
    date = extract_date(document, path)
    title = extract_title(document, path, date)
    summary, warnings = extract_summary(document)
    return {
        "id": stable_report_id(date, path.read_bytes()),
        "date": date,
        "year": int(date[:4]),
        "title": title,
        "summary": summary,
        "file": path.relative_to(root).as_posix(),
        "industries": [],
        "tags": [],
        "stocks": [],
        "influencers": [],
        "sources": [],
        "featured": False,
        "metrics": {},
        "_warnings": warnings,
    }
