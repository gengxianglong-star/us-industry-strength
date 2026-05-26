"""Pydantic models for web-editable configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WeightsConfig(BaseModel):
    week: float = Field(ge=0, description="1周权重")
    month: float = Field(ge=0, description="1月权重")
    quarter: float = Field(ge=0, description="3月权重")
    half: float = Field(ge=0, description="6月权重")
    year: float = Field(ge=0, description="1年权重")


class ThresholdsConfig(BaseModel):
    tier_a_score: float = Field(ge=0, le=1)
    tier_b_score: float = Field(ge=0, le=1)
    core_rank_max: int = Field(ge=1)
    max_rank_spread: int = Field(ge=0)
    top_list_count: int = Field(default=10, ge=1)
    acceleration_rank_delta: int = Field(ge=0)
    pullback_midterm_rank_max: int = Field(ge=1)
    pullback_week_rank_min: int = Field(ge=1)


class StockFiltersConfig(BaseModel):
    price_above_sma20: str = "ta_sma20_pa"
    sma20_above_sma50: str = "ta_sma50_sb20"
    dollar_volume_min: str = "sh_curvol_ousd100000"
    eps_growth_qoq_min: str = "fa_epsqoq_o10"
    sales_growth_qoq_min: str = "fa_salesqoq_o10"


class StockRsConfig(BaseModel):
    request_timeout_seconds: int = Field(default=20, ge=5, le=120)
    max_workers: int = Field(default=24, ge=4, le=64)
    min_price_rows: int = Field(default=260, ge=120, le=1000)
    save_price_history: bool = False
    incremental_mode: bool = True
    prefer_stooq: bool = False
    tier_a_score: float = Field(default=0.8, ge=0, le=1)
    tier_b_score: float = Field(default=0.65, ge=0, le=1)
    cross_top_percent: float = Field(default=0.1, ge=0.01, le=1.0)
    universe_cap: int = Field(default=0, ge=0, le=12000)
    new_stock_enabled: bool = True


class ConfigUpdate(BaseModel):
    weights: WeightsConfig
    thresholds: ThresholdsConfig
    stock_filters: StockFiltersConfig
    stock_rs: StockRsConfig

    def to_payload(self) -> dict:
        return {
            "weights": self.weights.model_dump(),
            "thresholds": self.thresholds.model_dump(),
            "stock_filters": self.stock_filters.model_dump(),
            "stock_rs": self.stock_rs.model_dump(),
        }
