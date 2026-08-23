"""Shadow Challenger & Red-Team Deliberation Engine (ADR-0196).

Executes multi-perspective adversarial review on proposals and drafts:
1. Audit Angle (Audit Bureau / Finance Inspection)
2. Cyber Security Angle (MLPS Level 3 & Xinchuang / Data Safety)
3. Transfer Reward & TRL Angle (Legal Reward Red-Line)

Includes automated patch synthesis to auto-heal compliance vulnerabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ecos.ssot.compiler.policy_inspector import PolicyComplianceInspector


@dataclass(frozen=True, slots=True)
class ChallengeIssue:
    perspective: str  # "AUDIT_FINANCE" | "CYBER_SECURITY" | "TECH_TRANSFER"
    severity: str  # "BLOCK" | "WARN"
    flaw_title: str
    attack_critique: str
    patch_prescription: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "perspective": self.perspective,
            "severity": self.severity,
            "flaw_title": self.flaw_title,
            "attack_critique": self.attack_critique,
            "patch_prescription": self.patch_prescription,
        }


@dataclass(slots=True)
class ShadowChallengeReport:
    target_name: str
    domain: str
    passed: bool
    robustness_score: int  # 0 - 100
    challenges: list[ChallengeIssue] = field(default_factory=list)
    patched_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "domain": self.domain,
            "passed": self.passed,
            "robustness_score": self.robustness_score,
            "challenges_count": len(self.challenges),
            "challenges": [c.to_dict() for c in self.challenges],
            "patched_text": self.patched_text,
        }


class ShadowChallenger:
    """Multi-angle adversarial challenger for documents, specs, and proposals."""

    def __init__(self) -> None:
        self.policy_inspector = PolicyComplianceInspector()

    def challenge_text(
        self,
        text: str,
        domain: str = "auto",
        target_name: str = "raw-proposal",
        auto_patch: bool = True,
    ) -> ShadowChallengeReport:
        # 1. Run Policy Inspector
        policy_report = self.policy_inspector.audit_text(text, domain=domain, target_name=target_name)
        detected_domain = policy_report.domain

        challenges: list[ChallengeIssue] = []

        # 2. Angle A: Audit & Finance Critique
        for v in policy_report.violations:
            if v.rule_id == "E-POL-WJ-001":
                challenges.append(
                    ChallengeIssue(
                        perspective="AUDIT_FINANCE",
                        severity="BLOCK",
                        flaw_title="大额财政预算缺乏立项专家评审论证与信创技术路线",
                        attack_critique="审计署审计要点：单体项目超 500 万元未组织外部专家论证，且软硬件未明确信创适配，属于重大审计合规缺陷。",
                        patch_prescription="必须在方案第一章补充‘经组织行业与信创专家专题论证，技术架构 100% 采用自主可控基础软硬件’条款。",
                    )
                )

        # 3. Angle B: Cyber Security Critique
        for v in policy_report.violations:
            if v.rule_id == "E-POL-WJ-002":
                challenges.append(
                    ChallengeIssue(
                        perspective="CYBER_SECURITY",
                        severity="BLOCK",
                        flaw_title="核心医疗临床业务系统缺失网络安全等保三级与国密测评方案",
                        attack_critique="网信与卫健安全检查要点：处理居民电子健康档案与临床诊疗数据的系统未明确保密资质与等保三级防护，存在一票否决风险。",
                        patch_prescription="必须在安全体系章节补充‘系统严格落实国家网络安全等级保护三级要求，全链路启用 SM2/SM3/SM4 国密算法加密传输’。",
                    )
                )

        # 4. Angle C: Tech Transfer Reward Critique
        for v in policy_report.violations:
            if v.rule_id == "E-POL-TF-001":
                challenges.append(
                    ChallengeIssue(
                        perspective="TECH_TRANSFER",
                        severity="BLOCK",
                        flaw_title="科技成果转化团队收益分配低于 70% 法定红线",
                        attack_critique="科技法务审查要点：根据《促进科技成果转化法》，科研团队收益分配比例不得低于 70%，当前约定将导致合同无效与法律纠纷。",
                        patch_prescription="将作价入股或转让收益分配方案明确调整为‘完成人及团队所得收益占比 ≥70%’。",
                    )
                )

        for w in policy_report.warnings:
            if w.rule_id == "E-POL-TF-002":
                challenges.append(
                    ChallengeIssue(
                        perspective="TECH_TRANSFER",
                        severity="WARN",
                        flaw_title="中试/产业化项目技术成熟度 (TRL < 6) 风险未披露",
                        attack_critique="国资与产业化基金视角：TRL 低于 6 级的早期项目直接进行产业化推广容易面临工程化落地失败。",
                        patch_prescription="补充前期中试验证报告，或在方案中增加‘第一阶段：概念验证与小试中试突破’的里程碑安排。",
                    )
                )

        # Robustness calculation
        block_count = sum(1 for c in challenges if c.severity == "BLOCK")
        warn_count = sum(1 for c in challenges if c.severity == "WARN")
        robustness = max(0, 100 - (block_count * 35 + warn_count * 15))
        passed = block_count == 0

        # Auto-patching synthesis
        patched = None
        if auto_patch and len(challenges) > 0:
            patched = self._synthesize_patch(text, detected_domain, challenges)

        return ShadowChallengeReport(
            target_name=target_name,
            domain=detected_domain,
            passed=passed,
            robustness_score=robustness,
            challenges=challenges,
            patched_text=patched,
        )

    def challenge_file(
        self,
        file_path: str | Path,
        domain: str = "auto",
        auto_patch: bool = True,
    ) -> ShadowChallengeReport:
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return ShadowChallengeReport(
                target_name=str(p),
                domain=domain,
                passed=False,
                robustness_score=0,
                challenges=[
                    ChallengeIssue(
                        perspective="AUDIT_FINANCE",
                        severity="BLOCK",
                        flaw_title="目标文件不存在",
                        attack_critique=f"无法找到物理文件: {p}",
                        patch_prescription="请提供有效的方案文件路径",
                    )
                ],
            )
        content = p.read_text(encoding="utf-8")
        return self.challenge_text(content, domain=domain, target_name=str(p), auto_patch=auto_patch)

    def _synthesize_patch(self, original_text: str, domain: str, challenges: list[ChallengeIssue]) -> str:
        patch_blocks: list[str] = []
        for c in challenges:
            patch_blocks.append(
                f"> **【影子对抗合规强化补丁 — {c.perspective}】**\n> 规避缺陷: {c.flaw_title}\n> 强化声明: {c.patch_prescription}\n"
            )

        header = "\n\n## 🛡️ 影子红蓝对抗合规补强与审查批注 (Shadow Certified Addendum)\n\n"
        return original_text + header + "\n".join(patch_blocks)
