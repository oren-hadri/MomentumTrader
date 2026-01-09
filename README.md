## Momentum Trader

This repository contains a **sample / demonstration project** designed to showcase the design and implementation of a conservative algorithmic trading system.

The system was run on the **OKX exchange**, trading **a single asset (BTC-USDT)** using a **risk-constrained, conservative strategy**. The primary goal of the project was **risk reduction and stability**, rather than maximizing directional exposure or outperforming the underlying market.

Specifically:

* The strategy trades a single market.
* Position sizing and execution are deliberately conservative.
* Trading activity is throttled during periods of extreme momentum.
* The objective is to achieve **consistent, steady profitability with lower variance**, rather than market beta capture.

The results illustrate that the cumulative profit curve exhibits **significantly lower volatility than the underlying BTC price**, while still producing **positive and consistent returns over time**. This indicates a strategy that is **largely independent of overall market direction**.

This project should be viewed primarily as a **proof of concept and validation of a trading hypothesis**, as well as a demonstration of trading infrastructure, system design, and risk-aware execution logic — not as a production-ready or profit-maximizing trading system.

---

## Results

The following results were produced by running the strategy on **OKX**, trading a **single BTC-USDT market**.

### Cumulative PnL (%) vs BTC

![Cumulative PnL % vs BTC](assets/cumulative_pnl_percent_vs_btc.png)

This chart compares the strategy’s cumulative return to the BTC price movement over the same period. The strategy delivers positive absolute returns with **significantly lower volatility than BTC itself**. During strong directional market moves, the strategy intentionally underperforms the benchmark, reflecting its conservative, risk-aware design rather than directional exposure.

### Cumulative PnL (USD)

![Cumulative PnL (USD)](assets/cumulative_pnl_usd.png)

The cumulative PnL curve in USD shows **steady, incremental profit generation with relatively low variance**, punctuated by limited drawdowns. This behavior supports the thesis that the strategy’s performance is **largely independent of overall market direction**.

Overall, these results serve as a **proof of concept**, validating the hypothesis that a conservative execution and momentum-filtered approach can reduce risk while maintaining consistent profitability.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              TradingBot                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Trade Logic Loop                            │   │
│  │  1. Fetch price → 2. Calculate momentum → 3. Check extreme momentum │   │
│  │  │  4. Check order status → 5. Place new orders → 6. Sleep & repeat │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────────┬─────────────────────────┬───────────────────────┬──────────┘
                │                         │                       │
                ▼                         ▼                       ▼
┌───────────────────────┐   ┌─────────────────────┐   ┌───────────────────────┐
│    ExchangeClient     │   │    WalletManager    │   │       Loggers         │
│    (Abstract Base)    │   │                     │   │                       │
├───────────────────────┤   ├─────────────────────┤   ├───────────────────────┤
│ • get_price()         │   │ • check_order_size()│   │ • Logger (app.log)    │
│ • place_order()       │   │ • update_executed   │   │ • PriceLogger         │
│ • check_order_status()│   │   _order()          │   │ • OrderLogger         │
│ • cancel_order()      │   │ • Balance tracking  │   │                       │
│ • get_account_balance │   │                     │   │                       │
└───────────┬───────────┘   └─────────────────────┘   └───────────────────────┘
            │
            ▼
┌───────────────────────┐
│      OKXClient        │
│   (Implementation)    │
├───────────────────────┤
│ • API authentication  │
│ • Request signing     │
│ • Rate limit handling │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│      APIClient        │
├───────────────────────┤
│ • HTTP session        │
│ • Retry logic         │
│ • Error handling      │
└───────────┬───────────┘
            │
            ▼
    ┌───────────────┐
    │   OKX API     │
    └───────────────┘
```

## Disclaimer

This is an educational and demonstration project only. Use at your own risk. Cryptocurrency trading involves significant risk of loss.
