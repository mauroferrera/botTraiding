from mcp.server.fastmcp import FastMCP
import MetaTrader5 as mt5
import json

# Create the FastMCP server
mcp = FastMCP("MetaTrader5-Local")

def init_mt5():
    if not mt5.initialize():
        return False, "Failed to initialize MetaTrader 5. Make sure the MetaTrader 5 application is running."
    return True, ""

@mcp.tool()
def get_account_info() -> str:
    """
    Get information about the currently logged-in trading account,
    including balance, equity, profit, free margin, leverage, and account holder details.
    """
    success, err = init_mt5()
    if not success:
        return err
    
    info = mt5.account_info()
    mt5.shutdown()
    
    if info is None:
        return "Failed to retrieve account info. Please make sure you are logged in to an account in the MT5 terminal."
    
    data = {
        "login": info.login,
        "trade_mode": info.trade_mode,
        "company": info.company,
        "name": info.name,
        "balance": info.balance,
        "equity": info.equity,
        "profit": info.profit,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "margin_level": info.margin_level,
        "leverage": info.leverage,
        "currency": info.currency
    }
    return json.dumps(data, indent=2)

@mcp.tool()
def get_open_positions() -> str:
    """
    Get a list of all currently active open positions in the trading account.
    """
    success, err = init_mt5()
    if not success:
        return err
    
    positions = mt5.positions_get()
    mt5.shutdown()
    
    if positions is None:
        return "Failed to retrieve positions."
    
    if len(positions) == 0:
        return "There are no open positions currently."
    
    res = []
    for pos in positions:
        res.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == 0 else "SELL",
            "volume": pos.volume,
            "price_open": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "price_current": pos.price_current,
            "profit": pos.profit,
            "comment": pos.comment
        })
    return json.dumps(res, indent=2)

@mcp.tool()
def get_symbol_price(symbol: str) -> str:
    """
    Get the current market price (bid and ask) for a specific financial symbol (e.g. 'EURUSD', 'BTCUSD', 'GOLD').
    """
    success, err = init_mt5()
    if not success:
        return err
    
    symbol_info = mt5.symbol_info(symbol)
    mt5.shutdown()
    
    if symbol_info is None:
        return f"Symbol '{symbol}' not found or not visible in Market Watch."
    
    data = {
        "symbol": symbol_info.name,
        "bid": symbol_info.bid,
        "ask": symbol_info.ask,
        "last": symbol_info.last,
        "volume": symbol_info.volume,
        "digits": symbol_info.digits
    }
    return json.dumps(data, indent=2)

if __name__ == "__main__":
    mcp.run()
