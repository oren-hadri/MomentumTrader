from dataclasses import dataclass


@dataclass
class TradingConfig:
    asset: str = "BTC-USDT"
    price_movement_threshold: float = 0.01
    price_resolution_minutes: int = 1
    momentum_lookback_window_minutes: int = 30
    momentum_std_threshold: float = 1.0
    order_size_factor: int = 65
    max_order_size_multiplier: int = 6
    maker_fee_rate: float = 0.0008
    taker_fee_rate: float = 0.001
    price_validation_threshold: float = 1.2
    price_adjustment_offset: float = 0.001

    @property
    def momentum_history_window_minutes(self) -> int:
        return 2 * self.momentum_lookback_window_minutes


@dataclass
class ExchangeConfig:
    base_url: str = "https://www.okx.com"
    api_prefix: str = "/api/v5"
    initial_ban_sleep_seconds: int = 60
    request_timeout_seconds: int = 10
    max_retries: int = 5
    backoff_factor: float = 0.5


DEFAULT_TRADING_CONFIG = TradingConfig()
DEFAULT_EXCHANGE_CONFIG = ExchangeConfig()
