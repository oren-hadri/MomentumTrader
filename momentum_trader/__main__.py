import os

from momentum_trader.config import TradingConfig
from momentum_trader.Logic.trading_bot import TradingBot


def main() -> None:
    config = TradingConfig()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_folder = os.path.join(project_root, 'logs')
    bot = TradingBot(logs_folder, config=config)
    bot.run()


if __name__ == "__main__":
    main()

