import time
import hmac
import hashlib
import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import requests

from momentum_trader.Clients.api_client import APIClient
from momentum_trader.Clients.base_client import ExchangeClient
from momentum_trader.Utils.logger import Logger
from momentum_trader.config import ExchangeConfig, DEFAULT_EXCHANGE_CONFIG


class OKXClient(ExchangeClient):
    def __init__(self, asset: str, app_logger: Logger, config: ExchangeConfig = DEFAULT_EXCHANGE_CONFIG) -> None:
        self.asset = asset
        self.config = config
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        secrets_file = os.path.join(project_root, "secrets/okx_secrets.txt")
        secrets = self._load_secrets(secrets_file)
        self.api_key = secrets.get("OKX_API_KEY")
        self.secret_key = secrets.get("OKX_SECRET_KEY")
        self.passphrase = secrets.get("OKX_PASSPHRASE")
        self.logger = app_logger
        self.log_event = self.logger.log_event
        if not self.api_key or not self.secret_key or not self.passphrase:
            self.log_event("Error: Missing API credentials!")
            exit(1)
        self.prefix_endpoint = config.api_prefix
        self.ban_sleep_time = config.initial_ban_sleep_seconds
        self.api_client = APIClient(
            base_url=config.base_url,
            prefix_endpoint=self.prefix_endpoint,
            config=config
        )

    def _get_utc_timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def get_account_balance(self, asset: str = 'BTC', account: str = 'trading') -> float:
        request_path = ''
        if 'trading' in account:
            request_path = f"/account/balance?ccy={asset}"
        if 'funding' in account:
            request_path = f"/asset/balances?ccy={asset}"
        data = self._send_request(method="GET", endpoint=request_path)

        if 'funding' in account:
            if "data" in data and data["data"]:
                asset_balance = data["data"][0].get("availBal", "0")
                self.log_event(f"Available {asset} Balance: {asset_balance} {asset}")
                return float(asset_balance)
        if 'trading' in account:
            if "data" in data and data["data"]:
                if "details" in data["data"][0]:
                    if "availBal" in data["data"][0]["details"][0]:
                        asset_balance = data["data"][0]["details"][0].get("availBal", "0")
                        self.log_event(f"Available Balance: {asset_balance} {asset}")
                        return float(asset_balance)
        self.log_event(f"Failed to fetch balance: {data}")
        return 0.0

    def _load_secrets(self, filename: str) -> dict[str, str]:
        secrets: dict[str, str] = {}
        try:
            with open(filename, "r") as file:
                for line in file:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        secrets[key] = value
        except FileNotFoundError:
            exit(1)
        return secrets

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = timestamp + method + request_path + body
        mac = hmac.new(bytes(self.secret_key, encoding="utf-8"), bytes(message, encoding="utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _send_request(self, method: str, endpoint: str, body: Optional[dict] = None) -> dict[str, Any]:
        body_str = json.dumps(body) if body else ""
        headers = self._get_headers(method=method, request_path=f"{self.prefix_endpoint}{endpoint}", body=body_str)
        response = self.api_client.send_request(
            method=method,
            endpoint=endpoint,
            body=body,
            headers=headers
        )
        if isinstance(response, dict) and 'error' in response and 'Max retries exceeded' in str(response.get('error', '')):
            self.log_event(f"Warning: Exchange ban!, sleeping for {self.ban_sleep_time} seconds")
            time.sleep(self.ban_sleep_time)
            self.ban_sleep_time = 2 * self.ban_sleep_time
        else:
            self.ban_sleep_time = self.config.initial_ban_sleep_seconds
        return response

    def get_price(self, symbol: str = 'BTC-USDT') -> Optional[float]:
        response = self._send_request("GET", f"/market/ticker?instId={symbol}")
        return float(response["data"][0]["last"]) if "data" in response else None

    def get_minimum_size(self, symbol: str = 'BTC-USDT') -> Optional[float]:
        url = f"{self.config.base_url}{self.config.api_prefix}/public/instruments?instType=SPOT"
        response = requests.get(url).json()

        if "data" in response:
            for instrument in response["data"]:
                if instrument["instId"] == symbol:
                    return float(instrument["minSz"])
        return None

    def place_order(self, side: str, price: float, size: float) -> Optional[str]:
        body = {
            "instId": self.asset,
            "tdMode": "cash",
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(Decimal(str(size))),
            "tgtCcy": "quote_ccy"
        }

        response = self._send_request("POST", "/trade/order", body)
        if "data" in response:
            order_id = response["data"][0]["ordId"]
            if order_id:
                return order_id
        self.log_event(f"Failed to place order {body}, response: {response}")
        return None

    def check_order_status(self, order_id: str) -> tuple[str, float, float, float]:
        response = self._send_request("GET", f"/trade/order?ordId={order_id}&instId=BTC-USDT")
        if "data" in response and len(response["data"]) > 0:
            response_size = float(response["data"][0]["accFillSz"])
            response_price = 0.0
            fee = abs(float(response["data"][0]["fee"]))
            if response_size > 0:
                response_price = float(response["data"][0]["avgPx"])
            return response["data"][0]["state"], response_price, response_size, fee
        return "failed", 0.0, 0.0, 0.0

    def get_order_fill_details(self, order_id: str) -> Optional[tuple[str, str, str]]:
        try:
            response = self._send_request("GET", f"/trade/fills?ordId={order_id}")
            if "data" in response and len(response["data"]) > 0:
                trade = response["data"][0]
                fee_rate = trade.get("feeRate", "N/A")
                fill_time_ms = trade.get("fillTime", "N/A")
                exec_type = trade.get("execType", "N/A")

                fill_time = "N/A"
                if fill_time_ms != "N/A":
                    fill_time = datetime.fromtimestamp(int(fill_time_ms) / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

                order_type = "Maker" if exec_type == "M" else "Taker" if exec_type == "T" else "unknown"
                return order_type, fee_rate, fill_time
            else:
                self.log_event(f"No trade details found for order {order_id}")
                return None
        except Exception as e:
            self.log_event(f"Error fetching order {order_id} details: {str(e)}")
            return None

    def cancel_order(self, order_id: str, symbol: str = 'BTC-USDT') -> dict:
        body = {"instId": symbol, "ordId": order_id}
        response = self._send_request("POST", "/trade/cancel-order", body)
        return response

    def _get_headers(self, method: str, request_path: str, body: str = "") -> dict[str, str]:
        timestamp = str(self._get_utc_timestamp())
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self._generate_signature(timestamp, method, request_path, body),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

    def get_open_orders(self, inst_type: str = "SPOT") -> list[dict]:
        response = self._send_request(method="GET", endpoint="/trade/orders-pending")
        if int(response['code']) == 0:
            return response['data']
        else:
            self.log_event(f'Failed fetching open orders: {response["msg"]}')
            return []

    def close_all_orders(self) -> None:
        orders = self.get_open_orders()
        if not orders:
            return
        for order in orders:
            order_id = order["ordId"]
            inst_id = order["instId"]
            self.cancel_order(order_id, inst_id)
