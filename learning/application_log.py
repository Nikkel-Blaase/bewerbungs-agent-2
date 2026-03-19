"""Persist and aggregate application history for the self-learning loop."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from utils.config import ROOT_DIR

LOG_FILE = ROOT_DIR / "learning" / "applications.jsonl"


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40]


def save_application(mega, job_url: str) -> str:
    """Append one record to the JSONL log. Returns the record id."""
    from models.document import MegaAnalysisOutput  # avoid circular at module level

    now = datetime.now()
    ts = now.strftime("%Y-%m-%dT%H:%M:%S")
    slug = _slugify(f"{mega.job_data.company}-{mega.job_data.title}")
    record_id = f"{ts}_{slug}"

    translations = []
    for t in mega.skill_translations.translations:
        translations.append({
            "requirement": t.requirement,
            "evidence": t.evidence,
            "cover_letter_formulation": t.cover_letter_formulation,
            "credibility": t.credibility,
        })

    pm_primary = mega.pm_archetype.primary if mega.pm_archetype else None
    pm_confidence = mega.pm_archetype.confidence if mega.pm_archetype else None
    narrative_frame = mega.skill_translations.narrative_frame

    record = {
        "id": record_id,
        "timestamp": ts,
        "job_url": job_url,
        "job_title": mega.job_data.title,
        "company": mega.job_data.company,
        "language": mega.language,
        "fit_score": mega.gap.fit_score,
        "recommendation": mega.gap.recommendation,
        "pm_archetype_primary": pm_primary,
        "pm_archetype_confidence": pm_confidence,
        "translations": translations,
        "gap_notes": list(mega.gap.gap_notes),
        "ko_compensations": list(mega.gap.ko_compensations),
        "top_arguments": list(mega.gap.top_arguments),
        "narrative_frame": narrative_frame,
        "outcome": None,
        "outcome_updated_at": None,
    }

    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record_id


def load_recent(n: int = 20) -> list[dict]:
    """Read last n lines from JSONL. Skips malformed lines silently."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def build_lessons_context(n_recent: int = 20) -> str | None:
    """Aggregate history into injectable string. Returns None if <2 records."""
    records = load_recent(n_recent)
    if len(records) < 2:
        return None

    n = len(records)

    # 1. Stark translations: group by requirement, keep those appearing ≥2×
    stark_map: dict[str, list[str]] = {}
    for rec in records:
        for t in rec.get("translations", []):
            if t.get("credibility") == "stark":
                req = t.get("requirement", "")
                formulation = t.get("cover_letter_formulation", "")
                if req and formulation:
                    stark_map.setdefault(req, []).append(formulation)

    # Sort by frequency, keep top 5 with ≥2 occurrences
    stark_items = sorted(
        [(req, forms) for req, forms in stark_map.items() if len(forms) >= 2],
        key=lambda x: -len(x[1]),
    )[:5]

    # 2. Gap notes: Counter, top 4 appearing in >25% of runs
    gap_counter: Counter = Counter()
    for rec in records:
        for note in rec.get("gap_notes", []):
            gap_counter[note] += 1

    threshold = max(2, round(n * 0.25))
    top_gaps = [(note, cnt) for note, cnt in gap_counter.most_common(4) if cnt >= threshold]

    # 3. KO compensations: deduplicated, top 3, truncated to 120 chars
    seen_ko: set[str] = set()
    ko_comps: list[str] = []
    for rec in records:
        for comp in rec.get("ko_compensations", []):
            if comp not in seen_ko:
                seen_ko.add(comp)
                ko_comps.append(comp[:120])
            if len(ko_comps) >= 3:
                break
        if len(ko_comps) >= 3:
            break

    # 4. PM archetype frequency
    arch_counter: Counter = Counter()
    for rec in records:
        arch = rec.get("pm_archetype_primary")
        if arch:
            arch_counter[arch] += 1

    # Build output string
    lines = [f"## LERNHISTORIE (letzte {n} Bewerbungen)"]

    if stark_items:
        lines.append("\n### Erprobte Übersetzungen mit hoher Glaubwürdigkeit:")
        for req, forms in stark_items:
            # Pick most common formulation
            best_form = Counter(forms).most_common(1)[0][0]
            lines.append(f'- "{req}" → "{best_form}" [{len(forms)}× stark]')

    if top_gaps:
        lines.append("\n### Wiederkehrende Lücken (proaktiv adressieren):")
        for note, cnt in top_gaps:
            lines.append(f"- {note} [{cnt}/{n} Bewerbungen]")

    if ko_comps:
        lines.append("\n### Erprobte K.O.-Kompensationen:")
        for comp in ko_comps:
            suffix = "..." if len(comp) == 120 else ""
            lines.append(f'- "{comp}{suffix}"')

    if arch_counter:
        lines.append("\n### PM-Archetyp-Häufigkeit bisher:")
        parts = [f"{arch}: {cnt}×" for arch, cnt in arch_counter.most_common()]
        lines.append("- " + " | ".join(parts))

    result = "\n".join(lines)

    # Hard limit: 2400 chars
    if len(result) > 2400:
        result = result[:2397] + "[...]"

    return result


def tag_outcome(record_id: str, outcome: str) -> bool:
    """Find record by id, set outcome field, rewrite JSONL. Returns True if found."""
    if not LOG_FILE.exists():
        return False

    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if rec.get("id") == record_id:
            rec["outcome"] = outcome
            rec["outcome_updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            found = True
        new_lines.append(json.dumps(rec, ensure_ascii=False))

    if found:
        LOG_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return found


def list_recent_ids(n: int = 10) -> list[dict]:
    """Return last n records with: id, timestamp, company, job_title, fit_score, outcome."""
    records = load_recent(n)
    return [
        {
            "id": r.get("id", ""),
            "timestamp": r.get("timestamp", ""),
            "company": r.get("company", ""),
            "job_title": r.get("job_title", ""),
            "fit_score": r.get("fit_score", 0.0),
            "outcome": r.get("outcome"),
        }
        for r in records
    ]
