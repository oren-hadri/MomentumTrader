from abc import ABC, abstractmethod
from typing import Any, Optional


class ExchangeClient(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> Optional[float]:
        pass

    @abstractmethod
    def get_minimum_size(self, symbol: str) -> Optional[float]:
        pass

    @abstractmethod
    def place_order(self, side: str, price: float, size: float) -> Optional[str]:
        pass

    @abstractmethod
    def check_order_status(self, order_id: str) -> tuple[str, float, float, float]:
        pass

    @abstractmethod
    def get_order_fill_details(self, order_id: str) -> Optional[tuple[str, str, str]]:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def get_account_balance(self, asset: str, account: str) -> float:
        pass

    @abstractmethod
    def get_open_orders(self, inst_type: str) -> list[dict]:
        pass

    @abstractmethod
    def close_all_orders(self) -> None:
        pass

