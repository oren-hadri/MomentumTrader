import logging
import os
from datetime import datetime


class Logger:
    _instance: 'Logger | None' = None

    def __new__(cls, log_file: str) -> 'Logger':
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialize(log_file)
        return cls._instance

    def _initialize(self, log_file: str) -> None:
        self.log_file = log_file
        self.logger = logging.getLogger("GlobalLogger")
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        file_handler = logging.FileHandler(self.log_file, mode='a')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        if not self.logger.hasHandlers():
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

        self._write_start_header()

    def _write_start_header(self) -> None:
        if not os.path.exists(self.log_file) or os.stat(self.log_file).st_size == 0:
            with open(self.log_file, 'a') as log:
                log.write(f"\n{'='*50}\n")
                log.write(f"LOG START - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log.write(f"{'='*50}\n\n")

        self.logger.info("===== NEW SESSION STARTED =====")

    def log_event(self, message: str) -> None:
        self.logger.info(message)

