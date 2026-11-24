"""The Meeting-to-Action Policy, parsed from data/policy.md."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from kangaroo.config import DATA_DIR
from kangaroo.models.case import Tier

POLICY_PATH = DATA_DIR / "policy.md"

_VERSION_RE = re.compile(r"^\*\*Version (\S+) · ")
_RULE_RE = re.compile(r"^\*\*(R(\d)\.\d) · (.+?)\.\*\* (.+)$")
# A row of the "Tiers and actions" table: | T2 | Ticket | evidence | action | approval |
_TIER_RE = re.compile(r"^\| (T\d) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$")


class Rule(BaseModel):
    id: str
    tier: Tier
    name: str
    text: str


class TierInfo(BaseModel):
    """One row of the policy's tier table."""

    id: Tier
    name: str
    evidence: str
    default_action: str
    approval: str


class Policy(BaseModel):
    version: str
    rules: dict[str, Rule]
    tiers: dict[str, TierInfo]
    text: str

    def rules_for(self, tiers: set[str]) -> list[Rule]:
        return [rule for rule in self.rules.values() if rule.tier in tiers]

    def has_rule(self, rule_id: str) -> bool:
        return rule_id in self.rules


def parse_policy(markdown: str) -> Policy:
    version = ""
    rules: dict[str, Rule] = {}
    tiers: dict[str, TierInfo] = {}

    for line in markdown.splitlines():
        if match := _VERSION_RE.match(line):
            version = match.group(1)
        elif match := _RULE_RE.match(line):
            rule_id, tier_digit, name, text = match.groups()
            rules[rule_id] = Rule(id=rule_id, tier=f"T{tier_digit}", name=name, text=text)
        elif match := _TIER_RE.match(line):
            tier_id, name, evidence, action, approval = match.groups()
            tiers[tier_id] = TierInfo(
                id=tier_id, name=name, evidence=evidence, default_action=action, approval=approval
            )

    if not version or not rules or not tiers:
        raise ValueError("policy.md is missing its version line, tier table or rules")

    return Policy(version=version, rules=rules, tiers=tiers, text=markdown)


@lru_cache
def load_policy(path: Path = POLICY_PATH) -> Policy:
    return parse_policy(path.read_text(encoding="utf-8"))
