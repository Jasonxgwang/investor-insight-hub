#!/usr/bin/env python3
"""扫描投资日报 HTML，并生成供纯静态首页读取的索引。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
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


class ImportResult:
    """汇总本次导入结果，并保留失败时回滚所需的移动记录。"""

    def __init__(self) -> None:
        self.imported: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []
        self.moves: list[tuple[Path, Path]] = []


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
    value = re.sub(r"[（(]\s*[）)]", " ", value)
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


def load_entities(path: Path) -> dict[str, Any]:
    """读取受控实体词典；词典是识别别名和统一标签的维护边界。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ReportParseError(f"实体词典版本无效：{path}")
    return payload


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """读取少量人工校准记录，用于保留历史日报的高质量元数据。"""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("reports"), dict):
        raise ReportParseError(f"日报覆盖文件格式无效：{path}")
    return payload["reports"]


def split_metadata_values(value: str) -> list[str]:
    return [normalize_text(item) for item in re.split(r"[;；,，]", value) if normalize_text(item)]


def append_unique(items: list[Any], value: Any, key) -> None:
    identity = key(value)
    if identity and all(key(existing) != identity for existing in items):
        items.append(value)


def extract_stocks(document: ParsedDocument, entities: dict[str, Any]) -> list[dict[str, str]]:
    """按显式元数据、表格、词典顺序识别股票，不扫描任意六位数字。"""

    stocks: list[dict[str, str]] = []
    for item in re.split(r"[;；]", document.meta.get("report:stocks", "")):
        if not normalize_text(item):
            continue
        name, separator, code = item.partition("|")
        append_unique(
            stocks,
            {"name": normalize_text(name), "code": normalize_text(code) if separator else ""},
            lambda stock: stock["code"] or stock["name"],
        )

    name_headers = {"标的", "股票", "证券", "股票名称", "证券名称"}
    code_headers = {"代码", "股票代码", "证券代码"}
    for table in document.tables:
        if not table:
            continue
        headers = [normalize_text(cell).replace(" ", "") for cell in table[0]]
        name_index = next((index for index, value in enumerate(headers) if value in name_headers), None)
        code_index = next((index for index, value in enumerate(headers) if value in code_headers), None)
        if name_index is None:
            continue
        for row in table[1:]:
            if name_index >= len(row):
                continue
            name = normalize_text(row[name_index])
            code = normalize_text(row[code_index]) if code_index is not None and code_index < len(row) else ""
            if name:
                append_unique(stocks, {"name": name, "code": code}, lambda stock: stock["code"] or stock["name"])

    visible_text = document.text
    for definition in entities.get("stocks", []):
        aliases = [definition.get("name", ""), *definition.get("aliases", [])]
        if any(alias and alias in visible_text for alias in aliases):
            append_unique(
                stocks,
                {"name": definition["name"], "code": definition.get("code", "")},
                lambda stock: stock["code"] or stock["name"],
            )
    return stocks


def extract_influencers(document: ParsedDocument, entities: dict[str, Any]) -> list[str]:
    """把作者别名统一为词典中的规范名称，并保留表格中的新作者。"""

    influencers: list[str] = []
    alias_map: dict[str, str] = {}
    for definition in entities.get("influencers", []):
        for alias in [definition.get("name", ""), *definition.get("aliases", [])]:
            if alias:
                alias_map[alias] = definition["name"]

    def add_author(value: str) -> None:
        value = normalize_text(value)
        if not value:
            return
        canonical = alias_map.get(value, value)
        append_unique(influencers, canonical, lambda item: item)

    for value in split_metadata_values(document.meta.get("report:influencers", "")):
        add_author(value)

    author_headers = {"作者", "大V", "大v", "账号", "博主", "观点人"}
    for table in document.tables:
        if not table:
            continue
        headers = [normalize_text(cell).replace(" ", "") for cell in table[0]]
        author_index = next((index for index, value in enumerate(headers) if value in author_headers), None)
        if author_index is None:
            continue
        for row in table[1:]:
            if author_index >= len(row):
                continue
            cell = normalize_text(row[author_index])
            matched = [alias_map[alias] for alias in alias_map if alias in cell]
            if matched:
                for name in matched:
                    add_author(name)
            else:
                for value in split_metadata_values(cell):
                    add_author(value)

    for definition in entities.get("influencers", []):
        aliases = [definition.get("name", ""), *definition.get("aliases", [])]
        if any(alias and alias in document.text for alias in aliases):
            add_author(definition["name"])
    return influencers


def score_controlled_terms(
    text: str,
    headings: str,
    definitions: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    """只从受控词表返回分类，避免相近词不断制造新标签。"""

    scored: list[tuple[int, int, str]] = []
    for position, definition in enumerate(definitions):
        keywords = [keyword for keyword in definition.get("keywords", []) if keyword]
        score = sum(text.count(keyword) for keyword in keywords)
        score += 2 * sum(headings.count(keyword) for keyword in keywords)
        if score:
            scored.append((-score, position, definition["name"]))
    return [name for _, _, name in sorted(scored)[:limit]]


def extract_controlled_metadata(
    document: ParsedDocument,
    entities: dict[str, Any],
    meta_name: str,
    dictionary_name: str,
    limit: int,
) -> list[str]:
    explicit = split_metadata_values(document.meta.get(meta_name, ""))
    if explicit:
        return explicit[:limit]
    headings = "\n".join(text for _, text in document.headings)
    return score_controlled_terms(document.text, headings, entities.get(dictionary_name, []), limit)


def extract_sources(document: ParsedDocument, entities: dict[str, Any]) -> list[str]:
    return extract_controlled_metadata(document, entities, "report:sources", "sources", 6)


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
        "industries": extract_controlled_metadata(
            document, entities, "report:industries", "industries", 6
        ),
        "tags": extract_controlled_metadata(document, entities, "report:tags", "tags", 8),
        "stocks": extract_stocks(document, entities),
        "influencers": extract_influencers(document, entities),
        "sources": extract_sources(document, entities),
        "featured": False,
        "metrics": {},
        "_warnings": warnings,
    }


def validate_index(payload: dict[str, Any], root: Path) -> None:
    """在写入前验证首页依赖的数据契约和所有归档路径。"""

    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("reports"), list):
        raise ReportParseError("日报索引结构无效")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    required = ("id", "date", "year", "title", "summary", "file")
    reports = payload["reports"]
    for report in reports:
        missing = [field for field in required if report.get(field) in (None, "")]
        if missing:
            raise ReportParseError(f"日报记录缺少字段：{', '.join(missing)}")
        if report["id"] in seen_ids:
            raise ReportParseError(f"日报 ID 重复：{report['id']}")
        seen_ids.add(report["id"])

        normalized_path = str(report["file"]).replace("\\", "/")
        folded_path = normalized_path.casefold()
        if folded_path in seen_paths:
            raise ReportParseError(f"日报路径重复：{normalized_path}")
        seen_paths.add(folded_path)
        if not normalized_path.startswith(f"Reports/{report['year']}/"):
            raise ReportParseError(f"日报路径与年份不一致：{normalized_path}")
        if int(str(report["date"])[:4]) != report["year"]:
            raise ReportParseError(f"日报日期与年份不一致：{normalized_path}")
        if not (root / normalized_path).is_file():
            raise ReportParseError(f"日报文件不存在：{normalized_path}")

        for field in ("industries", "tags", "stocks", "influencers", "sources"):
            if not isinstance(report.get(field), list):
                raise ReportParseError(f"日报字段必须是数组：{normalized_path} -> {field}")

    expected_updated = max((report["date"] for report in reports), default="")
    if payload.get("site", {}).get("updatedAt") != expected_updated:
        raise ReportParseError("站点最近更新日期与日报数据不一致")


def build_index(
    root: Path,
    entities_path: Path,
    overrides_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    """全量重建索引，以自动反映新增、删除、改名和规则升级。"""

    root = root.resolve()
    entities = load_entities(entities_path)
    overrides = load_overrides(overrides_path)
    archive = root / "Reports"
    report_paths = sorted(
        (path for path in archive.rglob("*.html") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    ) if archive.exists() else []

    reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in report_paths:
        relative = path.relative_to(root).as_posix()
        record = parse_report(path, root, entities, overrides)
        warnings.extend(f"{relative}：{message}" for message in record.pop("_warnings", []))
        override = overrides.get(relative, {})
        if not isinstance(override, dict):
            raise ReportParseError(f"日报覆盖记录必须是对象：{relative}")
        record.update(override)
        record["file"] = relative
        record["year"] = int(record["date"][:4])
        reports.append(record)

    reports.sort(
        key=lambda report: (
            -int(report["date"].replace("-", "")),
            report["title"],
            report["file"],
        )
    )
    updated_at = max((report["date"] for report in reports), default="")
    payload = {
        "schemaVersion": 1,
        "site": {
            "name": "Investor Insight Hub 投资观点库",
            "description": "雪球与微博大 V 投资观点日报归档",
            "updatedAt": updated_at,
        },
        "reports": reports,
    }
    validate_index(payload, root)
    return payload, warnings


def serialize_index(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_index_atomic(payload: dict[str, Any], destination: Path) -> None:
    """先写临时文件，再原子替换，避免中途失败破坏可用索引。"""

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(serialize_index(payload), encoding="utf-8", newline="\n")
    temporary.replace(destination)


def import_inbox(root: Path) -> ImportResult:
    """预检并归档 Inbox 中的 HTML；任何冲突都会阻止本批次移动。"""

    root = root.resolve()
    inbox = root / "Inbox"
    result = ImportResult()
    if not inbox.exists():
        return result

    entities = load_entities(root / "data" / "entities.json")
    archive_hashes: set[bytes] = set()
    archive = root / "Reports"
    if archive.exists():
        for archived in archive.rglob("*.html"):
            if archived.is_file():
                archive_hashes.add(hashlib.sha256(archived.read_bytes()).digest())

    planned: list[tuple[Path, Path]] = []
    planned_hashes: set[bytes] = set()
    # 同内容异名时优先保留文件名更短的一份，例如不带“(1)”的原始文件名。
    candidates = sorted(inbox.glob("*.html"), key=lambda path: (len(path.name), path.name.casefold()))
    for source in candidates:
        try:
            content_hash = hashlib.sha256(source.read_bytes()).digest()
            if content_hash in archive_hashes:
                result.skipped.append(f"{source.name}：归档中已存在相同内容")
                continue
            if content_hash in planned_hashes:
                result.skipped.append(f"{source.name}：本批次存在重复内容")
                continue
            record = parse_report(source, root, entities, {})
        except (OSError, UnicodeError, ReportParseError) as error:
            result.failed.append(f"{source.name}：{error}")
            continue
        destination = root / "Reports" / str(record["year"]) / source.name
        if destination.exists():
            if hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(
                destination.read_bytes()
            ).digest():
                result.skipped.append(f"{source.name}：归档中已存在相同文件")
            else:
                result.failed.append(f"{source.name}：目标文件冲突，未覆盖现有归档")
            continue
        planned.append((source, destination))
        planned_hashes.add(content_hash)

    if result.failed:
        return result

    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        result.imported.append(destination.relative_to(root).as_posix())
        result.moves.append((source, destination))
    return result


def rollback_import(result: ImportResult) -> None:
    """索引生成失败时把本批次文件放回 Inbox，保持可重试状态。"""

    for source, destination in reversed(result.moves):
        if destination.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            destination.replace(source)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动生成投资日报静态索引")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="站点项目根目录")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="验证后写入 reports.json")
    mode.add_argument("--check", action="store_true", help="检查 reports.json 是否为最新")
    parser.add_argument(
        "--import-inbox",
        action="store_true",
        help="先把 Inbox 中通过预检的 HTML 归档到年份目录",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    root = args.root.resolve()
    import_result = ImportResult()
    try:
        if args.import_inbox:
            if not args.write:
                raise ReportParseError("--import-inbox 必须与 --write 一起使用")
            import_result = import_inbox(root)
            if import_result.failed:
                for failure in import_result.failed:
                    print(f"导入失败：{failure}", file=sys.stderr)
                return 1
        payload, warnings = build_index(
            root,
            root / "data" / "entities.json",
            root / "data" / "report-overrides.json",
        )
        serialized = serialize_index(payload)
        destination = root / "reports.json"
        if args.check:
            current = destination.read_text(encoding="utf-8") if destination.exists() else ""
            if current != serialized:
                print("reports.json 不是最新状态，请运行 --write。", file=sys.stderr)
                return 1
            print(f"索引检查通过：{len(payload['reports'])} 份日报。")
        else:
            write_index_atomic(payload, destination)
            print(f"索引已更新：{len(payload['reports'])} 份日报。")
        for warning in warnings:
            print(f"警告：{warning}", file=sys.stderr)
        if args.import_inbox:
            print(
                f"Inbox 处理完成：导入 {len(import_result.imported)} 份，"
                f"跳过 {len(import_result.skipped)} 份。"
            )
            for message in import_result.skipped:
                print(f"跳过：{message}", file=sys.stderr)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        rollback_import(import_result)
        print(f"索引生成失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
