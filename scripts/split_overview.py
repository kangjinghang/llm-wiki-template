#!/usr/bin/env python3
"""split_overview.py — Split overview.md 关键发现 into topic-specific overview files.

One-time script that:
1. Reads wiki/overview.md
2. Extracts all ### subsections under ## 关键发现
3. Classifies each by title keywords into 8 topic clusters
4. Writes topic overview pages to wiki/overviews/
5. Rewrites overview.md with 专题概览 index replacing 关键发现

Usage:
    python scripts/split_overview.py <wiki-root> [--dry-run]

Exit codes:
    0 — success
    1 — error
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── Topic definitions (ordered by match priority) ──────────────────────

TOPIC_DEFINITIONS = [
    {
        "slug": "可转债",
        "title": "可转债：关键发现",
        "tags": ["可转债", "量化", "策略"],
        "keywords": ["转债", "可转债", "赎回", "转股", "偏债"],
    },
    {
        "slug": "行业轮动与景气度",
        "title": "行业轮动与景气度：关键发现",
        "tags": ["行业轮动", "景气度", "量化", "a股"],
        "keywords": ["行业轮动", "行业配置", "行业多因子", "行业超预期",
                      "行业拥挤", "景气", "板块轮动", "板块配置", "大消费板块"],
    },
    {
        "slug": "资金面与北向资金",
        "title": "资金面与北向资金：关键发现",
        "tags": ["资金面", "北向资金流", "量化"],
        "keywords": ["北向", "资金流", "资金面", "龙虎", "外资", "资金流择时"],
    },
    {
        "slug": "资产配置与组合管理",
        "title": "资产配置与组合管理：关键发现",
        "tags": ["资产配置", "组合管理", "量化"],
        "keywords": ["配置", "组合优化", "风险平价", "固收", "基金", "FOF",
                      "债基", "持仓借鉴", "二次成长"],
    },
    {
        "slug": "宏观择时与风格",
        "title": "宏观择时与风格：关键发现",
        "tags": ["宏观", "择时", "风格轮动", "量化"],
        "keywords": ["宏观", "货币", "经济周期", "通胀", "风格轮动", "大小盘",
                      "波动率"],
    },
    {
        "slug": "另类数据与机器学习",
        "title": "另类数据与机器学习：关键发现",
        "tags": ["另类数据", "机器学习", "量化"],
        "keywords": ["深度学习", "机器学习", "另类", "舆情", "文本", "调研",
                      "NLP", "ML", "新闻", "GPT", "社交媒体", "关注度",
                      "文本情感", "高频交易", "微观结构", "日内", "订单流",
                      "资金扩散", "Semi-Beta", "Log-Signature"],
    },
    {
        "slug": "技术分析与择时",
        "title": "技术分析与择时：关键发现",
        "tags": ["技术面", "择时", "量化"],
        "keywords": ["形态", "通道", "K线", "技术指标", "事件驱动",
                      "十字孕线", "母子线", "三内部", "乌云", "停顿线",
                      "宽基指数", "价量非线性", "AH溢价", "恒生指数"],
    },
    {
        "slug": "因子投资",
        "title": "因子投资：关键发现",
        "tags": ["因子投资", "量化", "a股", "因子"],
        "keywords": ["因子", "动量", "反转", "振幅", "估值", "成长", "价值",
                      "alpha", "Alpha", "聪明钱", "买卖", "选股", "GARP",
                      "ESG", "esg", "盈余", "业绩", "留存", "盈利", "信噪",
                      "昼夜", "拥挤交易", "因子择时", "因子收益", "分域",
                      "企业生命周期", "量价", "Barra", "风险模型", "供应链",
                      "营收相似", "隔夜", "高质量", "金股"],
    },
]

# Fallback topic for unmatched subsections
FALLBACK_TOPIC = "因子投资"


def classify_subsection(title: str) -> str:
    """Classify a subsection title into a topic slug."""
    for topic in TOPIC_DEFINITIONS:
        for kw in topic["keywords"]:
            if kw.lower() in title.lower():
                return topic["slug"]
    return FALLBACK_TOPIC


def parse_overview(content: str) -> dict:
    """Parse overview.md into sections.

    Returns dict with keys:
        preamble: text before ## 核心主题
        core_topics: text of ## 核心主题 section
        findings_sections: list of (title, body) tuples under ## 关键发现
        open_questions: text of ## 开放问题 section
        notes: text of ## Notes section
    """
    parts = {
        "preamble": "",
        "core_topics": "",
        "findings_sections": [],
        "open_questions": "",
        "notes": "",
    }

    # Split by ## headings
    h2_pattern = re.compile(r"^## ", re.MULTILINE)
    positions = [(m.start(), m.group()) for m in h2_pattern.finditer(content)]

    # Add end position
    positions.append((len(content), ""))

    for i, (start, heading_line) in enumerate(positions[:-1]):
        end = positions[i + 1][0]
        section_text = content[start:end]

        first_line = section_text.split("\n", 1)[0].strip()

        if first_line == "## 核心主题":
            parts["core_topics"] = section_text
        elif first_line == "## 关键发现":
            # Parse subsections
            subsections = parse_subsections(section_text)
            parts["findings_sections"] = subsections
        elif first_line in ("## 开放问题", "## Open Questions"):
            parts["open_questions"] = section_text
        elif "Notes" in first_line:
            parts["notes"] = section_text
        else:
            # Preamble or unknown section — treat as preamble if before first ##
            if i == 0 and not content[:start].strip().startswith("##"):
                parts["preamble"] = content[:start] + section_text

    # If preamble wasn't captured (content starts with frontmatter)
    if not parts["preamble"]:
        first_h2 = positions[0][0] if positions else len(content)
        parts["preamble"] = content[:first_h2]

    return parts


def parse_subsections(section_text: str) -> list[tuple[str, str]]:
    """Parse a ## section into list of (### title, body) tuples."""
    subsections = []

    # Find all ### positions within this section
    h3_pattern = re.compile(r"^### ", re.MULTILINE)
    h3_positions = [m.start() for m in h3_pattern.finditer(section_text)]

    if not h3_positions:
        return subsections

    for i, pos in enumerate(h3_positions):
        end = h3_positions[i + 1] if i + 1 < len(h3_positions) else len(section_text)
        sub_text = section_text[pos:end].rstrip()

        # Extract title
        title_line = sub_text.split("\n", 1)[0]
        title = title_line.replace("### ", "").strip()

        subsections.append((title, sub_text))

    return subsections


def build_topic_frontmatter(topic: dict, subsection_count: int) -> str:
    """Build YAML frontmatter for a topic overview page."""
    today = date.today().isoformat()
    tags_str = ", ".join(topic["tags"])
    summary = f"量化投资「{topic['slug']}」方向的关键发现，共 {subsection_count} 个研究摘要。"

    return (
        "---\n"
        f'title: "{topic["title"]}"\n'
        f'title_zh: "{topic["title"]}"\n'
        "type: overview\n"
        f'summary: "{summary}"\n'
        f"tags: [{tags_str}]\n"
        "sources: []\n"
        "origin: agent-compiled\n"
        "status: developing\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        'review_by: ""\n'
        "---\n"
    )


def build_overview_index(topic_counts: dict[str, int]) -> str:
    """Build the 专题概览 index section for overview.md."""
    lines = ["## 专题概览\n"]
    lines.append("以下专题页面收录了各研究方向的关键发现：\n")

    topic_map = {t["slug"]: t for t in TOPIC_DEFINITIONS}
    for topic in TOPIC_DEFINITIONS:
        slug = topic["slug"]
        count = topic_counts.get(slug, 0)
        if count > 0:
            lines.append(f"- [[{slug}|{topic['title']}]] — {count} 篇研究摘要")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split overview.md 关键发现 into topic-specific files."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root).resolve()
    overview_path = wiki_root / "wiki" / "overview.md"

    if not overview_path.exists():
        print(f"ERROR: {overview_path} not found", file=sys.stderr)
        return 1

    content = overview_path.read_text(encoding="utf-8")
    parts = parse_overview(content)

    findings = parts["findings_sections"]
    print(f"Parsed {len(findings)} subsections from ## 关键发现")

    # Classify
    classified: dict[str, list[tuple[str, str]]] = {t["slug"]: [] for t in TOPIC_DEFINITIONS}
    unclassified: list[tuple[str, str]] = []

    for title, body in findings:
        slug = classify_subsection(title)
        if slug in classified:
            classified[slug].append((title, body))
        else:
            unclassified.append((title, body))

    # Report
    topic_counts: dict[str, int] = {}
    for topic in TOPIC_DEFINITIONS:
        slug = topic["slug"]
        count = len(classified[slug])
        topic_counts[slug] = count
        print(f"  {slug}: {count} 小节")

    if unclassified:
        print(f"\n  Unmatched ({len(unclassified)}):")
        for title, _ in unclassified:
            print(f"    - {title}")

    # Write topic files
    overviews_dir = wiki_root / "wiki" / "overviews"
    if not args.dry_run:
        overviews_dir.mkdir(parents=True, exist_ok=True)

    topic_map = {t["slug"]: t for t in TOPIC_DEFINITIONS}
    for topic in TOPIC_DEFINITIONS:
        slug = topic["slug"]
        subsections = classified[slug]
        if not subsections:
            continue

        fm = build_topic_frontmatter(topic, len(subsections))
        body_parts = [f"# {topic['title']}\n"]
        for _, sub_body in subsections:
            body_parts.append(sub_body)
        body_parts.append("")  # trailing newline

        page_content = fm + "\n" + "\n\n".join(body_parts)

        filepath = overviews_dir / f"{slug}-关键发现.md"
        if args.dry_run:
            print(f"  [DRY RUN] Would write: {filepath} ({len(subsections)} subsections)")
        else:
            filepath.write_text(page_content, encoding="utf-8")
            print(f"  Wrote: {filepath} ({len(subsections)} subsections)")

    # Rewrite overview.md
    new_content_parts = [
        parts["preamble"].rstrip(),
        "",
        parts["core_topics"].rstrip(),
        "",
        build_overview_index(topic_counts).rstrip(),
        "",
        parts["open_questions"].rstrip(),
        "",
        parts["notes"].rstrip(),
        "",
    ]
    new_overview = "\n".join(new_content_parts)

    if args.dry_run:
        print(f"\n  [DRY RUN] overview.md would shrink from {content.count(chr(10))+1} to ~{new_overview.count(chr(10))+1} lines")
    else:
        overview_path.write_text(new_overview, encoding="utf-8")
        old_lines = content.count("\n") + 1
        new_lines = new_overview.count("\n") + 1
        print(f"\n  overview.md: {old_lines} → {new_lines} lines")

    print(f"\nTotal subsections distributed: {sum(topic_counts.values())}/{len(findings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
