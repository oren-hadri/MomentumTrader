import os
import time
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import numpy as np

from momentum_trader.config import TradingConfig, DEFAULT_TRADING_CONFIG
from momentum_trader.Logic.wallet import WalletManager, OrderType
from momentum_trader.Clients.okx_client import OKXClient
from momentum_trader.Clients.base_client import ExchangeClient
from momentum_trader.Utils.logger import Logger
from momentum_trader.Utils.price_logger import PriceLogger

NOT_ENOUGH_BALANCE = -55


class TradingBot:
    class OrderStatus(Enum):
        FILLED = 1
        WAITING = 2
        CANCELED = 3
        NOT_ENOUGH_BALANCE = 4

    @dataclass
    class OrderExecutionResult:
        order_status: 'TradingBot.OrderStatus'
        executed_order_id: int
        executed_price: float
        executed_size: float
        executed_side: str
        fill_time_ms: str

    def __init__(
        self,
        logs_folder: str,
        config: TradingConfig = DEFAULT_TRADING_CONFIG,
        exchange_client: Optional[ExchangeClient] = None
    ) -> None:
        self.config = config
        self.expected_sell_size: float = 0.0
        self.expected_buy_size: float = 0.0
        self.expected_buy_price: float = 0.0
        self.expected_sell_price: float = 0.0
        self.last_price: float = 0.0
        self.logger = Logger(os.path.join(logs_folder, 'app.log'))
        self.params_filename = os.path.join(logs_folder, 'params.json')
        self.asset = config.asset

        if exchange_client:
            self.exchange_client = exchange_client
        else:
            self.exchange_client = OKXClient(self.asset, app_logger=self.logger)

        account_btc_size, account_usdt_size = self._get_account_balance()
        self.min_size = self.exchange_client.get_minimum_size(self.asset) or 0.00001
        self.order_start_size = config.order_size_factor * self.min_size
        self.order_type = OrderType.MAKER

        self.wallet = WalletManager(
            account_btc_size,
            account_usdt_size,
            config.maker_fee_rate,
            config.taker_fee_rate,
            self.order_type,
            log_folder=logs_folder,
            app_logger=self.logger
        )
        self._on_start(self.order_start_size, self.order_start_size)
        self.usdt_size = account_usdt_size

        self.log_event = self.logger.log_event
        self.log_event(f"Last BTC Price: {self.last_price}")
        self.price_logger = PriceLogger(logs_folder)

        self.price_history: list[dict] = []
        self.momentum_history: list[dict] = []

        self.buy_order_id: int = 0
        self.sell_order_id: int = 0
        self.buy_size_btc: float = self.order_start_size
        self.sell_size_btc: float = self.order_start_size

    def _get_account_balance(self) -> tuple[float, float]:
        account_btc_size = float(self.exchange_client.get_account_balance(asset='BTC'))
        account_usdt_size = float(self.exchange_client.get_account_balance(asset='USDT'))
        return account_btc_size, account_usdt_size

    def _is_valid_number(self, price: float) -> bool:
        return isinstance(price, (int, float)) and not isinstance(price, bool)

    def _is_valid_price(self, price: float) -> bool:
        return self._is_valid_number(price) and abs(price - self.last_price) < self.last_price * self.config.price_validation_threshold

    def _add_price_to_history(self, price: float, timestamp: datetime) -> None:
        self.price_history.append({'timestamp': timestamp, 'price': price})
        cutoff_time = timestamp - timedelta(
            minutes=self.config.momentum_history_window_minutes + self.config.momentum_lookback_window_minutes
        )
        self.price_history = [p for p in self.price_history if p['timestamp'] >= cutoff_time]

    def _calculate_current_momentum(self, current_price: float, current_timestamp: datetime) -> float:
        if len(self.price_history) == 0:
            return 0.0

        lookback_time = current_timestamp - timedelta(minutes=self.config.momentum_lookback_window_minutes)
        recent_data = [p for p in self.price_history if lookback_time <= p['timestamp'] < current_timestamp]

        if len(recent_data) == 0:
            return 0.0

        start_price = recent_data[0]['price']
        start_time = recent_data[0]['timestamp']
        time_diff = (current_timestamp - start_time).total_seconds() / 60

        if time_diff > 0:
            price_change_pct = ((current_price - start_price) / start_price) * 100
            momentum = price_change_pct / time_diff
        else:
            momentum = 0.0

        return momentum

    def _is_extreme_momentum(self, current_momentum: float, current_timestamp: datetime) -> bool:
        min_required_points = self.config.momentum_history_window_minutes / self.config.price_resolution_minutes - 1

        lookback_time = current_timestamp - timedelta(minutes=self.config.momentum_history_window_minutes)
        recent_momentum_list = [m['momentum'] for m in self.momentum_history if m['timestamp'] >= lookback_time]
        recent_momentum_list.append(current_momentum)

        if len(recent_momentum_list) < min_required_points:
            return False

        recent_momentum = np.array(recent_momentum_list)
        mean_momentum = np.mean(recent_momentum)
        std_momentum = np.std(recent_momentum)

        if std_momentum > 0:
            high_threshold = mean_momentum + self.config.momentum_std_threshold * std_momentum
            low_threshold = mean_momentum - self.config.momentum_std_threshold * std_momentum
        else:
            high_threshold = mean_momentum + 0.01
            low_threshold = mean_momentum - 0.01

        is_extreme = current_momentum > high_threshold or current_momentum < low_threshold
        return is_extreme

    def _add_momentum_to_history(self, momentum: float, timestamp: datetime) -> None:
        self.momentum_history.append({'timestamp': timestamp, 'momentum': momentum})
        cutoff_time = timestamp - timedelta(minutes=self.config.momentum_history_window_minutes)
        self.momentum_history = [m for m in self.momentum_history if m['timestamp'] >= cutoff_time]

    def _trade_logic(self) -> None:
        while True:
            current_price = self.exchange_client.get_price(self.asset)
            if current_price is None:
                time.sleep(10)
                continue

            current_timestamp = datetime.now()
            local_ts = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            self.price_logger.log_price(price=current_price, timestamp=local_ts)

            if not self._is_valid_price(current_price):
                self.log_event(f"{datetime.now()} - Error, price value looks wrong: {current_price}")
                time.sleep(10)
                continue

            self._add_price_to_history(current_price, current_timestamp)
            current_momentum = self._calculate_current_momentum(current_price, current_timestamp)

            is_extreme = self._is_extreme_momentum(current_momentum, current_timestamp)
            self._add_momentum_to_history(current_momentum, current_timestamp)

            buy_result = self._check_order_status(
                self.buy_order_id, 'buy', self.expected_buy_price, self.expected_buy_size, local_ts
            )
            order_buy_executed = buy_result.order_status in {
                TradingBot.OrderStatus.FILLED,
                TradingBot.OrderStatus.CANCELED
            }

            sell_result = self._check_order_status(
                self.sell_order_id, 'sell', self.expected_sell_price, self.expected_sell_size, local_ts
            )
            order_sell_executed = sell_result.order_status in {
                TradingBot.OrderStatus.FILLED,
                TradingBot.OrderStatus.CANCELED
            }

            orders: list[TradingBot.OrderExecutionResult] = []
            if order_buy_executed:
                orders.append(buy_result)
            if order_sell_executed:
                if sell_result.fill_time_ms < buy_result.fill_time_ms:
                    orders.insert(0, sell_result)
                else:
                    orders.append(sell_result)

            for order in orders:
                if order.executed_order_id and order.executed_order_id != 0:
                    self._adjust_order_sizes(order.executed_side)
                    self.last_price = order.executed_price

            if order_buy_executed or order_sell_executed:
                self._close_open_orders()
                if not is_extreme:
                    self.sell_order_id, self.buy_order_id = self._set_new_orders(current_price)

            elif is_extreme:
                self._close_open_orders()

            self._check_wallet_limits(current_price, self.sell_order_id, self.buy_order_id)

            time.sleep(60 * self.config.price_resolution_minutes)

    def _check_wallet_limits(self, current_price: float, order_sell_id: int, order_buy_id: int) -> None:
        if order_sell_id == NOT_ENOUGH_BALANCE:
            if current_price > self.last_price * (1 + self.config.price_movement_threshold):
                self.log_event(
                    f"*** No BTC to sell, cancel all orders, and set last price from {self.last_price} to {current_price}"
                )
                self.last_price = current_price
                self._close_open_orders()
        if order_buy_id == NOT_ENOUGH_BALANCE:
            if current_price < self.last_price * (1 - self.config.price_movement_threshold):
                self.log_event(
                    f"*** No USDT to buy, cancel all orders, and set last price from {self.last_price} to {current_price}"
                )
                self.last_price = current_price
                self._close_open_orders()

    def _close_open_orders(self) -> None:
        self.exchange_client.close_all_orders()
        self.buy_order_id = 0
        self.sell_order_id = 0

    def _set_new_orders(self, current_price: float) -> tuple[int, int]:
        sell_order_id = 0
        little_below_current_price = round(current_price * (1 - self.config.price_adjustment_offset), 2)
        self.expected_sell_price = round(self.last_price * (1 + self.config.price_movement_threshold), 2)
        self.expected_sell_size = max(self.expected_sell_price, little_below_current_price)
        self.expected_sell_size = self.wallet.check_order_size(
            self.expected_sell_price, self.sell_size_btc, "sell", self.asset
        )
        if self.expected_sell_size > 0:
            result = self.exchange_client.place_order("sell", self.expected_sell_price, self.expected_sell_size)
            sell_order_id = int(result) if result else 0
        if not sell_order_id:
            self.log_event("Failed to place sell order..")
            sell_order_id = NOT_ENOUGH_BALANCE

        buy_order_id = 0
        little_above_current_price = round(current_price * (1 + self.config.price_adjustment_offset), 2)
        self.expected_buy_price = round(self.last_price * (1 - self.config.price_movement_threshold), 2)
        self.expected_buy_price = min(self.expected_buy_price, little_above_current_price)
        self.expected_buy_size = self.wallet.check_order_size(
            self.expected_buy_price, self.buy_size_btc, "buy", self.asset
        )
        if self.expected_buy_size > 0:
            result = self.exchange_client.place_order("buy", self.expected_buy_price, self.expected_buy_size)
            buy_order_id = int(result) if result else 0
        if not buy_order_id:
            self.log_event("Failed to place buy order..")
            buy_order_id = NOT_ENOUGH_BALANCE

        return sell_order_id, buy_order_id

    def _check_order_status(
        self,
        order_id: int,
        side: str,
        expected_price: float,
        expected_size: float,
        local_ts: str
    ) -> 'TradingBot.OrderExecutionResult':
        executed_order_id = 0
        executed_price = 0.0
        executed_size = 0.0
        executed_fee = 0.0
        order_status = self.OrderStatus.CANCELED
        fill_time_ms = '2111-01-01 00:00:00 UTC'

        if order_id == NOT_ENOUGH_BALANCE:
            return TradingBot.OrderExecutionResult(
                self.OrderStatus.NOT_ENOUGH_BALANCE,
                order_id,
                executed_price,
                executed_size,
                '',
                fill_time_ms
            )

        if not order_id:
            return TradingBot.OrderExecutionResult(
                order_status,
                executed_order_id,
                executed_price,
                executed_size,
                '',
                fill_time_ms
            )

        status, price, size, fee = self.exchange_client.check_order_status(str(order_id))

        if status == "filled" or status == "partially_filled":
            self.log_event(f"order {order_id} was filled by exchange with price {price}, size {size}, fee {fee}.")
            executed_order_id = order_id
            executed_price = price
            executed_size = size
            executed_fee = fee
            order_status = TradingBot.OrderStatus.FILLED
        elif status == "canceled":
            order_status = TradingBot.OrderStatus.CANCELED
        elif status == "failed":
            order_status = TradingBot.OrderStatus.CANCELED
        else:
            order_status = TradingBot.OrderStatus.WAITING

        if order_status == TradingBot.OrderStatus.FILLED:
            fee_rate: float = 0.0
            order_type = 'NA'
            if executed_price * executed_size > 0:
                fee_rate = (executed_fee / (executed_price * executed_size)) * 100
                order_type = 'Taker' if fee_rate > 0.08 else 'Maker'
            order_details = self.exchange_client.get_order_fill_details(str(executed_order_id))
            if not order_details:
                self.log_event(f"Order {executed_order_id} was not found at exchange response!")
            else:
                order_type, fee_rate_str, fill_time_ms = order_details
                fee_rate = float(fee_rate_str) if fee_rate_str != 'N/A' else 0.0

            if executed_order_id and executed_order_id != 0:
                account_btc_size, account_usdt_size = self._get_account_balance()
                self.wallet.update_executed_order(
                    local_ts=local_ts,
                    order_id=str(executed_order_id),
                    price_expected=expected_price,
                    price_actual=executed_price,
                    size_expected=expected_size,
                    size_actual=executed_size,
                    side=side,
                    asset=self.asset,
                    fee=executed_fee,
                    account_btc_size=account_btc_size,
                    account_usdt_size=account_usdt_size,
                    order_type=order_type,
                    fee_rate=fee_rate,
                    fill_time_ms=fill_time_ms
                )

                self._save_runtime_params()

        return TradingBot.OrderExecutionResult(
            order_status,
            executed_order_id,
            executed_price,
            executed_size,
            side,
            fill_time_ms
        )

    def _adjust_order_sizes(self, executed_side: str) -> None:
        if executed_side == "buy":
            self.buy_size_btc += self.buy_size_btc
            self.buy_size_btc = min(self.config.max_order_size_multiplier * self.order_start_size, self.buy_size_btc)
            self.sell_size_btc = self.order_start_size
        elif executed_side == "sell":
            self.sell_size_btc += self.sell_size_btc
            self.sell_size_btc = min(self.config.max_order_size_multiplier * self.order_start_size, self.sell_size_btc)
            self.buy_size_btc = self.order_start_size
        self.log_event(
            f"(executed_side: {executed_side})  Updated Buy Size: {self.buy_size_btc:.5f}, Sell Size: {self.sell_size_btc:.5f}"
        )

    def _save_runtime_params(self) -> None:
        parameters = {
            "last_price": self.last_price,
            "buy_size_btc": self.buy_size_btc,
            "sell_size_btc": self.sell_size_btc,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
        }
        with open(self.params_filename, "w") as file:
            json.dump(parameters, file, indent=4)

    def _on_close(self) -> None:
        self._save_runtime_params()
        self.price_logger.close()

    def _on_start(self, default_buy_size_btc: float, default_sell_size_btc: float) -> None:
        if os.path.exists(self.params_filename):
            with open(self.params_filename, "r") as file:
                loaded_parameters = json.load(file)
                if 'last_price' in loaded_parameters:
                    self.last_price = loaded_parameters["last_price"]
                else:
                    self.log_event("ERROR: last_price is missing from parameters file")
                    self.last_price = self.exchange_client.get_price(self.asset) or 0.0

                self.buy_size_btc = loaded_parameters.get('buy_size_btc', default_buy_size_btc)
                self.sell_size_btc = loaded_parameters.get('sell_size_btc', default_sell_size_btc)
                self.buy_order_id = loaded_parameters.get('buy_order_id', 0)
                self.sell_order_id = loaded_parameters.get('sell_order_id', 0)
        else:
            self.log_event(f"ERROR: Missing parameters file: {self.params_filename}")
            self.last_price = self.exchange_client.get_price(self.asset) or 0.0
            self.buy_size_btc = default_buy_size_btc
            self.sell_size_btc = default_sell_size_btc
            self.buy_order_id = 0
            self.sell_order_id = 0

    def run(self) -> None:
        try:
            self._trade_logic()
        except KeyboardInterrupt:
            self._on_close()
            self.log_event("Bot stopped by user. Exiting gracefully.")
