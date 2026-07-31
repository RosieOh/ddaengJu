# -*- coding: utf-8 -*-
"""config.json 읽기/쓰기.

설정의 단일 출처는 프로젝트 루트의 config.json 이다.
웹 UI 에서 저장해도 이 파일에 쓰이므로, 메모장으로 직접 고쳐도 된다.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .collector import Target

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "data" / "ranks.db"

DEFAULT_CONFIG: dict = {
    "keywords": ["중고차팔기", "내차팔기", "내차시세조회"],
    "targets": [
        {"name": "엔카", "patterns": ["엔카", "encar"]},
        {"name": "헤이딜러", "patterns": ["헤이딜러", "heydealer"]},
        {"name": "K다이렉트카", "patterns": ["다이렉트카", "kdirectcar"]},
        {"name": "현대글로비스오토벨", "patterns": ["오토벨", "autobell"]},
    ],
    "repeat": 3,
    "max_workers": 5,
    "max_pages": 10,
    "schedule_enabled": True,
    "schedule_minute": 0,
}

_lock = threading.Lock()


@dataclass
class AppConfig:
    keywords: list[str] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    repeat: int = 3
    max_workers: int = 5
    max_pages: int = 10
    schedule_enabled: bool = True
    schedule_minute: int = 0

    @property
    def primary_target(self) -> Target | None:
        return self.targets[0] if self.targets else None

    def to_dict(self) -> dict:
        return {
            "keywords": self.keywords,
            "targets": [{"name": t.name, "patterns": list(t.patterns)} for t in self.targets],
            "repeat": self.repeat,
            "max_workers": self.max_workers,
            "max_pages": self.max_pages,
            "schedule_enabled": self.schedule_enabled,
            "schedule_minute": self.schedule_minute,
        }


def _coerce(raw: dict) -> AppConfig:
    merged = {**DEFAULT_CONFIG, **(raw or {})}
    targets = [
        Target(name=t["name"], patterns=list(t.get("patterns") or [t["name"]]))
        for t in merged.get("targets", [])
        if t.get("name")
    ]
    return AppConfig(
        keywords=[k.strip() for k in merged.get("keywords", []) if str(k).strip()],
        targets=targets,
        repeat=max(1, min(5, int(merged.get("repeat", 3)))),
        max_workers=max(1, min(10, int(merged.get("max_workers", 5)))),
        max_pages=max(1, min(30, int(merged.get("max_pages", 10)))),
        schedule_enabled=bool(merged.get("schedule_enabled", True)),
        schedule_minute=max(0, min(59, int(merged.get("schedule_minute", 0)))),
    )


def load() -> AppConfig:
    with _lock:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return _coerce(DEFAULT_CONFIG)
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 설정 파일이 깨져도 서비스는 떠야 한다.
            raw = {}
        return _coerce(raw)


def save(cfg: AppConfig) -> AppConfig:
    with _lock:
        CONFIG_PATH.write_text(
            json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return cfg


def parse_keywords(text: str) -> list[str]:
    """'중고차팔기, 내차팔기' 또는 줄바꿈/탭 구분 입력을 리스트로 바꾼다.

    엑셀에서 셀 여러 개를 그대로 복사해 붙여넣어도 인식되도록
    콤마·줄바꿈·탭을 모두 구분자로 취급하고 중복은 순서를 지키며 제거한다.
    """
    if not text:
        return []
    parts = [p.strip().strip('"').strip("'") for p in re_split(text)]
    seen: dict[str, None] = {}
    for p in parts:
        if p:
            seen.setdefault(p, None)
    return list(seen)


def re_split(text: str) -> list[str]:
    import re

    return re.split(r"[,\n\r\t;]+", text)
