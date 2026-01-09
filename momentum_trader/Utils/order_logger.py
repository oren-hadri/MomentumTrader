import csv
import os
from typing import Any


class OrderLogger:
    def __init__(self, filename: str = "orders_log.csv") -> None:
        self.filename = filename
        self.fieldnames = [
            'local_ts', 'side', 'price_expected', 'price_actual',
            'size_expected', 'size_actual', 'asset', 'fee', 'order_id',
            'account_btc_size', 'account_usdt_size', 'fee_rate',
            'fill_time_ms', 'order_type'
        ]
        file_exists = os.path.exists(self.filename)
        self.file = open(self.filename, mode="a", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        if not file_exists or os.stat(self.filename).st_size == 0:
            self.writer.writeheader()

    def log_order(self, order: dict[str, Any]) -> None:
        self.writer.writerow(order)
        self.file.flush()

    def close(self) -> None:
        self.file.close()

