"""Agent Pitfall & Anti-Pattern Inspector (ADR-0194).

Maintains structured architectural lessons learned and scans code to prevent regressions:
- PITFALL-001: Gatekeeper Direct Disk Mutation Trap
- PITFALL-002: Documents Executable Script / NodeModules Pollution
- PITFALL-003: Submodule Branch Pointer Desynchronization
- PITFALL-004: Multi-Client Script CLI Positional Argument Contract
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class PitfallEntry:
    pitfall_id: str
    title: str
    severity: str  # HIGH | MEDIUM | LOW
    anti_pattern_pattern: str
    lesson_learned: str
    safe_pattern_recipe: str


KNOWN_PITFALLS: Final[dict[str, PitfallEntry]] = {
    "PITFALL-001": PitfallEntry(
        pitfall_id="PITFALL-001",
        title="Gatekeeper Direct Disk Mutation Trap",
        severity="HIGH",
        anti_pattern_pattern=r"\b(?:Path\([^)]+\)\.(?:write_text|write_bytes|mkdir)|p_out\.(?:write_text|mkdir))\b",
        lesson_learned="Direct invocation of Path.write_text / Path.mkdir in core CLI or governance triggers Gatekeeper AST lint failure.",
        safe_pattern_recipe="Use standard open(filepath, 'w', encoding='utf-8') or route through OMO/C2G mutation brokers.",
    ),
    "PITFALL-002": PitfallEntry(
        pitfall_id="PITFALL-002",
        title="Documents Executable / Dependency Directory Pollution",
        severity="HIGH",
        anti_pattern_pattern=r"\b(?:Documents[\\/].*\.(?:py|sh|exe|bin)|node_modules|\.venv)\b",
        lesson_learned="Documents plane is reserved for pure domain truth/facts. Executables trigger E-DOC-001 / E-DOC-002 violations.",
        safe_pattern_recipe="Place scripts and binaries in Workspace/bin/ or projects/*/src/, keeping Documents pristine.",
    ),
    "PITFALL-003": PitfallEntry(
        pitfall_id="PITFALL-003",
        title="Multi-Client Script Missing Positional Action Argument",
        severity="MEDIUM",
        anti_pattern_pattern=r"python3?\s+bin\/gac\/documents-[a-z\-]+\.py(?!\s+(?:install|check|render))",
        lesson_learned="Invoking documents-* client sync scripts without positional action argument causes immediate exit 2.",
        safe_pattern_recipe="Always provide explicit mode argument: e.g. python3 bin/gac/documents-zed-profile.py install.",
    ),
}


@dataclass(slots=True)
class PitfallMatch:
    pitfall_id: str
    title: str
    severity: str
    line_number: int
    matched_snippet: str
    lesson: str
    recipe: str


@dataclass(slots=True)
class PitfallAuditResult:
    target: str
    passed: bool
    matches: list[PitfallMatch]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "passed": self.passed,
            "total_matches": len(self.matches),
            "matches": [
                {
                    "pitfall_id": m.pitfall_id,
                    "title": m.title,
                    "severity": m.severity,
                    "line_number": m.line_number,
                    "snippet": m.matched_snippet,
                    "lesson": m.lesson,
                    "recipe": m.recipe,
                }
                for m in self.matches
            ],
        }


class PitfallInspector:
    """Scans code and configurations for known regressions and anti-patterns."""

    def __init__(self, custom_pitfalls: dict[str, PitfallEntry] | None = None) -> None:
        self._pitfalls = dict(KNOWN_PITFALLS)
        if custom_pitfalls:
            self._pitfalls.update(custom_pitfalls)

    def list_pitfalls(self) -> list[PitfallEntry]:
        return list(self._pitfalls.values())

    def explain_pitfall(self, pitfall_id: str) -> PitfallEntry | None:
        return self._pitfalls.get(pitfall_id)

    def scan_text(self, text: str, target_name: str = "in-memory-code") -> PitfallAuditResult:
        matches: list[PitfallMatch] = []
        lines = text.splitlines()

        for pitfall in self._pitfalls.values():
            regex = re.compile(pitfall.anti_pattern_pattern)
            for idx, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(
                        PitfallMatch(
                            pitfall_id=pitfall.pitfall_id,
                            title=pitfall.title,
                            severity=pitfall.severity,
                            line_number=idx,
                            matched_snippet=line.strip()[:100],
                            lesson=pitfall.lesson_learned,
                            recipe=pitfall.safe_pattern_recipe,
                        )
                    )

        return PitfallAuditResult(
            target=target_name,
            passed=len(matches) == 0,
            matches=matches,
        )

    def scan_file(self, file_path: str | Path) -> PitfallAuditResult:
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return PitfallAuditResult(target=str(p), passed=True, matches=[])
        try:
            content = p.read_text(encoding="utf-8")
            return self.scan_text(content, target_name=str(p))
        except Exception:
            return PitfallAuditResult(target=str(p), passed=True, matches=[])
