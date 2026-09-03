"""DLP broker — 防泄密围栏与自动脱敏沙箱 (BET-Y1Q4-T10-01).

外发公文/邮件/外部模型调用前的本地闸: 规则引擎 (regex, <2ms 热路径零模型)
+ NER 插件接口 (可选增强). 高危涉密 → quarantine 挂起 + 报警,
永不自动外发 (non_goal 红线: 未脱敏原文绝不外传).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA = "ecos.governance.dlp.v1"
SCAN_BUDGET_MS = 2.0  # done_when: 判定耗时 <2ms (规则层热路径)
QUARANTINE_ALERT = "检测到{types}，需夏明星二次确认"
TYPE_LABELS = {  # 报警文案中文化 (done_when 契约文案)
    "classified_doc_number": "机密文号",
    "classified_mark": "涉密标识",
    "national_id": "身份证号",
    "mobile_phone": "手机号",
    "internal_ip": "内部IP",
    "financial_budget": "机密财务预算",
}

# ── Rule engine (single source) ───────────────────────────────────────
# (type, compiled, risk, redaction_level) — 高危: 涉密文号/身份证; 中危: 其余
_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "classified_doc_number",
        re.compile(r"〔\d{4}〕\d{1,4}号|〔\d{4}〕第?\d+号"),
        "high",
        "mask",
    ),
    (
        "classified_mark",
        re.compile(r"绝密|机密级|秘密级|涉密"),
        "high",
        "redact",
    ),
    (
        "national_id",
        re.compile(r"\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])\d{3}[\dXx]\b"),
        "high",
        "partial",
    ),
    (
        "mobile_phone",
        re.compile(r"\b1[3-9]\d{9}\b"),
        "medium",
        "partial",
    ),
    (
        "internal_ip",
        re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b"
        ),
        "medium",
        "mask",
    ),
    (
        "financial_budget",
        re.compile(
            r"(?:预算|拨款|决算|经费)[^。\n]{0,12}\d+(?:\.\d+)?\s*(?:万亿元?|亿元?|万元?)|金额[^。\n]{0,8}\d+(?:\.\d+)?\s*万元?"
        ),
        "high",
        "mask",
    ),
]


@dataclass(frozen=True, slots=True)
class Finding:
    type: str
    start: int
    end: int
    snippet: str  # 命中片段 (报告用; quarantine 产物不外传)
    risk: str
    redaction: str


class NERBackend:
    """可选 NER 增强 (人名/机构/地名). 模型在位时 detect; 不在位跳过.

    规则层已保证 done_when 的 100%/2ms — NER 是能力增强不是契约依赖.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._failed = False

    @property
    def available(self) -> bool:
        if self._failed:
            return False
        if self._model is None:
            try:
                from transformers import AutoModelForTokenClassification, AutoTokenizer  # type: ignore[import-not-found]

                name = "uer/roberta-base-finetuned-cluener2020-chinese"
                self._model = (
                    AutoTokenizer.from_pretrained(name),
                    AutoModelForTokenClassification.from_pretrained(name),
                )
            except Exception:
                self._failed = True
                return False
        return True

    def detect(self, text: str) -> list[Finding]:
        """NER 命中仅标 medium (非确定性敏感), 与规则层去重由 scan 负责."""
        if not self.available:
            return []
        tokenizer, model = self._model
        import torch

        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inputs).logits
        labels = logits.argmax(-1)[0].tolist()
        tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
        entities: list[str] = []
        current: list[str] = []
        for tok, label in zip(tokens, labels):
            tag = model.config.id2label.get(label, "O")
            piece = tok[2:] if tok.startswith("##") else tok
            if tag != "O" or current:
                current.append(piece)
                if tag.endswith("E") or tag == "O":  # entity end or boundary
                    ent = "".join(current)
                    if len(ent) >= 2:
                        entities.append(ent)
                    current = []
        out: list[Finding] = []
        for ent in entities:
            idx = text.find(ent)
            if idx >= 0:
                out.append(Finding("ner_entity", idx, idx + len(ent), ent[:30], "medium", "partial"))
        return out


def scan(text: str, ner: NERBackend | None = None) -> list[Finding]:
    """Rule-first scan (hot path, <2ms); optional NER enrichment afterwards."""
    findings: list[Finding] = [
        Finding(rule_id, m.start(), m.end(), m.group()[:40], risk, redaction)
        for rule_id, pattern, risk, redaction in _RULES
        for m in pattern.finditer(text)
    ]
    if ner is not None:
        rule_spans = {(f.start, f.end) for f in findings}
        findings.extend(f for f in ner.detect(text) if (f.start, f.end) not in rule_spans)
    findings.sort(key=lambda f: f.start)
    return findings


def sanitize(text: str, findings: list[Finding], level: str | None = None) -> str:
    """多级脱敏: partial(首尾保留) / mask(掩码) / redact(删除)."""
    out = list(text)
    for f in findings:
        lv = level or f.redaction
        if lv == "redact":
            repl = ""
        elif lv == "mask":
            repl = "█" * (f.end - f.start)
        else:  # partial: 首尾各留 1/4, 中间掩码
            n = f.end - f.start
            keep = max(1, n // 4)
            repl = (
                text[f.start : f.start + keep] + "█" * max(0, n - 2 * keep) + text[f.end - keep : f.end]
                if n > 4
                else "█" * n
            )
        for i in range(f.start, f.end):
            out[i] = ""
        out[f.start] = repl
    return "".join(out)


def quarantine(text: str, findings: list[Finding]) -> dict[str, Any]:  # noqa: ARG001 (text kept for API symmetry)
    """高危挂起: 永不自动外发, 报警需人工确认 (done_when 契约)."""
    high = [f for f in findings if f.risk == "high"]
    types = sorted({TYPE_LABELS.get(f.type, f.type) for f in high})
    return {
        "schema": SCHEMA,
        "status": "pending_approval" if high else "clean_or_medium",
        "alert": QUARANTINE_ALERT.format(types="、".join(types)) if high else None,
        "high_risk_count": len(high),
        "finding_count": len(findings),
        "finding_types": sorted({f.type for f in findings}),
        "red_line": "未脱敏原文不外传; 高危须人工确认后处置",
    }


# ── Offline eval (verify contract) ────────────────────────────────────

_EVAL: list[tuple[str, str]] = [
    # classified doc numbers (high)
    ("国卫办发布〔2026〕15号文件", "classified_doc_number"),
    ("依据〔2025〕第128号文执行", "classified_doc_number"),
    ("机要〔2024〕3号密件转发", "classified_doc_number"),
    # classified marks (high)
    ("本文件属于机密级管理范围", "classified_mark"),
    ("该方案标注绝密字样", "classified_mark"),
    # national ids (high)
    ("联系人身份证号 11010119900307867X", "national_id"),
    ("经办人证件 440301200112150030 请核验", "national_id"),
    # mobile phones (medium)
    ("联系电话 13812345678 王先生", "mobile_phone"),
    ("回拨 15901234567 确认", "mobile_phone"),
    # internal IPs (medium)
    ("内网服务器 10.12.34.56 维护窗口", "internal_ip"),
    ("节点地址 100.99.210.78 不可外泄", "internal_ip"),
    ("交换机 192.168.1.1 配置变更", "internal_ip"),
    # financial budgets (high)
    ("本年度预算安排 3500万元 用于试点", "financial_budget"),
    ("专项拨款 1.2亿元 已获批", "financial_budget"),
    # adversarial: must NOT trigger
    ("今天会议纪要编号第3号议题", None),
    ("用户名为 user19 的会话", None),
    ("参考 GB/T 9704-2012 排版标准", None),
]


def test_dlp() -> dict[str, Any]:
    """Verify contract: 100% recall (rule face), <2ms, quarantine semantics."""
    misses: list[str] = []
    false_positives: list[str] = []
    for text, expected in _EVAL:
        found_types = {f.type for f in scan(text)}
        if expected and expected not in found_types:
            misses.append(f"{expected} missed: {text[:30]}")
        if not expected and found_types:
            false_positives.append(f"false positive {found_types}: {text[:30]}")

    samples: list[float] = []
    long_text = "，".join(t for t, _ in _EVAL) * 5
    for _ in range(5):  # median-of-5
        t0 = time.monotonic()
        scan(long_text)
        samples.append((time.monotonic() - t0) * 1000)
    samples.sort()
    scan_ms = samples[len(samples) // 2]

    q = quarantine("国卫办发布〔2026〕15号", scan("国卫办发布〔2026〕15号"))

    checks = {
        "recall_100pct": not misses,
        "zero_false_positives": not false_positives,
        "scan_within_2ms": scan_ms <= SCAN_BUDGET_MS,
        "quarantine_alerts_high_risk": q["status"] == "pending_approval" and "夏明星" in (q["alert"] or ""),
        "sanitized_output_clean": not scan(sanitize(long_text, scan(long_text))),
    }
    return {
        "schema": SCHEMA,
        "checks": checks,
        "scan_ms_median": round(scan_ms, 3),
        "misses": misses,
        "false_positives": false_positives,
        "quarantine_sample": q,
        "ner_backend_available": NERBackend().available,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-dlp", action="store_true")
    parser.add_argument("--scan-text", help="扫描一段文本")
    args = parser.parse_args(argv)
    if args.test_dlp:
        report = test_dlp()
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if all(report["checks"].values()) else 1
    if args.scan_text:
        findings = scan(args.scan_text)
        print(json.dumps(quarantine(args.scan_text, findings), ensure_ascii=False, indent=1))
        print("findings:", json.dumps([asdict(f) for f in findings], ensure_ascii=False))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
