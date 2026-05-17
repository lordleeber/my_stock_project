from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    """台灣股市交易成本設定。

    commission_rate: 買賣雙邊各收一次，預設 0.1425‰（券商手續費，可打折）
    tax_rate: 僅賣出時收取，預設 0.3‰（證券交易稅）
    """

    commission_rate: float = 0.001425
    tax_rate: float = 0.003
