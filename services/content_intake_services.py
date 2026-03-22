from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

from fastapi import HTTPException, UploadFile, status

from database.database import content_intake_sessions_collection, course_catalog_collection, course_curricula_collection
from schemas.schemas import CourseCatalogCreate, CourseCurriculumUpsert, QuestionCreate
from services.agent_services import (
    PLATFORM_AREAS,
    _default_course_tags,
    _infer_course_category,
    _infer_course_difficulty,
    _openai_json_request,
    _slugify_title,
)
from services.auth_services import validate_object_id
from services.content_services import ContentService, normalize_lesson
from services.course_services import CourseCatalogService
from services.lesson_library_services import LessonLibraryService
from services.quiz_services import QuizService

SUPPORTED_UPLOADS = {
    ".json",
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".docx",
    ".csv",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
}
QUESTION_INTENTS = {"quiz", "question_bank"}
QUESTION_TYPE_ALIASES = {
    "single": "single",
    "multiple": "multiple",
    "multiple_choice": "multiple_choice",
    "multiple-choice": "multiple_choice",
    "multiple choice": "multiple_choice",
    "mcq": "multiple_choice",
    "single_choice": "single",
    "single-choice": "single",
    "single choice": "single",
}
QUESTION_DIFFICULTY_ALIASES = {
    "easy": "Easy",
    "beginner": "Easy",
    "basic": "Easy",
    "medium": "Medium",
    "intermediate": "Medium",
    "moderate": "Medium",
    "hard": "Hard",
    "advanced": "Hard",
    "difficult": "Hard",
}
MAX_SOURCE_CHARS = 16000
FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
FENCED_DOCUMENT_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n```\s*$", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
SHORT_HEADING_STOPWORDS = {"and", "or", "to", "of", "in", "on", "for", "who", "what", "why", "how"}
MODULE_TITLE_RE = re.compile(r"^(module|week|unit|chapter|part|section)\b", re.IGNORECASE)
LESSON_TITLE_RE = re.compile(r"^(lesson|topic|session)\b", re.IGNORECASE)
FRAMING_SECTION_ALIASES = {
    "overview": "overview",
    "course overview": "overview",
    "introduction": "overview",
    "course framing": "overview",
    "learning flow": "learning_flow",
    "course flow": "learning_flow",
    "roadmap": "visual_aid",
    "visual aid": "visual_aid",
    "visual roadmap": "visual_aid",
    "course roadmap": "visual_aid",
    "modules and lessons": "modules",
    "modules": "modules",
}


def _actor_label(user: dict) -> str:
    return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("email", "Deveda Team")


def _safe_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() or "Imported Learning Content"


def _decode_text(blob: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return blob.decode(encoding)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="ignore")


def _unwrap_fenced_document(text: str) -> str:
    stripped = text.strip()
    match = FENCED_DOCUMENT_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def _parse_frontmatter_value(value: str):
    cleaned = value.strip().strip(",")
    if not cleaned:
        return ""
    if cleaned.startswith("[") and cleaned.endswith("]"):
        try:
            return json.loads(cleaned.replace("'", '"'))
        except json.JSONDecodeError:
            return [item.strip().strip("'\"") for item in cleaned[1:-1].split(",") if item.strip()]
    if cleaned.startswith('"') and cleaned.endswith('"'):
        return cleaned[1:-1]
    if cleaned.startswith("'") and cleaned.endswith("'"):
        return cleaned[1:-1]
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    metadata: dict[str, object] = {}
    for raw_line in match.group(1).splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        metadata[normalized_key] = _parse_frontmatter_value(value)
    return metadata, text[match.end() :].strip()


def _html_to_markdownish(value: str) -> str:
    html = value.replace("\r", "")
    replacements = [
        (r"(?is)<pre[^>]*><code[^>]*>(.*?)</code></pre>", lambda m: f"\n```\n{unescape(m.group(1)).strip()}\n```\n"),
        (r"(?is)<code[^>]*>(.*?)</code>", lambda m: f"`{unescape(m.group(1)).strip()}`"),
        (r"(?is)<h1[^>]*>(.*?)</h1>", lambda m: f"\n# {unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}\n"),
        (r"(?is)<h2[^>]*>(.*?)</h2>", lambda m: f"\n## {unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}\n"),
        (r"(?is)<h3[^>]*>(.*?)</h3>", lambda m: f"\n### {unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}\n"),
        (r"(?is)<li[^>]*>(.*?)</li>", lambda m: f"- {unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}\n"),
        (r"(?is)<strong[^>]*>(.*?)</strong>", lambda m: f"**{unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}**"),
        (r"(?is)<b[^>]*>(.*?)</b>", lambda m: f"**{unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}**"),
        (r"(?is)<em[^>]*>(.*?)</em>", lambda m: f"*{unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}*"),
        (r"(?is)<i[^>]*>(.*?)</i>", lambda m: f"*{unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()}*"),
        (r"(?is)<br\s*/?>", lambda _: "\n"),
        (r"(?is)</p>", lambda _: "\n\n"),
        (r"(?is)<p[^>]*>", lambda _: ""),
        (r"(?is)</div>", lambda _: "\n"),
        (r"(?is)<div[^>]*>", lambda _: ""),
    ]
    for pattern, repl in replacements:
        html = re.sub(pattern, repl, html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    return unescape(html)


def _clean_heading_title(value: str) -> str:
    cleaned = re.sub(r"[`*_#>\[\]()]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-")
    lowered = cleaned.lower()
    if len(cleaned) < 4 or lowered in SHORT_HEADING_STOPWORDS:
        return ""
    return cleaned


def _markdown_to_plain_text(value: str) -> str:
    text = value
    text = FRONTMATTER_RE.sub("", text)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_>#-]+", " ", text)
    return _collapse_text(text)


def _extract_level_sections(text: str, level: int) -> list[dict]:
    matches = list(re.finditer(rf"^(#{{{level}}})\s+(.+)$", text, flags=re.MULTILINE))
    sections: list[dict] = []
    for index, match in enumerate(matches):
        title = _clean_heading_title(match.group(2))
        if not title:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append({"title": title, "body": body, "markdown": body})
    return sections


def _extract_source_context(filename: str, raw_text: str) -> tuple[str, dict]:
    suffix = Path(filename).suffix.lower()
    normalized = _unwrap_fenced_document(raw_text.replace("\r", "").strip())
    if suffix in {".html", ".htm"} or normalized.lstrip().lower().startswith("<html"):
        normalized = _html_to_markdownish(normalized)
    metadata, body = _extract_frontmatter(normalized)
    cleaned_body = body.strip() or normalized.strip()
    return cleaned_body, {
        "metadata": metadata,
        "h1Sections": _extract_level_sections(cleaned_body, 1),
        "h2Sections": _extract_level_sections(cleaned_body, 2),
    }


def _extract_docx_text(blob: bytes) -> str:
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        document = archive.read("word/document.xml")
    root = ElementTree.fromstring(document)
    chunks = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def _extract_pdf_text(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "PDF import needs the optional `pypdf` dependency on the backend."},
        ) from exc

    reader = PdfReader(BytesIO(blob))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(part for part in parts if part.strip())


def _extract_upload_text(filename: str, blob: bytes) -> tuple[str, Optional[dict]]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOADS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": f"Unsupported file type `{suffix or 'unknown'}`. Use pdf, docx, json, md, txt, csv, html, or yaml."},
        )

    if suffix == ".json":
        structured = json.loads(_decode_text(blob))
        return json.dumps(structured, indent=2, ensure_ascii=False), structured

    if suffix == ".docx":
        return _extract_source_context(filename, _extract_docx_text(blob))

    if suffix == ".pdf":
        return _extract_source_context(filename, _extract_pdf_text(blob))

    return _extract_source_context(filename, _decode_text(blob))


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _section_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _first_sentences(text: str, limit: int = 2) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", _collapse_text(text))
    return [sentence.strip() for sentence in sentences if sentence.strip()][:limit]


def _summarize_text(text: str, fallback: str) -> str:
    sentences = _first_sentences(text, limit=2)
    if sentences:
        return " ".join(sentences)[:320]
    return fallback


def _split_sections(text: str) -> list[dict]:
    normalized = text.replace("\r", "")
    heading_matches = list(
        re.finditer(
            r"^(#{1,4}|\d+\.)\s+(.+)$|^((?:Module|Lesson|Week|Unit|Chapter|Part|Section)\s+\d+(?:\s*[:.-]\s*.+)?)$",
            normalized,
            flags=re.MULTILINE,
        )
    )
    sections: list[dict] = []

    if heading_matches:
        for index, match in enumerate(heading_matches):
            start = match.end()
            end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(normalized)
            title = _clean_heading_title(match.group(2) or match.group(3) or "")
            body = normalized[start:end].strip()
            if title and body:
                sections.append({"title": title, "body": _markdown_to_plain_text(body), "markdown": body})

    if sections:
        return sections

    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", normalized) if chunk.strip()]
    if len(paragraphs) <= 1:
        return [{"title": "Imported lesson", "body": _markdown_to_plain_text(normalized.strip()), "markdown": normalized.strip()}] if normalized.strip() else []

    for index, paragraph in enumerate(paragraphs[:8], start=1):
        paragraph_text = _markdown_to_plain_text(paragraph)
        title = _first_sentences(paragraph_text, limit=1)[0] if _first_sentences(paragraph_text, limit=1) else f"Lesson {index}"
        sections.append({"title": _clean_heading_title(title[:80]) or f"Lesson {index}", "body": _markdown_to_plain_text(paragraph), "markdown": paragraph})
    return sections


def _markdown_list_items(markdown: str) -> list[str]:
    items: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
            continue
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ordered:
            items.append(ordered.group(1).strip())
    return [_collapse_text(_markdown_to_plain_text(item)) for item in items if _collapse_text(_markdown_to_plain_text(item))]


def _flow_from_markdown(markdown: str, fallback: Optional[list[str]] = None) -> list[str]:
    list_items = _markdown_list_items(markdown)
    if list_items:
        return list_items[:6]

    sentences = _first_sentences(_markdown_to_plain_text(markdown), limit=4)
    if sentences:
        return sentences
    return fallback or []


def _find_section_by_alias(sections: list[dict], alias: str) -> Optional[dict]:
    for section in sections:
        normalized_title = _section_key(section.get("title", ""))
        if FRAMING_SECTION_ALIASES.get(normalized_title) == alias:
            return section
    return None


def _module_sections_from_context(source_context: Optional[dict]) -> list[dict]:
    context = source_context or {}
    raw_h2_sections = context.get("h2Sections", []) if isinstance(context, dict) else []
    if not isinstance(raw_h2_sections, list):
        return []

    explicit_modules = [section for section in raw_h2_sections if MODULE_TITLE_RE.match(section.get("title", ""))]
    if explicit_modules:
        return explicit_modules

    modules_anchor = _find_section_by_alias(raw_h2_sections, "modules")
    if modules_anchor:
        nested_modules = _extract_level_sections(modules_anchor.get("body", ""), 3)
        if nested_modules:
            return nested_modules

    return [
        section
        for section in raw_h2_sections
        if FRAMING_SECTION_ALIASES.get(_section_key(section.get("title", ""))) not in {"overview", "learning_flow", "visual_aid"}
    ]


def _lessons_from_module_section(course: dict, module_title: str, module_section: dict) -> list[dict]:
    nested_lessons = _extract_level_sections(module_section.get("body", ""), 3)
    if not nested_lessons:
        nested_lessons = [section for section in _split_sections(module_section.get("body", "")) if LESSON_TITLE_RE.match(section.get("title", ""))]
    if not nested_lessons:
        fallback_body = module_section.get("body", "").strip()
        nested_lessons = [
            {
                "title": module_title,
                "body": _markdown_to_plain_text(fallback_body),
                "markdown": fallback_body,
            }
        ]
    return [_build_lesson_payload(course, module_title, section, course["slug"]) for section in nested_lessons]


def _derive_learning_flow(title: str, summary: str) -> list[str]:
    return [
        f"Start with the problem space around {title}.",
        f"Clarify the central idea: {summary}",
        "Walk through one example before asking the learner to make a change.",
        "Close with a short check or reflection to confirm the idea stuck.",
    ]


def _derive_visual_aid(title: str, summary: str) -> str:
    return "\n".join(
        [
            "## Visual aid",
            f"`Context` -> `{title}` -> `Example` -> `Practice`",
            "",
            summary,
        ]
    )


def _coerce_generation_status(value: Optional[str], default: str = "generated") -> str:
    normalized = _safe_text(value).lower()
    if normalized in {"planned", "generated"}:
        return normalized
    return default


def _source_sections_for_module(module_plan: dict, source_context: Optional[dict]) -> list[dict]:
    if not isinstance(source_context, dict):
        return []

    targets = [module_plan.get("title", ""), *(_string_list(module_plan.get("lessonTitles"), limit=8))]
    target_tokens = [set(_section_key(target).split()) for target in targets if _section_key(target)]
    if not target_tokens:
        return []

    candidates: list[tuple[int, dict]] = []
    for section in [*(source_context.get("h1Sections", []) or []), *(source_context.get("h2Sections", []) or [])]:
        if not isinstance(section, dict):
            continue
        title = _safe_text(section.get("title"))
        body = _safe_text(section.get("body"))
        if not title or not body:
            continue
        section_tokens = set(_section_key(title).split())
        score = max((len(section_tokens & tokens) for tokens in target_tokens), default=0)
        if score <= 0:
            continue
        candidates.append(
            (
                score,
                {
                    "title": title,
                    "body": body[:2600],
                },
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [section for _, section in candidates[:4]]


def _chunk_sections(sections: list[dict], size: int) -> list[list[dict]]:
    return [sections[index : index + size] for index in range(0, len(sections), size)]


def _lesson_duration_from_text(text: str) -> int:
    words = len(_collapse_text(text).split())
    return max(10, min(35, round(words / 28) or 15))


def _markdown_body_for_lesson(title: str, markdown_body: str, summary: str) -> str:
    normalized = markdown_body.strip()
    if not normalized:
        return "\n".join(
            [
                f"# {title}",
                "",
                "## What this lesson is about",
                summary,
                "",
                "## Guided practice",
                "Recreate the core example from the source, then change one important part and explain the result.",
            ]
        )
    if normalized.startswith("#"):
        return normalized
    return "\n".join([f"# {title}", "", normalized])


def _build_lesson_payload(
    course: Optional[dict],
    module_title: str,
    lesson_seed: dict,
    lesson_slug_prefix: str,
    *,
    default_source: str = "agentic_upload",
    default_generation_status: str = "generated",
) -> dict:
    title = _safe_text(lesson_seed.get("title")) or "Imported lesson"
    markdown_body = (
        _safe_text(lesson_seed.get("contentMarkdown"))
        or _safe_text(lesson_seed.get("markdown"))
        or _safe_text(lesson_seed.get("body"))
    )
    body = _markdown_to_plain_text(markdown_body)
    summary = _safe_text(lesson_seed.get("summary")) or _summarize_text(body, f"Work through {title} with a guided explanation and one concrete practice step.")
    flow = _string_list(lesson_seed.get("learningFlow"), limit=6) or _flow_from_markdown(markdown_body, _derive_learning_flow(title, summary))
    lesson_slug = _slugify_title(f"{lesson_slug_prefix}-{title}")
    lesson = {
        "title": title,
        "slug": _safe_text(lesson_seed.get("slug")) or lesson_slug,
        "libraryLessonSlug": _safe_text(lesson_seed.get("libraryLessonSlug")) or _safe_text(lesson_seed.get("slug")) or lesson_slug,
        "source": _safe_text(lesson_seed.get("source")) or default_source,
        "generationStatus": _coerce_generation_status(lesson_seed.get("generationStatus"), default_generation_status),
        "summary": summary,
        "durationMinutes": int(lesson_seed.get("durationMinutes") or _lesson_duration_from_text(body)),
        "contentType": _safe_text(lesson_seed.get("contentType")).lower() or "lesson",
        "quizId": _safe_text(lesson_seed.get("quizId")) or None,
        "quizTitle": _safe_text(lesson_seed.get("quizTitle")) or None,
        "learningObjectives": _string_list(lesson_seed.get("learningObjectives"), limit=6)
        or [
            f"Explain {title} in simple language.",
            "Apply the concept once in a guided context.",
            "Recognize one mistake or misconception to avoid.",
        ],
        "keyTakeaways": _string_list(lesson_seed.get("keyTakeaways"), limit=6)
        or [
            summary,
            "Tie the concept to a visible outcome before memorizing details.",
            "Use the practice task to confirm the explanation is reusable.",
        ],
        "learningFlow": flow,
        "visualAidMarkdown": _safe_text(lesson_seed.get("visualAidMarkdown")) or _derive_visual_aid(title, summary),
        "contentMarkdown": _markdown_body_for_lesson(title, markdown_body, summary),
        "practicePrompt": _safe_text(lesson_seed.get("practicePrompt")) or f"Use {title} to build one small example, then explain what changed when you modified it.",
        "instructorNotes": _safe_text(lesson_seed.get("instructorNotes")) or "Imported from an uploaded source document and normalized for the Deveda lesson renderer.",
        "playground": lesson_seed.get("playground"),
    }
    if course:
        return normalize_lesson(course, module_title, lesson)
    return lesson


def _build_planned_lesson_payload(course: dict, module_title: str, lesson_title: str, lesson_slug_prefix: str, module_description: str) -> dict:
    title = _safe_text(lesson_title) or "Planned lesson"
    summary = _safe_text(module_description) or "Planned from the uploaded source. Generate this module to create the learner-facing lesson content."
    return _build_lesson_payload(
        course,
        module_title,
        {
            "title": title,
            "summary": summary,
            "learningFlow": [],
            "learningObjectives": [],
            "keyTakeaways": [],
            "contentMarkdown": f"# {title}\n\nThis lesson is planned from the uploaded source and will be generated after you approve this module.",
            "visualAidMarkdown": "",
            "practicePrompt": "",
            "instructorNotes": "Planned lesson shell created from the upload scan. Generate the module to replace this shell with learner-ready content.",
            "source": "scan_plan",
            "generationStatus": "planned",
        },
        lesson_slug_prefix,
        default_source="scan_plan",
        default_generation_status="planned",
    )


def _fallback_course_curriculum(course: dict, extracted_text: str, filename: str, source_context: Optional[dict] = None) -> dict:
    context = source_context or {}
    metadata = context.get("metadata", {}) if isinstance(context, dict) else {}
    raw_h2_sections = context.get("h2Sections", []) if isinstance(context, dict) else []
    structured_modules = _module_sections_from_context(source_context)
    overview_section = _find_section_by_alias(raw_h2_sections, "overview") if isinstance(raw_h2_sections, list) else None
    learning_flow_section = _find_section_by_alias(raw_h2_sections, "learning_flow") if isinstance(raw_h2_sections, list) else None
    visual_aid_section = _find_section_by_alias(raw_h2_sections, "visual_aid") if isinstance(raw_h2_sections, list) else None

    modules = []
    if structured_modules:
        for index, module_section in enumerate(structured_modules, start=1):
            lessons = _lessons_from_module_section(course, module_section["title"], module_section)
            modules.append(
                {
                    "title": module_section["title"],
                    "description": _summarize_text(_markdown_to_plain_text(module_section.get("body", "")), f"Progress through {module_section['title']} with guided explanation and application."),
                    "order": index,
                    "lessons": lessons,
                    "assessmentTitle": f"{module_section['title']} checkpoint",
                    "assessmentQuizId": f"{course['slug']}-module-{index}-checkpoint",
                }
            )
    else:
        sections = _split_sections(extracted_text)
        if not sections:
            sections = [{"title": _title_from_filename(filename), "body": _markdown_to_plain_text(extracted_text or "Imported source content."), "markdown": extracted_text or ""}]

        module_groups = _chunk_sections(sections, 2 if len(sections) > 4 else max(1, len(sections)))
        for index, group in enumerate(module_groups, start=1):
            module_title = _safe_text(group[0].get("title")) or f"Module {index}"
            lessons = [_build_lesson_payload(course, module_title, section, course["slug"]) for section in group]
            modules.append(
                {
                    "title": module_title,
                    "description": _summarize_text(" ".join(section.get("body", "") for section in group), f"Progress through {module_title} with guided explanation and application."),
                    "order": index,
                    "lessons": lessons,
                    "assessmentTitle": f"{module_title} checkpoint",
                    "assessmentQuizId": f"{course['slug']}-module-{index}-checkpoint",
                }
            )

    module_titles = [module["title"] for module in modules]
    overview_seed = str(metadata.get("description") or "").strip() if isinstance(metadata, dict) else ""
    course_learning_flow = _flow_from_markdown(
        learning_flow_section.get("body", "") if learning_flow_section else "",
        [
            f"Start with {module_titles[0]}." if module_titles else "Start with the first concept.",
            "Move from explanation into guided implementation.",
            "Use each checkpoint before moving to the next module.",
            "Finish by combining the ideas in a visible milestone.",
        ],
    )
    visual_aid = (
        visual_aid_section.get("body", "").strip()
        if visual_aid_section and visual_aid_section.get("body", "").strip()
        else "\n".join(
            [
                "## Course roadmap",
                " -> ".join(f"`{title}`" for title in module_titles) or "`Imported lesson`",
                "",
                "Study each module in order, then use the checkpoint to confirm the concept before moving forward.",
            ]
        )
    )
    return {
        "overview": overview_seed or _markdown_to_plain_text(overview_section.get("body", "") if overview_section else "") or _summarize_text(extracted_text, course.get("description", "")),
        "learningFlow": course_learning_flow,
        "visualAidMarkdown": visual_aid,
        "modules": modules,
        "milestoneProjects": [
            {
                "title": f"{course['title']} applied milestone",
                "description": "Turn the uploaded source into a practical end-to-end implementation or walkthrough deliverable.",
                "milestoneOrder": 1,
                "estimatedHours": max(3, len(modules) * 2),
                "deliverables": ["Working implementation or annotated notes", "Short reflection", "Reusable summary of the main ideas"],
                "completionThreshold": 70,
            }
        ],
    }


def _normalize_question_candidate(candidate: dict, quiz_id: str) -> Optional[dict]:
    prompt = _safe_text(candidate.get("question") or candidate.get("question_text"))
    if not prompt:
        return None

    raw_options = candidate.get("options")
    if isinstance(raw_options, dict):
        options = [str(raw_options.get(key, "")).strip() for key in ["A", "B", "C", "D"] if str(raw_options.get(key, "")).strip()]
        answer = str(candidate.get("correct_answer") or candidate.get("correctAnswer") or "").strip()
        if answer in {"A", "B", "C", "D"}:
            answer = next((option for key, option in zip(["A", "B", "C", "D"], options) if key == answer), options[0] if options else "")
    else:
        options = [str(option).strip() for option in raw_options or [] if str(option).strip()]
        answer = _safe_text(candidate.get("correctAnswer") or candidate.get("correct_answer"))

    if len(options) < 2:
        return None
    if answer not in options:
        answer = options[0]

    return {
        "quizId": _safe_text(candidate.get("quizId")) or quiz_id,
        "question": prompt,
        "options": options[:6],
        "correctAnswer": answer,
        "explanation": _safe_text(candidate.get("explanation")) or "Review the uploaded source and explain why the correct answer is the best fit.",
        "points": int(candidate.get("points") or 1),
        "timeLimit": int(candidate.get("timeLimit") or 60),
        "questionType": _normalize_question_type(candidate.get("questionType")),
        "difficulty": _normalize_question_difficulty(candidate.get("difficulty")),
        "isActive": bool(candidate.get("isActive", True)),
    }


def _string_list(value: object, limit: Optional[int] = None) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [_safe_text(str(item)) for item in value if _safe_text(str(item))]
    return items[:limit] if limit is not None else items


def _frontend_generation_contract() -> dict:
    return {
        "courseCurriculumFields": ["overview", "learningFlow", "visualAidMarkdown", "modules", "milestoneProjects"],
        "moduleFields": ["title", "description", "order", "source", "generationStatus", "assessmentTitle", "assessmentQuizId", "lessons"],
        "lessonFields": [
            "title",
            "slug",
            "libraryLessonSlug",
            "source",
            "generationStatus",
            "summary",
            "durationMinutes",
            "contentType",
            "learningObjectives",
            "keyTakeaways",
            "learningFlow",
            "contentMarkdown",
            "visualAidMarkdown",
            "practicePrompt",
            "instructorNotes",
        ],
        "questionRules": {
            "questionType": ["single", "multiple", "multiple_choice"],
            "difficulty": ["Easy", "Medium", "Hard"],
        },
        "renderingNotes": [
            "Overview is plain text summary shown before the modules.",
            "visualAidMarkdown should be readable markdown, not raw YAML or parser noise.",
            "Each lesson contentMarkdown should be learner-facing markdown that can render directly in the frontend.",
            "learningFlow items should be short instructional steps, not paragraphs.",
            "contentMarkdown and visualAidMarkdown can use headings, lists, code fences, links, quotes, and horizontal rules.",
            "Use precise descriptive lesson titles grounded in the uploaded source. Avoid filler titles like 'learn' or 'hands on' unless the source explicitly uses them and they are expanded.",
            "Planned shell lessons use generationStatus='planned'. Fully generated learner content uses generationStatus='generated'.",
        ],
        "platformAreas": PLATFORM_AREAS,
        "frontendSurfaces": {
            "lessonsLibrary": "Shows title, summary, duration, course link, and the first two learning flow items.",
            "coursePage": "Shows overview, module previews, detailed curriculum, and learner open buttons for published lessons.",
            "courseLearnPage": "Renders lesson summary, objectives, learning flow, markdown content, visual aid, practice prompt, and optional playground.",
            "cmsStudio": "Allows instructors to review planned shells first, then replace them module by module with generated learner-ready content.",
        },
    }


def _normalize_question_type(value: Optional[str]) -> str:
    normalized = _safe_text(value).lower().replace("_", " ").replace("-", " ")
    return QUESTION_TYPE_ALIASES.get(normalized, QUESTION_TYPE_ALIASES.get(_safe_text(value).lower(), "multiple_choice"))


def _normalize_question_difficulty(value: Optional[str]) -> str:
    normalized = _safe_text(value).lower()
    return QUESTION_DIFFICULTY_ALIASES.get(normalized, "Medium")


def _serialize_session(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "intent": document.get("intent", "course"),
        "status": document.get("status", "scanned"),
        "fileName": document.get("file_name", ""),
        "courseSlug": document.get("course_slug"),
        "sourcePreview": document.get("source_preview", ""),
        "summary": document.get("summary", ""),
        "scan": document.get("scan", {}),
        "generation": document.get("generation", {}),
        "course": document.get("course"),
        "curriculum": document.get("curriculum"),
        "createdAt": document.get("created_at"),
        "updatedAt": document.get("updated_at"),
    }


async def _get_generation_session_or_404(session_id: str, current_user: dict) -> dict:
    document = await content_intake_sessions_collection.find_one({"_id": validate_object_id(session_id)})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Content generation session not found."},
        )
    if str(document.get("user_id")) != str(current_user["_id"]) and current_user.get("role") != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "You do not have access to this content generation session."},
        )
    return document


def _find_question_candidates(structured: object) -> list[dict]:
    if isinstance(structured, list):
        return [item for item in structured if isinstance(item, dict)]
    if isinstance(structured, dict):
        for key in ("questions", "items"):
            value = structured.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        subjects = structured.get("subjects")
        if isinstance(subjects, list):
            collected = []
            for subject in subjects:
                if isinstance(subject, dict) and isinstance(subject.get("questions"), list):
                    collected.extend(item for item in subject["questions"] if isinstance(item, dict))
            if collected:
                return collected
    return []


def _structured_payload_excerpt(structured: object) -> str:
    if structured is None:
        return ""
    try:
        serialized = json.dumps(structured, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""
    return serialized[:MAX_SOURCE_CHARS]


def _normalize_openai_course_payload(course: dict, payload: object) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None

    modules = []
    raw_modules = payload.get("modules")
    if isinstance(raw_modules, list):
        for index, module in enumerate(raw_modules, start=1):
            if not isinstance(module, dict):
                continue
            module_title = _safe_text(module.get("title"))
            if not module_title:
                continue

            lesson_items = module.get("lessons") if isinstance(module.get("lessons"), list) else []
            lessons = []
            for lesson in lesson_items:
                if not isinstance(lesson, dict):
                    continue
                lesson_title = _safe_text(lesson.get("title"))
                if not lesson_title:
                    continue
                lessons.append(
                    _build_lesson_payload(
                        course,
                        module_title,
                        {
                            **lesson,
                            "title": lesson_title,
                            "contentMarkdown": lesson.get("contentMarkdown") or lesson.get("body") or lesson.get("summary") or "",
                            "source": lesson.get("source") or "agentic_upload",
                            "generationStatus": lesson.get("generationStatus") or "generated",
                        },
                        course["slug"],
                    )
                )

            if not lessons:
                continue

            modules.append(
                {
                    "title": module_title,
                    "description": _safe_text(module.get("description")) or f"Progress through {module_title} with guided explanation and application.",
                    "order": int(module.get("order") or index),
                    "source": _safe_text(module.get("source")) or "agentic_upload",
                    "generationStatus": _coerce_generation_status(module.get("generationStatus"), "generated"),
                    "lessons": lessons,
                    "assessmentTitle": _safe_text(module.get("assessmentTitle")) or f"{module_title} checkpoint",
                    "assessmentQuizId": _safe_text(module.get("assessmentQuizId")) or f"{course['slug']}-module-{index}-checkpoint",
                }
            )

    if not modules:
        return None

    overview = _markdown_to_plain_text(str(payload.get("overview") or ""))
    learning_flow = _string_list(payload.get("learningFlow"), limit=8)
    visual_aid = _safe_text(payload.get("visualAidMarkdown"))
    milestone_projects = payload.get("milestoneProjects") if isinstance(payload.get("milestoneProjects"), list) else []

    return {
        "overview": overview or course.get("description", ""),
        "learningFlow": learning_flow,
        "visualAidMarkdown": visual_aid,
        "modules": modules,
        "milestoneProjects": milestone_projects,
    }


def _normalize_openai_lesson_payload(course: Optional[dict], payload: object, lesson_slug_prefix: str) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None

    lesson = payload.get("lesson") if isinstance(payload.get("lesson"), dict) else payload
    if not isinstance(lesson, dict):
        return None

    title = _safe_text(lesson.get("title"))
    if not title:
        return None

    return _build_lesson_payload(
        course,
        _safe_text(lesson.get("moduleTitle")) or "Imported lesson",
        {
            **lesson,
            "title": title,
            "contentMarkdown": lesson.get("contentMarkdown") or lesson.get("body") or lesson.get("summary") or "",
            "source": lesson.get("source") or "agentic_upload",
            "generationStatus": lesson.get("generationStatus") or "generated",
        },
        lesson_slug_prefix,
    )


def _normalize_scan_payload(filename: str, payload: object, source_context: Optional[dict], extracted_text: str) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None

    recommended_course = payload.get("recommendedCourse") if isinstance(payload.get("recommendedCourse"), dict) else {}
    modules = []
    for index, module in enumerate(payload.get("modules", []), start=1) if isinstance(payload.get("modules"), list) else []:
        if not isinstance(module, dict):
            continue
        title = _safe_text(module.get("title"))
        if not title:
            continue
        lesson_titles = _string_list(module.get("lessonTitles"), limit=8)
        lesson_count = int(module.get("lessonCount") or len(lesson_titles) or 4)
        if not lesson_titles:
            lesson_titles = [f"{title} lesson {item}" for item in range(1, lesson_count + 1)]
        modules.append(
            {
                "order": int(module.get("order") or index),
                "title": title,
                "description": _safe_text(module.get("description")) or f"Work through {title} with guided explanation and practice.",
                "lessonCount": lesson_count,
                "lessonTitles": lesson_titles[:lesson_count],
                "estimatedQuestionCount": int(module.get("estimatedQuestionCount") or 5),
            }
        )

    if not modules:
        return None

    metadata = (source_context or {}).get("metadata", {}) if isinstance(source_context, dict) else {}
    title = _safe_text(recommended_course.get("title")) or _safe_text(str(metadata.get("title") or "")) or _title_from_filename(filename)
    description = _safe_text(recommended_course.get("description")) or _summarize_text(extracted_text, f"Imported learning content for {title}.")
    category = _safe_text(recommended_course.get("category")) or _infer_course_category(f"{title} {extracted_text[:1200]}")
    difficulty = _safe_text(recommended_course.get("difficulty")).title() or str(metadata.get("difficulty") or _infer_course_difficulty(extracted_text[:1200])).title()
    return {
        "summary": _safe_text(payload.get("summary")) or _summarize_text(extracted_text, description),
        "recommendedCourse": {
            "title": title,
            "description": description,
            "category": category,
            "difficulty": difficulty,
            "tags": recommended_course.get("tags") if isinstance(recommended_course.get("tags"), list) else _default_course_tags(category, title),
        },
        "overview": _markdown_to_plain_text(str(payload.get("overview") or description)),
        "learningFlow": _string_list(payload.get("learningFlow"), limit=8),
        "visualAidMarkdown": _safe_text(payload.get("visualAidMarkdown")),
        "modules": modules,
        "milestoneProjects": payload.get("milestoneProjects") if isinstance(payload.get("milestoneProjects"), list) else [],
    }


def _scan_fallback(filename: str, extracted_text: str, source_context: Optional[dict]) -> dict:
    metadata = (source_context or {}).get("metadata", {}) if isinstance(source_context, dict) else {}
    suggested_course = {
        "title": _safe_text(str(metadata.get("title") or "")) or _title_from_filename(filename),
        "description": _safe_text(str(metadata.get("description") or "")) or _summarize_text(extracted_text, _title_from_filename(filename)),
        "category": _infer_course_category(extracted_text[:1200]),
        "difficulty": str(metadata.get("difficulty") or _infer_course_difficulty(extracted_text[:1200])).title(),
        "tags": metadata.get("tags") if isinstance(metadata.get("tags"), list) else _default_course_tags(_infer_course_category(extracted_text[:1200]), _title_from_filename(filename)),
    }
    fallback_curriculum = _fallback_course_curriculum(
        {
            "slug": _slugify_title(suggested_course["title"]),
            "title": suggested_course["title"],
            "description": suggested_course["description"],
        },
        extracted_text,
        filename,
        source_context,
    )
    modules = []
    for module in fallback_curriculum.get("modules", []):
        lesson_titles = [lesson.get("title", "Lesson") for lesson in module.get("lessons", [])]
        modules.append(
            {
                "order": int(module.get("order") or len(modules) + 1),
                "title": module.get("title", f"Module {len(modules) + 1}"),
                "description": module.get("description", ""),
                "lessonCount": len(lesson_titles) or 1,
                "lessonTitles": lesson_titles or [module.get("title", "Lesson")],
                "estimatedQuestionCount": 5,
            }
        )
    return {
        "summary": _summarize_text(extracted_text, suggested_course["description"]),
        "recommendedCourse": suggested_course,
        "overview": fallback_curriculum.get("overview", suggested_course["description"]),
        "learningFlow": fallback_curriculum.get("learningFlow", []),
        "visualAidMarkdown": fallback_curriculum.get("visualAidMarkdown", ""),
        "modules": modules,
        "milestoneProjects": fallback_curriculum.get("milestoneProjects", []),
    }


def _build_shell_curriculum(course: dict, scan: dict) -> dict:
    modules = []
    for index, module in enumerate(scan.get("modules", []), start=1):
        lesson_titles = _string_list(module.get("lessonTitles"), limit=8)
        lessons = [
            _build_planned_lesson_payload(course, module.get("title", f"Module {index}"), lesson_title, course["slug"], module.get("description", ""))
            for lesson_title in lesson_titles
        ]
        modules.append(
            {
                "title": module.get("title", f"Module {index}"),
                "description": module.get("description", ""),
                "order": int(module.get("order") or index),
                "source": "scan_plan",
                "generationStatus": "planned",
                "assessmentTitle": f"{module.get('title', f'Module {index}')} checkpoint",
                "assessmentQuizId": f"{course['slug']}-module-{index}-checkpoint",
                "lessons": lessons,
            }
        )

    return {
        "overview": scan.get("overview", course.get("description", "")),
        "learningFlow": scan.get("learningFlow", []),
        "visualAidMarkdown": scan.get("visualAidMarkdown", ""),
        "modules": modules,
        "milestoneProjects": scan.get("milestoneProjects", []),
    }


def _course_payload_from_scan(scan: dict, current_user: dict) -> CourseCatalogCreate:
    suggested = scan.get("recommendedCourse", {})
    title = _safe_text(suggested.get("title")) or "Imported Course"
    category = _safe_text(suggested.get("category")) or "Frontend Development"
    difficulty = _safe_text(suggested.get("difficulty")).title() or "Beginner"
    base_slug = _slugify_title(title)
    return CourseCatalogCreate(
        slug=base_slug,
        title=title,
        description=_safe_text(suggested.get("description")) or scan.get("overview", title),
        category=category,
        difficulty=difficulty,
        duration=max(45, len(scan.get("modules", [])) * 20),
        totalLessons=sum(int(module.get("lessonCount") or 0) for module in scan.get("modules", [])),
        totalQuizzes=max(1, len(scan.get("modules", []))),
        instructor=_actor_label(current_user),
        prerequisites=[],
        tags=suggested.get("tags") if isinstance(suggested.get("tags"), list) else _default_course_tags(category, title),
        thumbnail="",
        thumbnailPublicId="",
    )


def _curriculum_payload_from_serialized(curriculum: dict) -> CourseCurriculumUpsert:
    return CourseCurriculumUpsert(
        overview=curriculum.get("overview", ""),
        learningFlow=curriculum.get("learningFlow", []),
        visualAidMarkdown=curriculum.get("visualAidMarkdown", ""),
        modules=curriculum.get("modules", []),
        milestoneProjects=curriculum.get("milestoneProjects", []),
    )


def _merge_module_into_curriculum(curriculum: dict, module_payload: dict) -> dict:
    modules = []
    replaced = False
    for module in curriculum.get("modules", []):
        if int(module.get("order") or 0) == int(module_payload.get("order") or 0):
            modules.append(module_payload)
            replaced = True
        else:
            modules.append(module)
    if not replaced:
        modules.append(module_payload)
    modules.sort(key=lambda item: int(item.get("order") or 1))
    return {
        **curriculum,
        "modules": modules,
    }


def _normalize_openai_module_payload(course: dict, module_order: int, module_plan: dict, payload: object) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None
    module = payload.get("module") if isinstance(payload.get("module"), dict) else payload
    if not isinstance(module, dict):
        return None
    title = _safe_text(module.get("title")) or _safe_text(module_plan.get("title"))
    if not title:
        return None
    lessons = []
    for lesson in module.get("lessons", []) if isinstance(module.get("lessons"), list) else []:
        if not isinstance(lesson, dict) or not _safe_text(lesson.get("title")):
            continue
        lessons.append(
            _build_lesson_payload(
                course,
                title,
                {
                    **lesson,
                    "source": lesson.get("source") or "agentic_upload",
                    "generationStatus": lesson.get("generationStatus") or "generated",
                },
                course["slug"],
            )
        )
    if not lessons:
        return None
    return {
        "title": title,
        "description": _safe_text(module.get("description")) or _safe_text(module_plan.get("description")),
        "order": module_order,
        "source": _safe_text(module.get("source")) or "agentic_upload",
        "generationStatus": _coerce_generation_status(module.get("generationStatus"), "generated"),
        "assessmentTitle": _safe_text(module.get("assessmentTitle")) or f"{title} checkpoint",
        "assessmentQuizId": _safe_text(module.get("assessmentQuizId")) or f"{course['slug']}-module-{module_order}-checkpoint",
        "lessons": lessons,
    }


def _openai_course_payload(
    course: dict,
    extracted_text: str,
    instruction: str,
    source_context: Optional[dict] = None,
    structured: Optional[object] = None,
) -> Optional[dict]:
    clipped_text = extracted_text[:MAX_SOURCE_CHARS]
    structured_excerpt = _structured_payload_excerpt(structured)
    payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's course ingestion and restructuring engine. Return valid JSON only. "
                    "Your job is to take parsed source material and rewrite it into Deveda's learner-facing frontend schema. "
                    "Treat the extracted content as raw source, then improve the arrangement, formatting, grouping, and lesson flow for frontend display. "
                    "Preserve useful markdown, produce clean module and lesson boundaries, and never echo YAML frontmatter as lesson text. "
                    "Use the uploaded source as the primary truth. Do not fall back to generic titles, generic summaries, or placeholder lesson bodies unless the source is genuinely missing."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact top-level shape: "
                    "{\"overview\": string, \"learningFlow\": string[], \"visualAidMarkdown\": string, "
                    "\"modules\": [{\"title\": string, \"description\": string, \"order\": number, \"assessmentTitle\": string, \"assessmentQuizId\": string, "
                    "\"source\": string, \"generationStatus\": string, "
                    "\"lessons\": [{\"title\": string, \"slug\": string, \"libraryLessonSlug\": string, \"source\": string, \"generationStatus\": string, \"summary\": string, \"durationMinutes\": number, "
                    "\"contentType\": string, \"learningObjectives\": string[], \"keyTakeaways\": string[], \"learningFlow\": string[], "
                    "\"contentMarkdown\": string, \"visualAidMarkdown\": string, \"practicePrompt\": string, \"instructorNotes\": string}]}], "
                    "\"milestoneProjects\": [{\"title\": string, \"description\": string, \"milestoneOrder\": number, \"estimatedHours\": number, "
                    "\"deliverables\": string[], \"completionThreshold\": number}]}. "
                    "Use the parsed context as hints only, but return a polished frontend-ready curriculum. "
                    "Use `generationStatus` of `generated` for full learner-ready content. "
                    "Keep markdown rich and readable, and preserve concrete terminology from the upload. "
                    "Prefer meaningful restructuring over copying the source verbatim. "
                    f"Frontend contract: {json.dumps(_frontend_generation_contract(), default=str)}. "
                    f"Course metadata: {json.dumps(course, default=str)}. "
                    f"Parsed source context: {json.dumps(source_context or {}, default=str)}. "
                    f"Parsed structured payload: {structured_excerpt or 'null'}. "
                    f"Instructor instruction: {instruction}. "
                    f"Uploaded source: {clipped_text}"
                ),
            },
        ],
        timeout=30,
    )
    return _normalize_openai_course_payload(course, payload)


def _openai_lesson_payload(
    course: Optional[dict],
    extracted_text: str,
    instruction: str,
    lesson_slug_prefix: str,
    source_context: Optional[dict] = None,
    structured: Optional[object] = None,
) -> Optional[dict]:
    clipped_text = extracted_text[:MAX_SOURCE_CHARS]
    structured_excerpt = _structured_payload_excerpt(structured)
    payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's lesson ingestion and restructuring engine. Return valid JSON only. "
                    "Turn the parsed source into one polished frontend-ready lesson with strong markdown structure, a clean learning flow, and a clear visual aid. "
                    "Do not dump raw frontmatter or broken source fragments back into the lesson. "
                    "Use the uploaded source as the authority and avoid generic filler phrasing."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"lesson\": {\"title\": string, \"slug\": string, \"libraryLessonSlug\": string, \"source\": string, \"generationStatus\": string, \"summary\": string, \"durationMinutes\": number, "
                    "\"contentType\": string, \"learningObjectives\": string[], \"keyTakeaways\": string[], \"learningFlow\": string[], "
                    "\"contentMarkdown\": string, \"visualAidMarkdown\": string, \"practicePrompt\": string, \"instructorNotes\": string}}. "
                    "Restructure the source for frontend rendering, not just extraction. "
                    "Set `generationStatus` to `generated` for this learner-ready lesson. "
                    f"Frontend contract: {json.dumps(_frontend_generation_contract(), default=str)}. "
                    f"Course context: {json.dumps(course or {}, default=str)}. "
                    f"Parsed source context: {json.dumps(source_context or {}, default=str)}. "
                    f"Parsed structured payload: {structured_excerpt or 'null'}. "
                    f"Slug prefix: {lesson_slug_prefix}. "
                    f"Instructor instruction: {instruction}. "
                    f"Uploaded source: {clipped_text}"
                ),
            },
        ],
        timeout=24,
    )
    return _normalize_openai_lesson_payload(course, payload, lesson_slug_prefix)


def _openai_scan_payload(
    filename: str,
    extracted_text: str,
    instruction: str,
    *,
    source_context: Optional[dict] = None,
    structured: Optional[object] = None,
    course: Optional[dict] = None,
) -> Optional[dict]:
    payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's content scan planner. Return valid JSON only. "
                    "Analyze the uploaded source and propose a staged course-generation plan that fits Deveda's frontend curriculum schema. "
                    "Do not generate full lessons yet. Produce a plan with modules, lesson counts, lesson titles, course framing, and milestone direction. "
                    "Use descriptive titles grounded in the source and avoid filler lesson names."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"summary\": string, "
                    "\"recommendedCourse\": {\"title\": string, \"description\": string, \"category\": string, \"difficulty\": string, \"tags\": string[]}, "
                    "\"overview\": string, \"learningFlow\": string[], \"visualAidMarkdown\": string, "
                    "\"modules\": [{\"order\": number, \"title\": string, \"description\": string, \"lessonCount\": number, \"lessonTitles\": string[], \"estimatedQuestionCount\": number}], "
                    "\"milestoneProjects\": [{\"title\": string, \"description\": string, \"milestoneOrder\": number, \"estimatedHours\": number, \"deliverables\": string[], \"completionThreshold\": number}]}. "
                    f"Frontend contract: {json.dumps(_frontend_generation_contract(), default=str)}. "
                    f"Linked course context: {json.dumps(course or {}, default=str)}. "
                    f"Parsed source context: {json.dumps(source_context or {}, default=str)}. "
                    f"Parsed structured payload: {_structured_payload_excerpt(structured) or 'null'}. "
                    f"Instructor instruction: {instruction}. "
                    f"Filename: {filename}. "
                    f"Uploaded source: {extracted_text[:MAX_SOURCE_CHARS]}"
                ),
            },
        ],
        timeout=24,
    )
    return _normalize_scan_payload(filename, payload, source_context, extracted_text)


def _openai_module_payload(
    course: dict,
    module_plan: dict,
    extracted_text: str,
    instruction: str,
    *,
    source_context: Optional[dict] = None,
    structured: Optional[object] = None,
    current_curriculum: Optional[dict] = None,
) -> Optional[dict]:
    relevant_source_sections = _source_sections_for_module(module_plan, source_context)
    payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's module generation agent. Return valid JSON only. "
                    "Generate exactly one module with polished lesson content that matches Deveda's frontend curriculum schema. "
                    "Use learner-facing markdown, concise instructional flow, and practical lesson boundaries. "
                    "Use the uploaded source as the authority for lesson content, examples, and sequencing."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"module\": {\"title\": string, \"description\": string, \"order\": number, \"source\": string, \"generationStatus\": string, \"assessmentTitle\": string, \"assessmentQuizId\": string, "
                    "\"lessons\": [{\"title\": string, \"slug\": string, \"libraryLessonSlug\": string, \"source\": string, \"generationStatus\": string, \"summary\": string, \"durationMinutes\": number, \"contentType\": string, \"learningObjectives\": string[], "
                    "\"keyTakeaways\": string[], \"learningFlow\": string[], \"contentMarkdown\": string, \"visualAidMarkdown\": string, "
                    "\"practicePrompt\": string, \"instructorNotes\": string}]}}. "
                    "Set the module and lessons to `generationStatus` of `generated`. "
                    "Base every lesson on the uploaded source and target module plan. "
                    "Do not return placeholder text like 'Work through X' unless the upload actually says that. "
                    f"Frontend contract: {json.dumps(_frontend_generation_contract(), default=str)}. "
                    f"Course context: {json.dumps(course, default=str)}. "
                    f"Current curriculum: {json.dumps(current_curriculum or {}, default=str)}. "
                    f"Target module plan: {json.dumps(module_plan, default=str)}. "
                    f"Relevant source sections: {json.dumps(relevant_source_sections, default=str)}. "
                    f"Parsed source context: {json.dumps(source_context or {}, default=str)}. "
                    f"Parsed structured payload: {_structured_payload_excerpt(structured) or 'null'}. "
                    f"Instructor instruction: {instruction}. "
                    f"Uploaded source: {extracted_text[:MAX_SOURCE_CHARS]}"
                ),
            },
        ],
        timeout=28,
    )
    return _normalize_openai_module_payload(course, int(module_plan.get("order") or 1), module_plan, payload)


def _openai_question_payloads(
    extracted_text: str,
    quiz_id: str,
    instruction: str,
    *,
    structured: Optional[object] = None,
    source_context: Optional[dict] = None,
) -> list[dict]:
    structured_excerpt = _structured_payload_excerpt(structured)
    payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's assessment ingestion and restructuring engine. Return valid JSON only. "
                    "Turn parsed assessment material into clean frontend-ready multiple-choice questions."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"questions\": [{\"quizId\": string, \"question\": string, \"options\": string[], \"correctAnswer\": string, "
                    "\"explanation\": string, \"points\": number, \"timeLimit\": number, \"questionType\": string, \"difficulty\": string, \"isActive\": boolean}]}. "
                    f"Use `{quiz_id}` as the default quizId. "
                    f"Parsed source context: {json.dumps(source_context or {}, default=str)}. "
                    f"Parsed structured payload: {structured_excerpt or 'null'}. "
                    f"Instructor instruction: {instruction}. "
                    f"Uploaded source: {extracted_text[:MAX_SOURCE_CHARS]}"
                ),
            },
        ],
        timeout=26,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        return []
    return [item for item in payload["questions"] if isinstance(item, dict)]


def _lesson_to_module(course: dict, lesson: dict, module_order: int) -> dict:
    title = lesson.get("title", "Imported lesson")
    return {
        "title": f"{title} module",
        "description": lesson.get("summary", f"Work through {title} with a guided lesson and follow-up practice."),
        "order": module_order,
        "lessons": [normalize_lesson(course, f"{title} module", lesson)],
        "assessmentTitle": f"{title} checkpoint",
        "assessmentQuizId": f"{course['slug']}-{_slugify_title(title)}-checkpoint",
    }


class ContentIntakeService:
    @staticmethod
    async def start_generation_session(
        current_user: dict,
        *,
        source_file: UploadFile,
        course_slug: Optional[str] = None,
        instructions: str = "",
    ):
        filename = source_file.filename or "uploaded-source"
        blob = await source_file.read()
        if not blob:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "The uploaded file is empty."},
            )

        extracted_text, structured = _extract_upload_text(filename, blob)
        if not _collapse_text(extracted_text):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "No readable text was found in the uploaded file."},
            )

        source_context = structured if isinstance(structured, dict) else {}
        linked_course = await course_catalog_collection.find_one({"slug": course_slug}) if course_slug else None
        scan = _openai_scan_payload(
            filename,
            extracted_text,
            instructions,
            source_context=source_context,
            structured=structured,
            course=linked_course,
        ) or _scan_fallback(filename, extracted_text, source_context)

        actor = _actor_label(current_user)
        now = datetime.utcnow()
        document = {
            "user_id": current_user["_id"],
            "intent": "course",
            "status": "scanned",
            "file_name": filename,
            "course_slug": course_slug,
            "source_preview": extracted_text[:1200],
            "source_text": extracted_text,
            "source_context": source_context,
            "structured_payload": structured,
            "summary": scan.get("summary") or _summarize_text(extracted_text, f"Imported content from {filename}."),
            "instructions": _safe_text(instructions),
            "scan": scan,
            "generation": {
                "shellCreated": False,
                "generatedModules": [],
                "generatedQuestionModules": [],
            },
            "course": linked_course and {
                "slug": linked_course.get("slug"),
                "title": linked_course.get("title"),
            },
            "curriculum": None,
            "created_at": now,
            "updated_at": now,
            "updated_by": actor,
        }
        result = await content_intake_sessions_collection.insert_one(document)
        document["_id"] = result.inserted_id
        return {"message": "Content scan complete", "data": _serialize_session(document)}

    @staticmethod
    async def get_generation_session(session_id: str, current_user: dict):
        session = await _get_generation_session_or_404(session_id, current_user)
        return {"message": "Content generation session fetched", "data": _serialize_session(session)}

    @staticmethod
    async def run_generation_action(
        session_id: str,
        current_user: dict,
        *,
        action_type: str,
        module_order: Optional[int] = None,
        question_count: Optional[int] = None,
        instructions: str = "",
    ):
        session = await _get_generation_session_or_404(session_id, current_user)
        actor = _actor_label(current_user)
        merged_instructions = "\n".join(item for item in [session.get("instructions", ""), _safe_text(instructions)] if item).strip()
        scan = session.get("scan", {})
        course_slug = session.get("course_slug")

        if action_type == "create_course_shell":
            course = await course_catalog_collection.find_one({"slug": course_slug}) if course_slug else None
            if not course:
                payload = _course_payload_from_scan(scan, current_user)
                base_slug = payload.slug
                slug = base_slug
                suffix = 2
                while await course_catalog_collection.find_one({"slug": slug}):
                    slug = f"{base_slug}-{suffix}"
                    suffix += 1
                payload.slug = slug
                created = await CourseCatalogService.create_course_catalog(payload)
                course = await course_catalog_collection.find_one({"slug": created["data"]["slug"]})

            shell_curriculum = _build_shell_curriculum(course, scan)
            saved_curriculum = await ContentService.upsert_course_curriculum(
                course["slug"],
                _curriculum_payload_from_serialized({**shell_curriculum, "courseSlug": course["slug"]}),
                actor,
            )
            await content_intake_sessions_collection.update_one(
                {"_id": session["_id"]},
                {
                    "$set": {
                        "status": "shell_created",
                        "course_slug": course["slug"],
                        "course": {"slug": course["slug"], "title": course.get("title", "")},
                        "curriculum": saved_curriculum["data"],
                        "generation.shellCreated": True,
                        "updated_at": datetime.utcnow(),
                        "updated_by": actor,
                    }
                },
            )
            refreshed = await _get_generation_session_or_404(session_id, current_user)
            return {"message": "Course shell created from scan plan", "data": _serialize_session(refreshed)}

        if action_type == "generate_overview":
            if not course_slug:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Create a course shell before generating overview content."})
            course = await course_catalog_collection.find_one({"slug": course_slug})
            saved_curriculum = await ContentService.upsert_course_curriculum(
                course_slug,
                _curriculum_payload_from_serialized({**_build_shell_curriculum(course, scan), "courseSlug": course_slug}),
                actor,
            )
            await content_intake_sessions_collection.update_one(
                {"_id": session["_id"]},
                {"$set": {"curriculum": saved_curriculum["data"], "updated_at": datetime.utcnow(), "updated_by": actor}},
            )
            refreshed = await _get_generation_session_or_404(session_id, current_user)
            return {"message": "Course framing refreshed from scan plan", "data": _serialize_session(refreshed)}

        if action_type == "generate_module":
            if not course_slug:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Create a course shell before generating modules."})
            if not module_order:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "moduleOrder is required for module generation."})
            module_plan = next((item for item in scan.get("modules", []) if int(item.get("order") or 0) == module_order), None)
            if not module_plan:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Requested module plan was not found in this session."})
            course = await course_catalog_collection.find_one({"slug": course_slug})
            current_curriculum = (await ContentService.get_course_curriculum(course_slug))["data"]
            generated_module = _openai_module_payload(
                course,
                module_plan,
                session.get("source_text", ""),
                merged_instructions,
                source_context=session.get("source_context", {}),
                structured=session.get("structured_payload"),
                current_curriculum=current_curriculum,
            ) or _build_shell_curriculum(course, {"modules": [module_plan], "overview": current_curriculum.get("overview", ""), "learningFlow": current_curriculum.get("learningFlow", []), "visualAidMarkdown": current_curriculum.get("visualAidMarkdown", ""), "milestoneProjects": current_curriculum.get("milestoneProjects", [])})["modules"][0]
            merged_curriculum = _merge_module_into_curriculum(current_curriculum, generated_module)
            saved_curriculum = await ContentService.upsert_course_curriculum(course_slug, _curriculum_payload_from_serialized(merged_curriculum), actor)
            generated_modules = sorted(set([*session.get("generation", {}).get("generatedModules", []), module_order]))
            await content_intake_sessions_collection.update_one(
                {"_id": session["_id"]},
                {
                    "$set": {
                        "status": "in_progress",
                        "curriculum": saved_curriculum["data"],
                        "generation.generatedModules": generated_modules,
                        "updated_at": datetime.utcnow(),
                        "updated_by": actor,
                    }
                },
            )
            refreshed = await _get_generation_session_or_404(session_id, current_user)
            return {"message": f"Module {module_order} generated", "data": _serialize_session(refreshed)}

        if action_type == "generate_questions":
            if not course_slug:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Create a course shell before generating questions."})
            if not module_order:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "moduleOrder is required for question generation."})
            current_curriculum = (await ContentService.get_course_curriculum(course_slug))["data"]
            module = next((item for item in current_curriculum.get("modules", []) if int(item.get("order") or 0) == module_order), None)
            if not module:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Generate the target module before generating questions for it."})
            quiz_id = module.get("assessmentQuizId") or f"{course_slug}-module-{module_order}-checkpoint"
            module_source = json.dumps(
                {
                    "modulePlan": next((item for item in scan.get("modules", []) if int(item.get("order") or 0) == module_order), {}),
                    "generatedModule": module,
                },
                default=str,
            )
            openai_candidates = _openai_question_payloads(
                module_source,
                quiz_id,
                merged_instructions,
                structured=session.get("structured_payload"),
                source_context={"moduleOrder": module_order, "moduleTitle": module.get("title"), "frontendContract": _frontend_generation_contract()},
            )
            normalized_candidates = [_normalize_question_candidate(item, quiz_id) for item in openai_candidates if isinstance(item, dict)]
            normalized_candidates = [item for item in normalized_candidates if item][: question_count or 5]
            existing = await QuizService.get_quiz_questions(quiz_id)
            existing_questions = {_collapse_text(item.get("question", "")) for item in existing["data"]}
            saved_questions = []
            for candidate in normalized_candidates:
                if _collapse_text(candidate["question"]) in existing_questions:
                    continue
                payload = QuestionCreate(**candidate)
                response = await QuizService.create_question(payload, actor)
                saved_questions.append(response["data"])
            generated_question_modules = sorted(set([*session.get("generation", {}).get("generatedQuestionModules", []), module_order]))
            await content_intake_sessions_collection.update_one(
                {"_id": session["_id"]},
                {
                    "$set": {
                        "generation.generatedQuestionModules": generated_question_modules,
                        "updated_at": datetime.utcnow(),
                        "updated_by": actor,
                    }
                },
            )
            refreshed = await _get_generation_session_or_404(session_id, current_user)
            data = _serialize_session(refreshed)
            data["generatedQuestions"] = saved_questions
            return {"message": f"Questions generated for module {module_order}", "data": data}

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Unknown content generation action."})

    @staticmethod
    async def ingest_upload(
        current_user: dict,
        *,
        intent: str,
        source_file: UploadFile,
        course_slug: Optional[str] = None,
        instructions: str = "",
    ):
        normalized_intent = _safe_text(intent).lower()
        if normalized_intent not in {"course", "lesson", "quiz", "question_bank"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Intent must be one of course, lesson, quiz, or question_bank."},
            )

        filename = source_file.filename or "uploaded-source"
        blob = await source_file.read()
        if not blob:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "The uploaded file is empty."},
            )

        extracted_text, structured = _extract_upload_text(filename, blob)
        if not _collapse_text(extracted_text):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "No readable text was found in the uploaded file."},
            )

        actor = _actor_label(current_user)
        summary = _summarize_text(extracted_text, f"Imported content from {filename}.")
        preview = extracted_text[:800]
        source_context = structured if isinstance(structured, dict) else {}

        if normalized_intent == "course":
            course = await ContentIntakeService._resolve_or_create_course(course_slug, filename, extracted_text, current_user, source_context)
            generated = (
                _openai_course_payload(course, extracted_text, instructions, source_context, structured)
                or _fallback_course_curriculum(course, extracted_text, filename, source_context)
            )
            curriculum_payload = CourseCurriculumUpsert(
                overview=_safe_text(generated.get("overview")) or course.get("description", ""),
                learningFlow=generated.get("learningFlow", []),
                visualAidMarkdown=_safe_text(generated.get("visualAidMarkdown")),
                modules=generated.get("modules", []),
                milestoneProjects=generated.get("milestoneProjects", []),
            )
            saved_curriculum = await ContentService.upsert_course_curriculum(
                course["slug"],
                curriculum_payload,
                actor,
            )
            curriculum_response = await CourseCatalogService.get_course_by_slug(course["slug"])
            questions = await ContentIntakeService._create_questions_from_source(
                structured=structured,
                source_context=source_context,
                extracted_text=extracted_text,
                default_quiz_id=f"{course['slug']}-imported-quiz",
                created_by=actor,
                instructions=instructions,
            )
            lessons = await LessonLibraryService.get_library(current_user)
            attached_lessons = [item for item in lessons["data"] if any(ref.get("courseSlug") == course["slug"] for ref in item.get("courseRefs", []))]
            return {
                "message": "Course content imported successfully",
                "data": {
                    "intent": normalized_intent,
                    "fileName": filename,
                    "extractedTextPreview": preview,
                    "summary": summary,
                    "course": curriculum_response["data"],
                    "curriculum": saved_curriculum["data"],
                    "lessons": attached_lessons,
                    "questions": questions,
                    "stats": {
                        "lessonCount": len(attached_lessons),
                        "questionCount": len(questions),
                        "quizCount": len({item["quizId"] for item in questions}) if questions else 0,
                    },
                },
            }

        if normalized_intent == "lesson":
            course = await course_catalog_collection.find_one({"slug": course_slug}) if course_slug else None
            lesson_prefix = course["slug"] if course else _slugify_title(_title_from_filename(filename))
            generated = _openai_lesson_payload(course, extracted_text, instructions, lesson_prefix, source_context, structured)
            lesson = (
                generated
                or
                _build_lesson_payload(
                    course,
                    "Imported lesson",
                    {
                        "title": str(source_context.get("metadata", {}).get("title") or _title_from_filename(filename)),
                        "body": _markdown_to_plain_text(extracted_text),
                        "markdown": extracted_text,
                    },
                    lesson_prefix,
                )
            )

            if course:
                existing = await course_curricula_collection.find_one({"course_slug": course["slug"]})
                modules = (existing or {}).get("modules", [])
                next_module_order = len(modules) + 1
                modules.append(_lesson_to_module(course, lesson, next_module_order))
                curriculum_payload = CourseCurriculumUpsert(
                    overview=(existing or {}).get("overview", course.get("description", "")),
                    learningFlow=(existing or {}).get("learning_flow", []),
                    visualAidMarkdown=(existing or {}).get("visual_aid_markdown", ""),
                    modules=modules,
                    milestoneProjects=(existing or {}).get("milestone_projects", []),
                )
                saved_curriculum = await ContentService.upsert_course_curriculum(
                    course["slug"],
                    curriculum_payload,
                    actor,
                )
                lessons = await LessonLibraryService.get_library(current_user)
                attached_lessons = [item for item in lessons["data"] if item["slug"] == lesson.get("libraryLessonSlug")]
                return {
                    "message": "Lesson imported into the selected course",
                    "data": {
                        "intent": normalized_intent,
                        "fileName": filename,
                        "extractedTextPreview": preview,
                        "summary": summary,
                        "course": (await CourseCatalogService.get_course_by_slug(course["slug"]))["data"],
                        "curriculum": saved_curriculum["data"],
                        "lessons": attached_lessons,
                        "questions": [],
                        "stats": {"lessonCount": len(attached_lessons), "questionCount": 0, "quizCount": 0},
                    },
                }

            standalone = await LessonLibraryService.upsert_standalone_lesson(lesson, actor)
            return {
                "message": "Standalone lesson imported successfully",
                "data": {
                    "intent": normalized_intent,
                    "fileName": filename,
                    "extractedTextPreview": preview,
                    "summary": summary,
                    "course": None,
                    "curriculum": None,
                    "lessons": [standalone],
                    "questions": [],
                    "stats": {"lessonCount": 1, "questionCount": 0, "quizCount": 0},
                },
            }

        default_quiz_id = f"{course_slug}-imported-quiz" if course_slug else f"{_slugify_title(_title_from_filename(filename))}-imported-quiz"
        questions = await ContentIntakeService._create_questions_from_source(
            structured=structured,
            source_context=source_context,
            extracted_text=extracted_text,
            default_quiz_id=default_quiz_id,
            created_by=actor,
            instructions=instructions,
        )
        return {
            "message": "Assessment content imported successfully",
            "data": {
                "intent": normalized_intent,
                "fileName": filename,
                "extractedTextPreview": preview,
                "summary": summary,
                "course": (await CourseCatalogService.get_course_by_slug(course_slug))["data"] if course_slug else None,
                "curriculum": None,
                "lessons": [],
                "questions": questions,
                "stats": {
                    "lessonCount": 0,
                    "questionCount": len(questions),
                    "quizCount": len({item["quizId"] for item in questions}) if questions else 0,
                },
            },
        }

    @staticmethod
    async def _resolve_or_create_course(course_slug: Optional[str], filename: str, extracted_text: str, current_user: dict, source_context: Optional[dict] = None) -> dict:
        if course_slug:
            course = await course_catalog_collection.find_one({"slug": course_slug})
            if not course:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"message": "Selected course was not found."},
                )
            return course

        metadata = (source_context or {}).get("metadata", {}) if isinstance(source_context, dict) else {}
        title = str(metadata.get("title") or _title_from_filename(filename))
        description = str(metadata.get("description") or _summarize_text(extracted_text, f"Imported learning content for {title}."))
        category = _infer_course_category(f"{title} {extracted_text[:1200]}")
        difficulty = str(metadata.get("difficulty") or _infer_course_difficulty(extracted_text[:1200])).title()
        base_slug = _slugify_title(title)
        slug = base_slug
        suffix = 2
        while await course_catalog_collection.find_one({"slug": slug}):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        lessons = max(1, len(_module_sections_from_context(source_context)) or len(_split_sections(extracted_text)))
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else _default_course_tags(category, title)
        payload = CourseCatalogCreate(
            slug=slug,
            title=title,
            description=description,
            category=category,
            difficulty=difficulty,
            duration=max(45, lessons * 20),
            totalLessons=lessons,
            totalQuizzes=max(1, min(lessons, 4)),
            instructor=_actor_label(current_user),
            prerequisites=[],
            tags=tags,
            thumbnail="",
            thumbnailPublicId="",
        )
        response = await CourseCatalogService.create_course_catalog(payload)
        return await course_catalog_collection.find_one({"slug": response["data"]["slug"]})

    @staticmethod
    async def _create_questions_from_source(
        *,
        structured: Optional[object],
        source_context: Optional[dict],
        extracted_text: str,
        default_quiz_id: str,
        created_by: str,
        instructions: str,
    ) -> list[dict]:
        normalized_candidates: list[dict] = []

        if extracted_text:
            openai_candidates = _openai_question_payloads(
                extracted_text,
                default_quiz_id,
                instructions,
                structured=structured,
                source_context=source_context,
            )
            normalized_candidates = [_normalize_question_candidate(item, default_quiz_id) for item in openai_candidates if isinstance(item, dict)]
            normalized_candidates = [item for item in normalized_candidates if item]

        if not normalized_candidates:
            candidates = [_normalize_question_candidate(item, default_quiz_id) for item in _find_question_candidates(structured) if isinstance(item, dict)]
            normalized_candidates = [item for item in candidates if item]

        saved_questions = []
        for candidate in normalized_candidates[:20]:
            payload = QuestionCreate(**candidate)
            response = await QuizService.create_question(payload, created_by)
            saved_questions.append(response["data"])
        return saved_questions
