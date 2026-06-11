"""ニュース収集・分類のデータモデル（§9.8）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: str
    query_label: str  # 検索に使った銘柄名/ティッカー


@dataclass
class ClassifiedNews:
    title: str
    link: str
    related_holding: str
    category: str   # 決算/開示/マクロ/業界/その他
    implication: str  # 保有銘柄への含意
    importance: str  # 高/中/低


@dataclass
class NewsDigest:
    narrative: str  # §4 本文用の通し要約（保有銘柄への含意に翻訳済み）
    items: list[ClassifiedNews] = field(default_factory=list)
