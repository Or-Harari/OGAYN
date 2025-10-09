from __future__ import annotations
from pandas import DataFrame, Series

class BaseStrategy:
    """Abstract base class for pluggable lightweight sub-strategies."""
    name: str = "base"

    def populate_indicators(self, df: DataFrame) -> None:
        return None

    def entry_mask(self, df: DataFrame) -> Series:
        raise NotImplementedError

    def exit_mask(self, df: DataFrame) -> Series:
        raise NotImplementedError

    def required_indicators(self) -> dict:
        return {}

    def required_informatives(self) -> list:
        return []
