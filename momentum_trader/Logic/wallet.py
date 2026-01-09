import os
from enum import Enum
from typing import Any

from momentum_trader.Utils.order_logger import OrderLogger
from momentum_trader.Utils.logger import Logger


class OrderType(Enum):
    MAKER = 1
    TAKER = 2


class WalletManager:
    def __init__(
        self,
        initial_btc: float,
        initial_usdt: float,
        commission_rate_maker: float,
        commission_rate_taker: float,
        order_type: OrderType,
        log_folder: str,
        app_logger: Logger
    ) -> None:
        self.current_btc = initial_btc
        self.current_usdt = initial_usdt
        self.paid_commission = 0.0
        self.expected_commission = 0.0
        self.commission_rate_maker = commission_rate_maker
        self.commission_rate_taker = commission_rate_taker
        self.order_type = order_type
        self.commission_rate = self.commission_rate_taker
        self.executed_orders: dict[str, dict[str, Any]] = {}
        self.app_logger = app_logger
        self.order_logger = OrderLogger(os.path.join(log_folder, 'orders.csv'))

    def check_order_size(self, price: float, size_btc: float, side: str, asset: str) -> float:
        if side == 'buy':
            if not self._check_buy_order(price, size_btc, asset):
                return 0.0
            return size_btc
        elif side == 'sell':
            if not self._check_sell_order(price, size_btc, asset):
                return 0.0
            return size_btc
        else:
            exit(f'invalid side: {side}')

    def _check_buy_order(self, price: float, size_btc: float, asset: str) -> bool:
        total_cost = size_btc * price * (1 + self.commission_rate)
        if self.current_usdt < total_cost:
            self.app_logger.log_event(
                f"Insufficient funds to buy {size_btc} of {asset} at {price} per unit. "
                f"wallet: usdt {self.current_usdt} btc {self.current_btc}"
            )
            return False
        return True

    def _check_sell_order(self, price: float, size_btc: float, asset: str) -> bool:
        if self.current_btc < size_btc * (1 + self.commission_rate):
            self.app_logger.log_event(
                f"Insufficient assets to sell {size_btc} of {asset} at {price} per unit."
                f"wallet: usdt {self.current_usdt} btc {self.current_btc}"
            )
            return False
        return True

    def update_executed_order(
        self,
        local_ts: str,
        order_id: str,
        price_expected: float,
        price_actual: float,
        size_expected: float,
        size_actual: float,
        side: str,
        asset: str,
        fee: float,
        account_btc_size: float,
        account_usdt_size: float,
        order_type: str,
        fee_rate: float,
        fill_time_ms: str
    ) -> None:
        self.executed_orders[order_id] = {
            "local_ts": local_ts,
            "side": side,
            "price_expected": price_expected,
            "price_actual": price_actual,
            "size_expected": size_expected,
            "size_actual": size_actual,
            "asset": asset,
            "fee": fee,
            "order_id": order_id,
            "account_btc_size": account_btc_size,
            "account_usdt_size": account_usdt_size,
            "fee_rate": fee_rate,
            "fill_time_ms": fill_time_ms,
            "order_type": order_type
        }
        self.app_logger.log_event(f"Wallet updated, Order {order_id}: {self.executed_orders[order_id]}")
        self.order_logger.log_order(self.executed_orders[order_id])
        self.current_btc = account_btc_size
        self.current_usdt = account_usdt_size

    def get_summary(self) -> dict[str, float]:
        summary = {
            "expected_commission": self.expected_commission,
        }
        self.app_logger.log_event(f"Portfolio Summary: {summary}")
        return summary
