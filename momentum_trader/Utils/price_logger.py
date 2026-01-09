import csv
import os


class PriceLogger:
    def __init__(self, logs_folder: str, filename: str = "price_data.csv") -> None:
        self.filename = os.path.join(logs_folder, filename)
        self.file = open(self.filename, mode="a", newline="")
        self.writer = csv.writer(self.file)
        if self.file.tell() == 0:
            self.writer.writerow(["Timestamp", "Price"])

    def log_price(self, price: float, timestamp: str) -> None:
        self.writer.writerow([timestamp, price])
        self.file.flush()

    def close(self) -> None:
        self.file.close()

