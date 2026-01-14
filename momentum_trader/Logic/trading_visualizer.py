"""
Trading Statistics Visualizer

Visualizes trading activity with three synchronized plots:
1. Price chart with buy/sell order markers
2. Momentum indicator with adaptive thresholds
3. Cumulative PnL (realized + unrealized)
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl

# Configure matplotlib backend for interactive plotting
mpl.use('macosx')

# =============================================================================
# CONFIGURATION - Adjust these values for your analysis
# =============================================================================

# Filter data starting from this timestamp (set to None to include all data)
CUTOFF_DATE = pd.Timestamp("<YYYY-MM-DD HH:MM:SS>")

# Set to True for full analysis (3 plots), False for price-only view
FULL_PLOT = True

# Momentum calculation parameters
PRICE_RESOLUTION_MINUTES = 10      # Time interval between price samples
MOMENTUM_LOOKBACK_MINUTES = 30     # Window for momentum calculation
MOMENTUM_STD_THRESHOLD = 1.0       # Standard deviations for extreme detection

# Derived constant
MOMENTUM_HISTORY_MINUTES = 2 * MOMENTUM_LOOKBACK_MINUTES

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================


def read_csv_safely(csv_filename, parse_dates):
    """Read CSV file without holding it open."""
    try:
        df = pd.read_csv(csv_filename, parse_dates=[parse_dates])
        return df
    except Exception as e:
        print(f"Error reading {csv_filename}: {e}")
        return None


def clean_price_data(df_prices):
    # Convert 'Timestamp' to datetime, invalid values become NaT
    df_prices['Timestamp'] = pd.to_datetime(df_prices['Timestamp'], errors='coerce')
    # Convert 'Price' to numeric, invalid values become NaN
    df_prices['Price'] = pd.to_numeric(df_prices['Price'], errors='coerce')
    # Remove rows with invalid timestamps or prices
    df_cleaned = df_prices.dropna()
    return df_cleaned


def read_price_data(price_file):
    df_prices = read_csv_safely(price_file, parse_dates='Timestamp')
    df_prices = clean_price_data(df_prices)
    if df_prices is None or df_prices.empty:
        print("No price data available.")
        return None
    return df_prices


# =============================================================================
# MOMENTUM ANALYSIS FUNCTIONS
# =============================================================================


def calculate_price_momentum(df: pd.DataFrame, lookback_minutes: int = MOMENTUM_LOOKBACK_MINUTES) -> list:
    """
    Calculate price momentum as percentage change per minute.
    
    Momentum = (price_change_percent) / (time_elapsed_minutes)
    
    Args:
        df: DataFrame with 'Timestamp' and 'Price' columns
        lookback_minutes: Time window for momentum calculation
        
    Returns:
        List of momentum values aligned with input DataFrame rows
    """
    momentum_series = []
    
    for i in range(len(df)):
        current_time = df.iloc[i]["Timestamp"]
        current_price = df.iloc[i]["Price"]
        
        # Get data within lookback window
        lookback_data = df[df["Timestamp"] < current_time]
        time_window = current_time - pd.Timedelta(minutes=lookback_minutes)
        recent_data = lookback_data[lookback_data["Timestamp"] >= time_window]
        
        if len(recent_data) > 0:
            start_price = recent_data.iloc[0]["Price"]
            start_time = recent_data.iloc[0]["Timestamp"]
            time_diff = (current_time - start_time).total_seconds() / 60
            
            if time_diff > 0:
                price_change_pct = ((current_price - start_price) / start_price) * 100
                momentum = price_change_pct / time_diff
            else:
                momentum = 0.0
        else:
            momentum = 0.0
        
        momentum_series.append(momentum)
    
    return momentum_series


def detect_momentum_extremes(
    df: pd.DataFrame,
    history_window_minutes: int = MOMENTUM_HISTORY_MINUTES,
    threshold_std: float = MOMENTUM_STD_THRESHOLD
) -> pd.DataFrame:
    """
    Detect momentum extremes using adaptive thresholds based on rolling statistics.
    
    Thresholds are calculated as: mean ± (threshold_std × standard_deviation)
    
    Args:
        df: DataFrame with 'Timestamp' and 'Momentum' columns
        history_window_minutes: Rolling window for statistics calculation
        threshold_std: Number of standard deviations for threshold
        
    Returns:
        DataFrame with added columns: HighThreshold, LowThreshold, ExtremeHigh, ExtremeLow
    """
    high_threshold_series = []
    low_threshold_series = []
    is_extreme_high = []
    is_extreme_low = []
    
    min_samples = MOMENTUM_HISTORY_MINUTES / PRICE_RESOLUTION_MINUTES - 1
    
    for i in range(len(df)):
        current_time = df.iloc[i]["Timestamp"]
        current_momentum = df.iloc[i]["Momentum"]
        
        # Get momentum values within history window
        time_window = current_time - pd.Timedelta(minutes=history_window_minutes)
        recent_data = df[(df["Timestamp"] >= time_window) & (df["Timestamp"] <= current_time)]
        
        if len(recent_data) >= min_samples:
            recent_momentum = recent_data["Momentum"].values
            mean_momentum = np.mean(recent_momentum)
            std_momentum = np.std(recent_momentum)
            
            # Calculate adaptive thresholds
            if std_momentum > 0:
                high_threshold = mean_momentum + threshold_std * std_momentum
                low_threshold = mean_momentum - threshold_std * std_momentum
            else:
                high_threshold = mean_momentum + 0.01
                low_threshold = mean_momentum - 0.01
            
            high_threshold_series.append(high_threshold)
            low_threshold_series.append(low_threshold)
            is_extreme_high.append(current_momentum > high_threshold)
            is_extreme_low.append(current_momentum < low_threshold)
        else:
            high_threshold_series.append(np.nan)
            low_threshold_series.append(np.nan)
            is_extreme_high.append(False)
            is_extreme_low.append(False)
    
    df['HighThreshold'] = high_threshold_series
    df['LowThreshold'] = low_threshold_series
    df['ExtremeHigh'] = is_extreme_high
    df['ExtremeLow'] = is_extreme_low
    
    return df


# =============================================================================
# PNL CALCULATION
# =============================================================================


def calculate_pnl_from_orders(df_prices: pd.DataFrame, df_orders: pd.DataFrame) -> list:
    """
    Calculate cumulative PnL over time based on trading activity.
    
    PnL = (current_portfolio_value) - (initial_portfolio_value)
    
    Portfolio value = USDT_balance + (BTC_balance × current_price)
    
    Args:
        df_prices: DataFrame with price history
        df_orders: DataFrame with executed orders
        
    Returns:
        List of PnL values aligned with price DataFrame rows
    """
    if df_orders is None or df_orders.empty:
        return [0.0] * len(df_prices)
    
    # Reconstruct initial state by reversing the first order
    first_order = df_orders.iloc[0]
    
    if first_order["side"] == "buy":
        initial_btc = first_order["account_btc_size"] - first_order["size_actual"]
        initial_usdt = first_order["account_usdt_size"] + first_order["size_actual"] * first_order["price_actual"]
    else:
        initial_btc = first_order["account_btc_size"] + first_order["size_actual"]
        initial_usdt = first_order["account_usdt_size"] - first_order["size_actual"] * first_order["price_actual"]
    
    initial_price = df_prices.iloc[0]["Price"]
    initial_portfolio_value = initial_usdt + initial_btc * initial_price
    
    # Track holdings over time
    current_usdt = initial_usdt
    current_btc = initial_btc
    
    pnl_series = []
    order_idx = 0
    
    for i in range(len(df_prices)):
        current_time = df_prices.iloc[i]["Timestamp"]
        current_price = df_prices.iloc[i]["Price"]
        
        # Process orders up to current time
        while order_idx < len(df_orders) and df_orders.iloc[order_idx]["local_ts"] <= current_time:
            order = df_orders.iloc[order_idx]
            side = order["side"]
            size = order["size_actual"]
            price = order["price_actual"]
            fee = order.get("fee", 0)
            
            if side == "buy":
                current_usdt -= size * price
                current_btc += size - fee
            elif side == "sell":
                current_btc -= size
                current_usdt += (size * price) - fee
            
            order_idx += 1
        
        # Calculate current PnL
        current_portfolio_value = current_usdt + current_btc * current_price
        current_pnl = current_portfolio_value - initial_portfolio_value
        pnl_series.append(current_pnl)
    
    return pnl_series


# =============================================================================
# VISUALIZATION
# =============================================================================


def plot_price_with_orders(price_file: str, orders_file: str):
    """
    Generate trading analysis visualization.
    
    Creates a multi-panel plot showing:
    - Price chart with buy/sell markers and ±1% range indicators
    - Momentum with adaptive threshold bands (if FULL_PLOT=True)
    - Cumulative PnL with profit/loss shading (if FULL_PLOT=True)
    
    Args:
        price_file: Path to CSV file with price data
        orders_file: Path to CSV file with order data
    """
    # Load and filter price data
    df_prices = read_price_data(price_file)
    if df_prices is None:
        print("Error: Could not load price data")
        return
    
    if CUTOFF_DATE is not None:
        df_prices = df_prices[df_prices['Timestamp'] >= CUTOFF_DATE]

    # Calculate momentum indicators
    df_prices['Momentum'] = calculate_price_momentum(df_prices)
    df_prices = detect_momentum_extremes(df_prices)

    # Load and filter order data
    df_orders = read_csv_safely(orders_file, parse_dates='local_ts')
    if df_orders is not None and not df_orders.empty and CUTOFF_DATE is not None:
        df_orders = df_orders[df_orders['local_ts'] >= CUTOFF_DATE]
    
    if df_orders is None or df_orders.empty:
        print("Note: No order data available")

    # Create figure layout
    if FULL_PLOT:
        fig, ax = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    else:
        fig, ax = plt.subplots(1, 1, figsize=(12, 4))
        ax = [ax]

    # --- Plot 1: Price with Orders ---
    ax[0].scatter(
        df_prices["Timestamp"], df_prices["Price"],
        marker='o', s=2, color='steelblue', label="Price"
    )

    if df_orders is not None and not df_orders.empty:
        for _, order in df_orders.iterrows():
            ts = order["local_ts"]
            price = order["price_actual"]
            side = order["side"]

            # ±1% price range for visualization
            price_above = price * 1.01
            price_below = price * 0.99

            color = "forestgreen" if side == "buy" else "crimson"
            marker = "^" if side == "buy" else "v"

            ax[0].scatter(ts, price, color=color, marker=marker, s=60, zorder=5)
            ax[0].scatter(ts, price_above, color=color, marker="_", s=80)
            ax[0].scatter(ts, price_below, color=color, marker="_", s=80)
            ax[0].plot([ts, ts], [price_below, price_above], color=color, linestyle="--", linewidth=1, alpha=0.7)

    ax[0].set_ylabel("Price (USDT)")
    ax[0].set_title("Price Chart with Buy/Sell Orders")
    ax[0].grid(True, alpha=0.3)

    if FULL_PLOT:
        # --- Plot 2: Momentum with Thresholds ---
        ax[1].scatter(
            df_prices["Timestamp"], df_prices["Momentum"],
            marker='o', s=3, color='steelblue', alpha=0.6
        )
        ax[1].axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        
        if 'HighThreshold' in df_prices.columns:
            ax[1].plot(
                df_prices["Timestamp"], df_prices["HighThreshold"],
                linestyle='--', color='crimson', linewidth=1.5, alpha=0.7, label='Upper Threshold'
            )
            ax[1].plot(
                df_prices["Timestamp"], df_prices["LowThreshold"],
                linestyle='--', color='forestgreen', linewidth=1.5, alpha=0.7, label='Lower Threshold'
            )
            
            # Highlight extreme points
            extreme_high = df_prices[df_prices['ExtremeHigh']]
            extreme_low = df_prices[df_prices['ExtremeLow']]
            
            if len(extreme_high) > 0:
                ax[1].scatter(
                    extreme_high["Timestamp"], extreme_high["Momentum"],
                    marker='o', s=50, color='crimson', edgecolors='darkred',
                    linewidth=1.5, label='Extreme High', zorder=5
                )
            
            if len(extreme_low) > 0:
                ax[1].scatter(
                    extreme_low["Timestamp"], extreme_low["Momentum"],
                    marker='o', s=50, color='lime', edgecolors='darkgreen',
                    linewidth=1.5, label='Extreme Low', zorder=5
                )
            
            ax[1].legend(loc='upper right', fontsize=8)
        
        ax[1].set_ylabel("Momentum (%/min)")
        ax[1].set_title("Price Momentum with Adaptive Thresholds")
        ax[1].grid(True, alpha=0.3)

        # --- Plot 3: PnL Over Time ---
        df_prices['PnL'] = calculate_pnl_from_orders(df_prices, df_orders)
        
        ax[2].plot(
            df_prices["Timestamp"], df_prices["PnL"],
            linestyle='-', color='purple', linewidth=2
        )
        ax[2].axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        ax[2].fill_between(
            df_prices["Timestamp"], df_prices["PnL"], 0,
            where=(df_prices["PnL"] >= 0), color='forestgreen', alpha=0.3, interpolate=True
        )
        ax[2].fill_between(
            df_prices["Timestamp"], df_prices["PnL"], 0,
            where=(df_prices["PnL"] < 0), color='crimson', alpha=0.3, interpolate=True
        )
        ax[2].set_xlabel("Time")
        ax[2].set_ylabel("PnL (USDT)")
        ax[2].set_title("Cumulative Profit & Loss")
        ax[2].grid(True, alpha=0.3)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Configure paths to your data files
    # Path: Logic/ -> momentum_trader/ -> project_root/<LOGS_FOLDER>
    current_folder = os.path.dirname(os.path.abspath(__file__))
    logs_folder = os.path.join(current_folder, '../../<LOGS_FOLDER>')
    
    price_file = os.path.join(logs_folder, 'price_data.csv')
    orders_file = os.path.join(logs_folder, 'orders.csv')
    
    plot_price_with_orders(price_file=price_file, orders_file=orders_file)
