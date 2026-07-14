#!/usr/bin/env python3
"""Sync fixed-revision PRTS event metadata into the offline RLV2 rules."""

from __future__ import annotations

import argparse
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
SCENES_PATH = RULES_DIR / "scenes.json"
EVENT_TAGS_PATH = RULES_DIR / "event_tags.json"
MANIFEST_PATH = RULES_DIR / "manifest.json"
API_URL = "https://prts.wiki/api.php"
CLIENT_SOURCE_REF = "client:roguelike-topic-table:634e7e7"
USER_SOURCE_REF = "user-review:2026-07-14"
USER_AGENT = "OpenDoctoratePy-rule-research/1.0"


@dataclass(frozen=True)
class Source:
    theme: str
    page_title: str
    revision: int
    sha1: str

    @property
    def source_ref(self) -> str:
        return f"prts:{self.theme.replace('_', '-')}-events:{self.revision}"


SOURCES = (
    Source(
        "rogue_1",
        "\u5080\u5f71\u4e0e\u7329\u7ea2\u5b64\u94bb/\u4e8b\u4ef6\u4e00\u89c8",
        408344,
        "e1fb2503be3472dccbe70c1c2e3fdca18c1ee30c",
    ),
    Source(
        "rogue_2",
        "\u6c34\u6708\u4e0e\u6df1\u84dd\u4e4b\u6811/\u4e8b\u4ef6\u4e00\u89c8",
        408461,
        "5fe7a759db05c2e68dd513062173b491d772b298",
    ),
    Source(
        "rogue_3",
        "\u63a2\u7d22\u8005\u7684\u94f6\u51c7\u6b62\u5883/\u4e8b\u4ef6\u4e00\u89c8",
        408462,
        "adeadfdd958c92bef31a8042c6d0d53d7385bf03",
    ),
    Source(
        "rogue_4",
        "\u8428\u5361\u5179\u7684\u65e0\u7ec8\u5947\u8bed/\u4e8b\u4ef6\u4e00\u89c8",
        408463,
        "e7b81b5e81ef21ee9f08f1f27753b05ce69ed9c3",
    ),
    Source(
        "rogue_5",
        "\u5c81\u7684\u754c\u56ed\u5fd7\u5f02/\u4e8b\u4ef6\u4e00\u89c8",
        408460,
        "f9eaa7181d0fb4996d24c2c7df7fad27741bdde1",
    ),
)

ROMAN_DEPTHS = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
}
EVENT_MARKER = re.compile(r"^\|\u4e8b\u4ef6([^=\n]+)=", re.MULTILINE)
NAMED_ARGUMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PageEvent:
    key: str
    title: str
    event_type_label: str
    floor_text: str | None
    logical_depths: list[int] | None
    description: str


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


def _logical_depths(floor_text: str | None) -> list[int] | None:
    if floor_text is None:
        return None
    values = [part.strip() for part in floor_text.split(",")]
    try:
        depths = [ROMAN_DEPTHS[value] for value in values]
    except KeyError as exc:
        raise ValueError(f"Unknown PRTS floor label: {exc.args[0]!r}") from exc
    if len(depths) != len(set(depths)):
        raise ValueError(f"Duplicate PRTS floor label: {floor_text!r}")
    return depths


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _parse_events(wikitext: str, source: Source) -> list[PageEvent]:
    markers = list(EVENT_MARKER.finditer(wikitext))
    events: list[PageEvent] = []
    current_event_type: str | None = None

    for index, marker in enumerate(markers):
        body_end = markers[index + 1].start() if index + 1 < len(markers) else len(wikitext)
        body = wikitext[marker.end() : body_end]
        template_start = body.find("{{ISEvent/scene|")
        if template_start < 0:
            raise ValueError(
                f"{source.source_ref} event {marker.group(1).strip()!r} has no scene"
            )

        arguments = _split_top_level(_matching_template(body, template_start))
        if arguments[0].strip() != "ISEvent/scene":
            raise ValueError(f"Unexpected template in {source.source_ref}")

        named: dict[str, str] = {}
        positional: list[str] = []
        for raw_argument in arguments[1:]:
            argument = raw_argument.strip()
            equals = argument.find("=")
            if equals > 0 and NAMED_ARGUMENT.fullmatch(argument[:equals].strip()):
                named[argument[:equals].strip()] = argument[equals + 1 :].strip()
            else:
                positional.append(argument)

        if len(positional) < 4 or positional[0] != "\u5f00\u59cb":
            raise ValueError(
                f"Unexpected opening scene shape in {source.source_ref} "
                f"event {marker.group(1).strip()!r}"
            )
        if "etype" in named:
            current_event_type = named["etype"]
        if not current_event_type:
            raise ValueError(f"Missing event type in {source.source_ref}")

        floor_text = named.get("floor")
        events.append(
            PageEvent(
                key=marker.group(1).strip(),
                title=positional[2],
                event_type_label=current_event_type,
                floor_text=floor_text,
                logical_depths=_logical_depths(floor_text),
                description=positional[3],
            )
        )

    keys = [event.key for event in events]
    if not events or len(keys) != len(set(keys)):
        raise ValueError(f"Missing or duplicate event keys in {source.source_ref}")
    return events


def _eligibility(event: PageEvent) -> dict[str, Any]:
    return {
        "logicalDepths": event.logical_depths,
        "zoneIds": None,
        "modes": None,
        "endingIds": None,
        "conditionAst": None,
        "weight": None,
    }


def _resolve_scene(
    source: Source,
    event: PageEvent,
    candidate_scene_ids: list[str],
    client_scenes: dict[str, dict[str, Any]],
) -> tuple[str, str] | None:
    if len(candidate_scene_ids) == 1:
        return candidate_scene_ids[0], "title_unique"

    theme_number = source.theme.removeprefix("rogue_")
    keyed_scene_id = f"scene_ro{theme_number}_{event.key}_enter"
    if keyed_scene_id in candidate_scene_ids:
        return keyed_scene_id, "source_key_matches_scene_suffix"

    description_matches = [
        scene_id
        for scene_id in candidate_scene_ids
        if _normalized_text(client_scenes[scene_id]["description"])
        == _normalized_text(event.description)
    ]
    if len(description_matches) == 1:
        return description_matches[0], "opening_description_unique"

    if source.theme == "rogue_3" and event.logical_depths is not None:
        standard_candidates = [
            scene_id for scene_id in candidate_scene_ids if "_month" not in scene_id
        ]
        if len(standard_candidates) == 1:
            return (
                standard_candidates[0],
                "standard_scene_selected_over_month_variant",
            )
    return None


def _annotation(
    source: Source,
    event: PageEvent,
    scene_id: str,
    method: str,
    candidate_scene_ids: list[str],
) -> dict[str, Any]:
    floor_note = (
        f"PRTS floor={event.floor_text}."
        if event.floor_text is not None
        else "The PRTS record has no floor parameter."
    )
    return {
        "id": f"{source.theme}:{scene_id}",
        "theme": source.theme,
        "sceneId": scene_id,
        "sourceEventKey": event.key,
        "sourceTitle": event.title,
        "sourceEventTypeLabel": event.event_type_label,
        "eligibility": _eligibility(event),
        "identityResolution": {
            "method": method,
            "candidateSceneIds": candidate_scene_ids,
            "excludedCandidateSceneIds": [
                candidate for candidate in candidate_scene_ids if candidate != scene_id
            ],
        },
        "sourceAliases": [f"{source.source_ref}#event-{event.key}"],
        "evidence": {
            "reviewStatus": "public_sourced",
            "sourceRefs": [source.source_ref, CLIENT_SOURCE_REF],
            "notes": f"{floor_note} Identity method={method}.",
        },
        "implementationStatus": "pending",
        "runtimeEnabled": False,
    }


def _quarantine_record(
    source: Source, event: PageEvent, candidate_scene_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": f"{source.theme}:prts-event:{event.key}",
        "theme": source.theme,
        "sourceEventKey": event.key,
        "sourceTitle": event.title,
        "sourceEventTypeLabel": event.event_type_label,
        "eligibility": _eligibility(event),
        "reason": "ambiguous_scene_identity",
        "candidateSceneIds": candidate_scene_ids,
        "sourceAliases": [f"{source.source_ref}#event-{event.key}"],
        "evidence": {
            "reviewStatus": "needs_review",
            "sourceRefs": [source.source_ref, CLIENT_SOURCE_REF],
            "notes": "The fixed page record matches multiple canonical client scenes.",
        },
        "implementationStatus": "pending",
        "runtimeEnabled": False,
    }


def _unresolved(source_refs: list[str], quarantine_count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": "event-eligibility-beyond-floor",
            "fields": [
                "zoneIds",
                "modes",
                "endingIds",
                "conditionAst",
                "weight",
            ],
            "description": (
                "Fixed PRTS revisions provide explicit logical depths for 171 events; "
                "the remaining eligibility dimensions are not established."
            ),
            "evidence": {
                "reviewStatus": "needs_review",
                "sourceRefs": source_refs,
                "notes": "Missing dimensions stay null; no full-theme fallback is allowed.",
            },
            "implementationStatus": "pending",
            "runtimeEnabled": False,
        },
        {
            "id": "event-scene-quarantine",
            "fields": ["sourceAliases", "sceneMappings", "monthVariants"],
            "description": (
                f"{quarantine_count} fixed-page records still match multiple client scenes "
                "and remain in quarantine."
            ),
            "evidence": {
                "reviewStatus": "needs_review",
                "sourceRefs": [CLIENT_SOURCE_REF, *source_refs],
                "notes": "Aliases never replace canonical sceneId values.",
            },
            "implementationStatus": "pending",
            "runtimeEnabled": False,
        },
        {
            "id": "event-condition-effects",
            "fields": ["conditionAst", "effects", "oneShot", "weight"],
            "description": (
                "Q10 selects a condition AST plus effect interpreter, but does not "
                "establish the missing rule values."
            ),
            "evidence": {
                "reviewStatus": "needs_review",
                "sourceRefs": [USER_SOURCE_REF],
                "notes": "Unknown events remain runtime-disabled.",
            },
            "implementationStatus": "pending",
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
    scene_catalog = json.loads(SCENES_PATH.read_text(encoding="utf-8"))
    topic_table = _load_topic_table()
    existing = json.loads(EVENT_TAGS_PATH.read_text(encoding="utf-8"))
    annotations: dict[str, dict[str, Any]] = {}
    quarantine: list[dict[str, Any]] = []
    summary: dict[str, dict[str, int]] = {}

    for source in SOURCES:
        scenes = scene_catalog["themes"][source.theme]["scenes"].values()
        client_scenes = topic_table["details"][source.theme]["choiceScenes"]
        enter_scenes = [scene for scene in scenes if scene["sceneId"].endswith("_enter")]
        by_title: dict[str, list[str]] = {}
        for scene in enter_scenes:
            by_title.setdefault(scene["title"], []).append(scene["sceneId"])
        for candidate_ids in by_title.values():
            candidate_ids.sort()

        events = _parse_events(_fetch_source(source), source)
        theme_floor_count = 0
        theme_annotation_count = 0
        theme_quarantine_count = 0
        for event in events:
            candidate_scene_ids = by_title.get(event.title, [])
            if not candidate_scene_ids:
                raise ValueError(
                    f"No client scene titled {event.title!r} for {source.source_ref}"
                )
            resolution = _resolve_scene(
                source, event, candidate_scene_ids, client_scenes
            )
            if resolution is None:
                quarantine.append(
                    _quarantine_record(source, event, candidate_scene_ids)
                )
                theme_quarantine_count += 1
                continue

            scene_id, method = resolution
            key = f"{source.theme}:{scene_id}"
            if key in annotations:
                raise ValueError(f"Multiple source events resolve to {key}")
            annotations[key] = _annotation(
                source, event, scene_id, method, candidate_scene_ids
            )
            theme_annotation_count += 1
            if event.logical_depths is not None:
                theme_floor_count += 1

        summary[source.theme] = {
            "sourceEvents": len(events),
            "annotations": theme_annotation_count,
            "quarantine": theme_quarantine_count,
            "explicitFloorAnnotations": theme_floor_count,
        }

    source_refs = [source.source_ref for source in SOURCES]
    result = {
        "$schema": existing["$schema"],
        "kind": existing["kind"],
        "schemaVersion": existing["schemaVersion"],
        "runtimeEnabled": existing["runtimeEnabled"],
        "sourceRefs": source_refs,
        "tagDefinitions": existing["tagDefinitions"],
        "identityPolicy": existing["identityPolicy"],
        "annotations": dict(sorted(annotations.items())),
        "quarantine": sorted(
            quarantine, key=lambda record: (record["theme"], record["sourceEventKey"])
        ),
        "unresolved": _unresolved(source_refs, len(quarantine)),
    }

    if sum(item["explicitFloorAnnotations"] for item in summary.values()) != 171:
        raise ValueError("Unexpected explicit floor annotation count")
    if len(annotations) + len(quarantine) != sum(
        item["sourceEvents"] for item in summary.values()
    ):
        raise ValueError("A PRTS event was lost during identity resolution")
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
        help="fail when event_tags.json differs from the fixed source revisions",
    )
    args = parser.parse_args()

    document, summary = build_document()
    existing = json.loads(EVENT_TAGS_PATH.read_text(encoding="utf-8"))
    if args.check:
        if existing != document:
            print(f"{EVENT_TAGS_PATH.relative_to(ROOT)} is out of date", file=sys.stderr)
            return 1
    else:
        raw_existing = EVENT_TAGS_PATH.read_bytes()
        EVENT_TAGS_PATH.write_bytes(_serialized(document, b"\r\n" in raw_existing))

    total_annotations = sum(item["annotations"] for item in summary.values())
    total_quarantine = sum(item["quarantine"] for item in summary.values())
    total_floors = sum(item["explicitFloorAnnotations"] for item in summary.values())
    print(
        f"events: {total_annotations} annotations, {total_quarantine} quarantine, "
        f"{total_floors} explicit floor mappings"
    )
    for theme, counts in summary.items():
        print(f"  {theme}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
