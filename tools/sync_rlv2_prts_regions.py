#!/usr/bin/env python3
"""Sync fixed-revision PRTS region metadata into the offline RLV2 rules."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "data" / "rlv2" / "rules"
ZONE_ROUTES_PATH = RULES_DIR / "zone_routes.json"
ZONES_PATH = RULES_DIR / "zones.json"
STAGES_PATH = RULES_DIR / "stages.json"
MANIFEST_PATH = RULES_DIR / "manifest.json"
API_URL = "https://prts.wiki/api.php"
CLIENT_SOURCE_REF = "client:roguelike-topic-table:634e7e7"
USER_AGENT = "OpenDoctoratePy-rule-research/1.0"


@dataclass(frozen=True)
class Source:
    theme: str
    page_title: str
    revision: int
    sha1: str
    core_zone_count: int

    @property
    def source_ref(self) -> str:
        return f"prts:{self.theme.replace('_', '-')}:{self.revision}"


SOURCES = (
    Source(
        "rogue_1",
        "\u5080\u5f71\u4e0e\u7329\u7ea2\u5b64\u94bb",
        408420,
        "b602537278585d7040c4c526fe25ad4e8145c64f",
        6,
    ),
    Source(
        "rogue_2",
        "\u6c34\u6708\u4e0e\u6df1\u84dd\u4e4b\u6811",
        408421,
        "ccd182ace56c5800f4293801f97f663aca7b3d9d",
        7,
    ),
    Source(
        "rogue_3",
        "\u63a2\u7d22\u8005\u7684\u94f6\u51c7\u6b62\u5883",
        408422,
        "851ae40d3aed08731e74c6b08ae209f424cee113",
        7,
    ),
    Source(
        "rogue_4",
        "\u8428\u5361\u5179\u7684\u65e0\u7ec8\u5947\u8bed",
        408423,
        "ca39b2ac37db1afbc6f834dfaa6e82ca0e207179",
        8,
    ),
    Source(
        "rogue_5",
        "\u5c81\u7684\u754c\u56ed\u5fd7\u5f02",
        408424,
        "519659b991f4ce965ebad7837a1ae938f37c693f",
        8,
    ),
)

REGION_HEADING = re.compile(r"^==\s*\u533a\u57df\s*==\s*$", re.MULTILINE)
NEXT_HEADING = re.compile(r"^==[^=\n].*?==\s*$", re.MULTILINE)
ENTRY_HEADING = re.compile(
    r"'''\u8fdb\u5165\u65b9\u5f0f'''\s*(?:<br\s*/?>)?", re.IGNORECASE
)
LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
LAYOUT_HEADER = re.compile(
    r"(?:\u57fa\u7840)?\u8282\u70b9\u957f\u5ea6[\uff1a:]\s*"
    r"(?P<length>[^\s\u3000<]+)[\s\u3000]+"
    r"\u6700\u5927\u5206\u652f\u6570[\uff1a:]\s*"
    r"(?P<branches>[^\s\u3000<]+)\s*<br\s*/?>\s*"
    r"(?:\u53ef\u80fd\u7684)?\u8282\u70b9\u6392\u5e03[\uff1a:]\s*<br\s*/?>\s*"
    r"(?P<layout>.*?)(?=\n\s*(?:</div>|\{\{ISArea/end))",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class TitleBlock:
    start: int
    end: int
    title: str


@dataclass(frozen=True)
class ParsedLayout:
    node_length_text: str
    base_node_length: int | None
    maximum_branches_text: str
    maximum_branches: int | None
    source_layout_text: str


def _fetch_source(source: Source) -> str:
    query = urlencode(
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "revids": str(source.revision),
            "prop": "revisions",
            "rvprop": "ids|timestamp|sha1|content",
            "rvslots": "main",
        }
    )
    request = Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    try:
        page = payload["query"]["pages"][0]
        revision = page["revisions"][0]
        slot = revision["slots"]["main"]
        content = slot.get("content", slot.get("*"))
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Invalid MediaWiki response for {source.source_ref}") from exc

    if page["title"] != source.page_title:
        raise RuntimeError(
            f"Page title mismatch for {source.source_ref}: {page['title']!r}"
        )
    if revision["revid"] != source.revision or revision["sha1"] != source.sha1:
        raise RuntimeError(f"Revision identity mismatch for {source.source_ref}")
    if not isinstance(content, str):
        raise RuntimeError(f"Missing wikitext for {source.source_ref}")
    return content


def _matching_template(text: str, start: int) -> str:
    depth = 0
    index = start
    while index < len(text) - 1:
        pair = text[index : index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            continue
        if pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return text[start + 2 : index - 2]
            continue
        index += 1
    raise ValueError(f"Unclosed template at offset {start}")


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    template_depth = 0
    link_depth = 0
    index = 0
    while index < len(value) - 1:
        pair = value[index : index + 2]
        if pair == "{{":
            template_depth += 1
            index += 2
            continue
        if pair == "}}":
            template_depth -= 1
            index += 2
            continue
        if pair == "[[":
            link_depth += 1
            index += 2
            continue
        if pair == "]]":
            link_depth -= 1
            index += 2
            continue
        if value[index] == "|" and template_depth == 0 and link_depth == 0:
            parts.append(value[start:index])
            start = index + 1
        index += 1
    parts.append(value[start:])
    return parts


def _region_section(wikitext: str, source: Source) -> str:
    heading = REGION_HEADING.search(wikitext)
    if heading is None:
        raise ValueError(f"Missing region section in {source.source_ref}")
    remainder = wikitext[heading.end() :]
    next_heading = NEXT_HEADING.search(remainder)
    if next_heading is None:
        raise ValueError(f"Unclosed region section in {source.source_ref}")
    return remainder[: next_heading.start()]


def _title_blocks(section: str, source: Source) -> list[TitleBlock]:
    marker = "{{AKCollapse/title|"
    blocks: list[TitleBlock] = []
    cursor = 0
    while True:
        start = section.find(marker, cursor)
        if start < 0:
            break
        template = _matching_template(section, start)
        arguments = _split_top_level(template)
        if len(arguments) < 2 or arguments[0].strip() != "AKCollapse/title":
            raise ValueError(f"Unexpected title template in {source.source_ref}")
        blocks.append(
            TitleBlock(
                start=start,
                end=start + len(template) + 4,
                title=arguments[1].strip(),
            )
        )
        cursor = blocks[-1].end
    if not blocks:
        raise ValueError(f"No region title blocks in {source.source_ref}")
    return blocks


def _clean_source_text(value: str) -> str:
    value = HTML_COMMENT.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    value = LINE_BREAK.sub("\n", value)
    lines = [line.rstrip() for line in value.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    normalized: list[str] = []
    for line in lines:
        if not line.strip() and normalized and not normalized[-1].strip():
            continue
        normalized.append(line)
    return "\n".join(normalized)


def _integer_prefix(value: str) -> int | None:
    match = re.match(r"\d+", value)
    return int(match.group()) if match else None


def _parse_linear_layout(content: str) -> ParsedLayout | None:
    match = LAYOUT_HEADER.search(content)
    if match is None:
        return None
    length_text = match.group("length").strip()
    branches_text = match.group("branches").strip()
    return ParsedLayout(
        node_length_text=length_text,
        base_node_length=_integer_prefix(length_text),
        maximum_branches_text=branches_text,
        maximum_branches=_integer_prefix(branches_text),
        source_layout_text=_clean_source_text(match.group("layout")),
    )


def _block_content(section: str, blocks: list[TitleBlock], index: int) -> str:
    end = blocks[index + 1].start if index + 1 < len(blocks) else len(section)
    return section[blocks[index].end : end]


def _collapse_content(section: str, start: int) -> str | None:
    opening = re.match(
        r"\s*<div\s+class=[\"']AKCollapse-content[\"'][^>]*>",
        section[start:],
        re.IGNORECASE,
    )
    if opening is None:
        return None
    content_start = start + opening.end()
    tag_pattern = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
    depth = 1
    for tag in tag_pattern.finditer(section, content_start):
        if tag.group().lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return section[content_start : tag.start()]
        else:
            depth += 1
    raise ValueError(f"Unclosed AKCollapse content at offset {start}")


def _source_text_record(review_status: str, source_refs: list[str], notes: str) -> dict[str, Any]:
    return {
        "reviewStatus": review_status,
        "sourceRefs": source_refs,
        "notes": notes,
    }


def _area_layout_record(
    source: Source,
    zone_id: str,
    zone: dict[str, Any],
    layout: ParsedLayout,
    excluded_zone_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": f"{source.theme}:{zone_id}",
        "theme": source.theme,
        "zoneId": zone_id,
        "name": zone["name"],
        "nodeLengthText": layout.node_length_text,
        "baseNodeLength": layout.base_node_length,
        "maximumBranches": layout.maximum_branches,
        "sourceLayoutText": layout.source_layout_text,
        "identityResolution": {
            "method": "explicit_core_zone_id_and_title",
            "excludedCandidateZoneIds": excluded_zone_ids,
        },
        "fieldEvidence": {
            "clientIdentity": _source_text_record(
                "client_verified",
                [CLIENT_SOURCE_REF],
                "zoneId and name come from the fixed client topic table.",
            ),
            "layoutSummary": _source_text_record(
                "public_sourced",
                [source.source_ref],
                "Node length, maximum branches, and layout text come from "
                "the fixed PRTS region section.",
            ),
        },
        "evidence": _source_text_record(
            "public_sourced",
            [CLIENT_SOURCE_REF, source.source_ref],
            "The client identity and fixed PRTS layout summary are cross-checked; "
            "detailed graph edges are not encoded.",
        ),
        "implementationStatus": "document_only",
        "runtimeEnabled": False,
    }


def _core_layouts(
    source: Source,
    section: str,
    blocks: list[TitleBlock],
    client_zones: dict[str, Any],
    catalog_zones: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, TitleBlock]]:
    records: list[dict[str, Any]] = []
    core_blocks: dict[str, TitleBlock] = {}
    block_indexes = {block.start: index for index, block in enumerate(blocks)}

    for zone_number in range(1, source.core_zone_count + 1):
        zone_id = f"zone_{zone_number}"
        client_zone = client_zones.get(zone_id)
        catalog_zone = catalog_zones.get(zone_id)
        if client_zone is None or catalog_zone is None:
            raise ValueError(f"Missing client core zone {source.theme}:{zone_id}")
        if client_zone["name"] != catalog_zone["name"]:
            raise ValueError(f"Zone catalog mismatch for {source.theme}:{zone_id}")

        candidates: list[tuple[TitleBlock, ParsedLayout]] = []
        for block in blocks:
            if client_zone["name"] not in block.title:
                continue
            index = block_indexes[block.start]
            layout = _parse_linear_layout(_block_content(section, blocks, index))
            if layout is not None and layout.base_node_length is not None:
                candidates.append((block, layout))
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one core layout for {source.theme}:{zone_id}, got {len(candidates)}"
            )

        block, layout = candidates[0]
        if layout.maximum_branches is None or not layout.source_layout_text:
            raise ValueError(f"Incomplete core layout for {source.theme}:{zone_id}")
        same_name_ids = sorted(
            candidate_id
            for candidate_id, candidate in client_zones.items()
            if candidate["name"] == client_zone["name"] and candidate_id != zone_id
        )
        records.append(
            _area_layout_record(
                source, zone_id, client_zone, layout, same_name_ids
            )
        )
        core_blocks[zone_id] = block

    positions = [
        core_blocks[f"zone_{number}"].start
        for number in range(1, source.core_zone_count + 1)
    ]
    if positions != sorted(positions):
        raise ValueError(f"Core zones are out of order in {source.source_ref}")
    return records, core_blocks


def _templates_named(value: str, name: str) -> list[str]:
    marker = "{{" + name
    templates: list[str] = []
    cursor = 0
    while True:
        start = value.find(marker, cursor)
        if start < 0:
            break
        template = _matching_template(value, start)
        if _split_top_level(template)[0].strip() == name:
            templates.append(template)
        cursor = start + len(template) + 4
    return templates


def _trim_entry_text(value: str) -> str:
    value = _clean_source_text(value)
    lines = value.splitlines()
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        if re.fullmatch(r"(?:</div>\s*)+", tail, re.IGNORECASE):
            lines.pop()
            continue
        if re.fullmatch(r"<hr\b[^>]*>", tail, re.IGNORECASE):
            lines.pop()
            continue
        if re.fullmatch(
            r"<div\s+class=[\"']area_divider[\"'][^>]*>.*?</div>",
            tail,
            re.IGNORECASE,
        ):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _entry_text(content: str) -> str | None:
    marker = ENTRY_HEADING.search(content)
    if marker is None:
        return None
    value = _trim_entry_text(content[marker.end() :])
    if not value:
        raise ValueError("Empty PRTS entry text")
    return value


def _ending_route_record(
    source: Source,
    ending: dict[str, Any],
    terminal_zone_id: str,
    entry_text: str | None,
    boss_stage_ids: list[str] | None,
) -> dict[str, Any]:
    boss_icon_id = ending["bossIconId"]
    boss_note = (
        "Derived from client ending.bossIconId == stage.specialNodeId."
        if boss_icon_id is not None
        else "The client ending has no bossIconId, so no stage is inferred."
    )
    entry_note = (
        "Verbatim wikitext below the fixed PRTS entry heading, with comments "
        "and structural wrappers removed."
        if entry_text is not None
        else "The fixed PRTS ending card has no explicit entry heading; the value remains null."
    )
    return {
        "id": f"{source.theme}:{ending['id']}",
        "theme": source.theme,
        "endingId": ending["id"],
        "endingName": ending["name"],
        "terminalZoneId": terminal_zone_id,
        "entryConditionText": entry_text,
        "entryConditionAst": None,
        "bossIconId": boss_icon_id,
        "bossStageIds": boss_stage_ids,
        "identityResolution": {
            "terminalZoneMethod": "prts_ending_card_under_core_area",
            "bossStageMethod": (
                "client_boss_icon_equals_stage_special_node"
                if boss_icon_id is not None
                else None
            ),
        },
        "fieldEvidence": {
            "endingIdentity": _source_text_record(
                "client_verified",
                [CLIENT_SOURCE_REF],
                "endingId, endingName, and bossIconId come from the fixed client topic table.",
            ),
            "terminalZoneAndEntryText": _source_text_record(
                "public_sourced", [source.source_ref], entry_note
            ),
            "bossStageIds": _source_text_record(
                "client_verified", [CLIENT_SOURCE_REF], boss_note
            ),
        },
        "evidence": _source_text_record(
            "public_sourced",
            [CLIENT_SOURCE_REF, source.source_ref],
            "Ending placement is public-sourced; ending and stage identities are client-verified.",
        ),
        "implementationStatus": "document_only",
        "runtimeEnabled": False,
    }


def _ending_routes(
    source: Source,
    section: str,
    blocks: list[TitleBlock],
    core_blocks: dict[str, TitleBlock],
    client_detail: dict[str, Any],
    catalog_stages: dict[str, Any],
) -> list[dict[str, Any]]:
    endings = client_detail["endings"]
    client_stages = client_detail["stages"]
    expected_ending_ids = set(endings)
    if source.theme == "rogue_3":
        expected_ending_ids.remove("ro3_ending_c")

    core_positions = sorted(
        ((block.start, zone_id) for zone_id, block in core_blocks.items())
    )
    routes: dict[str, dict[str, Any]] = {}

    for position_index, (zone_start, zone_id) in enumerate(core_positions):
        zone_end = (
            core_positions[position_index + 1][0]
            if position_index + 1 < len(core_positions)
            else len(section)
        )
        for block in blocks:
            if block.start <= zone_start or block.start >= zone_end:
                continue
            content = _collapse_content(section, block.end)
            if content is None:
                continue
            cards = _templates_named(content, "ISArea/end")
            for card in cards:
                matching_endings = [
                    ending
                    for ending in endings.values()
                    if ending["name"] in card
                ]
                if not matching_endings:
                    continue
                if len(matching_endings) != 1:
                    raise ValueError(
                        f"Ambiguous ending card under {source.theme}:{zone_id}"
                    )
                ending = matching_endings[0]
                ending_id = ending["id"]
                if ending_id not in expected_ending_ids:
                    continue
                if ending_id in routes:
                    raise ValueError(f"Duplicate PRTS ending placement for {ending_id}")

                boss_icon_id = ending["bossIconId"]
                boss_stage_ids: list[str] | None = None
                if boss_icon_id is not None:
                    boss_stage_ids = sorted(
                        stage["id"]
                        for stage in client_stages.values()
                        if stage.get("specialNodeId") == boss_icon_id
                    )
                    if not boss_stage_ids:
                        raise ValueError(f"No boss stage matches {source.theme}:{ending_id}")
                    if any(stage_id not in catalog_stages for stage_id in boss_stage_ids):
                        raise ValueError(f"Boss stage catalog mismatch for {ending_id}")

                routes[ending_id] = _ending_route_record(
                    source,
                    ending,
                    zone_id,
                    _entry_text(content),
                    boss_stage_ids,
                )

    if set(routes) != expected_ending_ids:
        missing = sorted(expected_ending_ids - set(routes))
        extra = sorted(set(routes) - expected_ending_ids)
        raise ValueError(
            f"Ending placement mismatch for {source.theme}: missing={missing}, extra={extra}"
        )
    return sorted(routes.values(), key=lambda record: endings[record["endingId"]]["priority"])


def _fallback_layout_text(content: str) -> str | None:
    layout = re.search(
        r"\*?\s*\u8282\u70b9\u6392\u5e03[\uff1a:]\s*(.*?)"
        r"(?=\n\s*(?:\*|\{\{ISArea/end|</div>))",
        content,
        re.DOTALL,
    )
    if layout is not None:
        return _clean_source_text(layout.group(1))
    grid = re.search(
        r"(\u8282\u70b9\u8303\u56f4[\uff1a:].*?)(?=\n\s*</div>)",
        content,
        re.DOTALL,
    )
    return _clean_source_text(grid.group(1)) if grid is not None else None


def _quarantine_record(
    *,
    record_id: str,
    kind: str,
    source: Source,
    source_name: str,
    ending_id: str | None,
    candidate_zone_ids: list[str] | None,
    candidate_stage_ids: list[str] | None,
    layout: ParsedLayout | None,
    fallback_layout_text: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": kind,
        "theme": source.theme,
        "endingId": ending_id,
        "sourceName": source_name,
        "candidateZoneIds": candidate_zone_ids,
        "candidateStageIds": candidate_stage_ids,
        "sourceNodeLengthText": (
            layout.node_length_text if layout is not None else None
        ),
        "sourceMaximumBranchesText": (
            layout.maximum_branches_text if layout is not None else None
        ),
        "sourceLayoutText": (
            layout.source_layout_text if layout is not None else fallback_layout_text
        ),
        "reason": reason,
        "evidence": _source_text_record(
            "needs_review",
            [CLIENT_SOURCE_REF, source.source_ref],
            "The source record is retained without selecting an unsupported "
            "canonical route or layout.",
        ),
        "implementationStatus": "unsupported",
        "runtimeEnabled": False,
    }


def _area_quarantine(
    source: Source,
    section: str,
    blocks: list[TitleBlock],
    client_zones: dict[str, Any],
    catalog_zones: dict[str, Any],
) -> list[dict[str, Any]]:
    specs: dict[str, list[tuple[str, str, set[str], str]]] = {
        "rogue_3": [
            (
                "rogue_3:prts-area:deep-buried-maze",
                "\u6df1\u57cb\u8ff7\u5883",
                set(),
                "The fixed page lists nine layouts, while 330 same-name client "
                "zones encode variants not resolved by the page summary.",
            )
        ],
        "rogue_4": [
            (
                "rogue_4:prts-area:bizarre-chapter",
                "\u8be1\u8c32\u65ad\u7ae0",
                set(),
                "The fixed page contains general and event-specific variants, "
                "while twelve same-name client zones are not individually identified.",
            ),
            (
                "rogue_4:prts-area:no-end-rest-extra",
                "\u65e0\u7ec8\u5b89\u606f",
                {"zone_8"},
                "The extra failure layout shares a title with the core ending zone "
                "and has no linear length/branch summary.",
            ),
        ],
        "rogue_5": [
            (
                "rogue_5:prts-area:past-present-realm",
                "\u4eca\u6614\u5883",
                set(),
                "This is a 5x5 planar area, outside the linear area-layout record shape.",
            ),
            (
                "rogue_5:prts-area:right-wrong-realm",
                "\u662f\u975e\u5883",
                set(),
                "This is a 5x7 planar area with two same-name client zone IDs, "
                "outside the linear area-layout record shape.",
            ),
        ],
    }
    records: list[dict[str, Any]] = []
    block_indexes = {block.start: index for index, block in enumerate(blocks)}
    for record_id, source_name, excluded_ids, reason in specs.get(source.theme, []):
        matching: list[tuple[TitleBlock, str, ParsedLayout | None]] = []
        for block in blocks:
            if source_name not in block.title:
                continue
            content = _block_content(section, blocks, block_indexes[block.start])
            layout = _parse_linear_layout(content)
            matching.append((block, content, layout))

        if record_id.endswith("no-end-rest-extra"):
            matching = [item for item in matching if item[2] is None]
        elif source.theme == "rogue_4" and source_name == "\u8be1\u8c32\u65ad\u7ae0":
            matching = [item for item in matching if item[2] is not None]
        if len(matching) != 1:
            raise ValueError(
                f"Expected one quarantine source block for {record_id}, got {len(matching)}"
            )

        _, content, layout = matching[0]
        candidate_zone_ids = sorted(
            zone_id
            for zone_id, zone in client_zones.items()
            if zone["name"] == source_name and zone_id not in excluded_ids
        )
        if not candidate_zone_ids:
            raise ValueError(f"No client zone candidates for {record_id}")
        if any(
            zone_id not in catalog_zones
            or catalog_zones[zone_id]["name"] != source_name
            for zone_id in candidate_zone_ids
        ):
            raise ValueError(f"Quarantine zone catalog mismatch for {record_id}")
        records.append(
            _quarantine_record(
                record_id=record_id,
                kind="area_layout",
                source=source,
                source_name=source_name,
                ending_id=None,
                candidate_zone_ids=candidate_zone_ids,
                candidate_stage_ids=None,
                layout=layout,
                fallback_layout_text=_fallback_layout_text(content),
                reason=reason,
            )
        )
    return records


def _ending_quarantine(
    source: Source,
    client_detail: dict[str, Any],
    catalog_stages: dict[str, Any],
) -> list[dict[str, Any]]:
    if source.theme != "rogue_3":
        return []
    ending = client_detail["endings"]["ro3_ending_c"]
    candidate_stage_ids = sorted(
        stage["id"]
        for stage in client_detail["stages"].values()
        if stage.get("specialNodeId") == ending["bossIconId"]
    )
    if any(stage_id not in catalog_stages for stage_id in candidate_stage_ids):
        raise ValueError("Ending quarantine stage catalog mismatch")
    return [
        _quarantine_record(
            record_id="rogue_3:ro3_ending_c",
            kind="ending_route",
            source=source,
            source_name=ending["name"],
            ending_id=ending["id"],
            candidate_zone_ids=None,
            candidate_stage_ids=candidate_stage_ids,
            layout=None,
            fallback_layout_text=None,
            reason=(
                "The client ending is absent from the fixed PRTS region section; "
                "its shared boss icon does not establish a terminal zone."
            ),
        )
    ]


def _enrich_ending_zones(
    ending_zones: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = deepcopy(ending_zones)
    for zone in result:
        matches = [
            route
            for route in routes
            if route["theme"] == zone["theme"]
            and route["terminalZoneId"] == zone["zoneId"]
        ]
        if not matches:
            continue
        source_ref = next(
            source.source_ref for source in SOURCES if source.theme == zone["theme"]
        )
        zone["routeRole"] = "terminal"
        zone["endingIds"] = [route["endingId"] for route in matches]
        zone["bossStageIds"] = sorted(
            {
                stage_id
                for route in matches
                for stage_id in (route["bossStageIds"] or [])
            }
        )
        zone["fieldEvidence"]["routeFields"] = _source_text_record(
            "public_sourced",
            [CLIENT_SOURCE_REF, source_ref],
            "routeRole, endingIds, and bossStageIds are aggregated from generated "
            "per-ending routes.",
        )
        existing_refs = zone["evidence"]["sourceRefs"]
        zone["evidence"] = _source_text_record(
            "public_sourced",
            list(dict.fromkeys([*existing_refs, source_ref])),
            "Client fields, user-confirmed reward tier, and fixed-revision route "
            "facts are tracked separately in fieldEvidence.",
        )
    return result


def _unresolved(source_refs: list[str], quarantine_count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": "ending-route-semantics",
            "fields": [
                "orderedZones",
                "entryConditionAst",
                "eventReplacements",
                "settleSequence",
            ],
            "description": (
                "Terminal zones and 20 explicit entry texts are synchronized, but "
                "natural-language conditions and settlement effects are not "
                "executable rules."
            ),
            "evidence": _source_text_record(
                "needs_review",
                source_refs,
                "Two base ending cards have no explicit entry heading; all routes "
                "remain runtime-disabled.",
            ),
            "implementationStatus": "pending",
            "runtimeEnabled": False,
        },
        {
            "id": "area-layout-structure",
            "fields": ["columns", "nodeTypes", "connections", "guarantees"],
            "description": (
                "Core node lengths, maximum branches, and source summaries are "
                "fixed, but prose is not converted into generator graph constraints."
            ),
            "evidence": _source_text_record(
                "needs_review",
                source_refs,
                "Source layout text is retained verbatim enough for review; no "
                "approximate graph is activated.",
            ),
            "implementationStatus": "pending",
            "runtimeEnabled": False,
        },
        {
            "id": "special-area-layout-identity",
            "fields": ["candidateZoneIds", "variantLayouts", "planarLayouts"],
            "description": (
                f"{quarantine_count - 1} special-area source records remain "
                "quarantined from linear core layouts."
            ),
            "evidence": _source_text_record(
                "needs_review",
                source_refs,
                "Ambiguous client variants and planar layouts require separate models.",
            ),
            "implementationStatus": "unsupported",
            "runtimeEnabled": False,
        },
    ]


def _validate_manifest_sources() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_sources = {source["id"]: source for source in manifest["sources"]}
    for source in SOURCES:
        record = manifest_sources.get(source.source_ref)
        expected_locator = (
            f"https://prts.wiki/w/Special:PermanentLink/{source.revision}"
        )
        if record is None:
            raise ValueError(f"Manifest is missing {source.source_ref}")
        if record["revision"] != str(source.revision):
            raise ValueError(f"Manifest revision mismatch for {source.source_ref}")
        if record["locator"] != expected_locator:
            raise ValueError(f"Manifest locator mismatch for {source.source_ref}")


def _load_topic_table() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    table_metadata = manifest["gameData"]["table"]
    table_path = ROOT / table_metadata["path"]
    raw_table = table_path.read_bytes()
    canonical_table = raw_table.replace(b"\r\n", b"\n")
    if hashlib.sha256(canonical_table).hexdigest() != table_metadata["sha256"]:
        raise ValueError("Client topic table SHA-256 does not match the manifest")
    return json.loads(raw_table)


def build_document() -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    _validate_manifest_sources()
    topic_table = _load_topic_table()
    zone_catalog = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
    stage_catalog = json.loads(STAGES_PATH.read_text(encoding="utf-8"))
    existing = json.loads(ZONE_ROUTES_PATH.read_text(encoding="utf-8"))
    area_layouts: list[dict[str, Any]] = []
    ending_routes: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    summary: dict[str, dict[str, int]] = {}

    for source in SOURCES:
        client_detail = topic_table["details"][source.theme]
        section = _region_section(_fetch_source(source), source)
        blocks = _title_blocks(section, source)
        theme_layouts, core_blocks = _core_layouts(
            source,
            section,
            blocks,
            client_detail["zones"],
            zone_catalog["themes"][source.theme]["zones"],
        )
        theme_routes = _ending_routes(
            source,
            section,
            blocks,
            core_blocks,
            client_detail,
            stage_catalog["themes"][source.theme]["stages"],
        )
        theme_quarantine = [
            *_ending_quarantine(
                source,
                client_detail,
                stage_catalog["themes"][source.theme]["stages"],
            ),
            *_area_quarantine(
                source,
                section,
                blocks,
                client_detail["zones"],
                zone_catalog["themes"][source.theme]["zones"],
            ),
        ]
        area_layouts.extend(theme_layouts)
        ending_routes.extend(theme_routes)
        quarantine.extend(theme_quarantine)
        summary[source.theme] = {
            "areaLayouts": len(theme_layouts),
            "endingRoutes": len(theme_routes),
            "explicitEntryTexts": sum(
                route["entryConditionText"] is not None for route in theme_routes
            ),
            "quarantine": len(theme_quarantine),
        }

    if len(area_layouts) != 36 or len(ending_routes) != 22:
        raise ValueError("Unexpected core area or ending route count")
    if sum(item["explicitEntryTexts"] for item in summary.values()) != 20:
        raise ValueError("Unexpected explicit entry text count")
    if len(quarantine) != 6:
        raise ValueError("Unexpected region quarantine count")

    source_refs = [source.source_ref for source in SOURCES]
    result = {
        "$schema": existing["$schema"],
        "kind": existing["kind"],
        "schemaVersion": existing["schemaVersion"],
        "runtimeEnabled": existing["runtimeEnabled"],
        "sourceRefs": source_refs,
        "stageRewardPolicy": existing["stageRewardPolicy"],
        "areaLayouts": area_layouts,
        "endingRoutes": ending_routes,
        "endingZones": _enrich_ending_zones(
            existing["endingZones"], ending_routes
        ),
        "specialRegions": existing["specialRegions"],
        "flagVariantMapping": existing["flagVariantMapping"],
        "quarantine": quarantine,
        "unresolved": _unresolved(source_refs, len(quarantine)),
    }
    return result, summary


def _serialized(document: dict[str, Any], use_crlf: bool) -> bytes:
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if use_crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when zone_routes.json differs from the fixed source revisions",
    )
    args = parser.parse_args()

    document, summary = build_document()
    existing = json.loads(ZONE_ROUTES_PATH.read_text(encoding="utf-8"))
    if args.check:
        if existing != document:
            print(
                f"{ZONE_ROUTES_PATH.relative_to(ROOT)} is out of date",
                file=sys.stderr,
            )
            return 1
    else:
        raw_existing = ZONE_ROUTES_PATH.read_bytes()
        ZONE_ROUTES_PATH.write_bytes(
            _serialized(document, b"\r\n" in raw_existing)
        )

    total_layouts = sum(item["areaLayouts"] for item in summary.values())
    total_routes = sum(item["endingRoutes"] for item in summary.values())
    total_entries = sum(item["explicitEntryTexts"] for item in summary.values())
    total_quarantine = sum(item["quarantine"] for item in summary.values())
    print(
        f"regions: {total_layouts} layouts, {total_routes} ending routes, "
        f"{total_entries} explicit entry texts, {total_quarantine} quarantine"
    )
    for theme, counts in summary.items():
        print(f"  {theme}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
