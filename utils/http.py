import requests
import time
import hmac
import hashlib
from decimal import Decimal
from typing import Dict, Any, Optional
from utils.config_loader import get_config

# Binance Future REST API地址
BINANCE_API_URLS = {
    "testnet": "https://testnet.binancefuture.com",
    # "mainnet": "https://fapi.binance.com",  # 实盘，后续支持
}

class BinanceRest:
    """
    Binance Future REST API 封装，支持 testnet，预留 mainnet 切换。
    金额、价格、数量均用 Decimal 处理。
    """
    def __init__(self, api_key: str, secret_key: str, env: str = "testnet"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.env = env
        self.base_url = BINANCE_API_URLS.get(env, BINANCE_API_URLS["testnet"])
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """签名参数"""
        params = {k: v for k, v in params.items() if v is not None}
        query = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(self.secret_key.encode(), query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = signature
        return params

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Any:
        url = self.base_url + path
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params = self._sign(params)
        resp = self.session.request(method, url, params=params)
        try:
            resp.raise_for_status()
        except Exception:
            print("[调试用] 接口返回内容:", resp.text)  # TODO: 问题排查后请删除本行
            raise
        return resp.json()

    def place_order(self, symbol: str, side: str, quantity: Decimal, price: Optional[Decimal] = None, order_type: str = "LIMIT", time_in_force: str = "GTC") -> Any:
        """下单，自动区分限价单和市价单参数"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": str(quantity),
        }
        if order_type == "LIMIT":
            params["price"] = str(price)
            params["timeInForce"] = time_in_force
        # 市价单不加 price 和 timeInForce
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def cancel_all_orders(self, symbol: str) -> Any:
        """撤销该交易对所有挂单"""
        params = {"symbol": symbol}
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params, signed=True)

    def get_open_orders(self, symbol: str) -> Any:
        """查询当前挂单"""
        params = {"symbol": symbol}
        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    def get_balance(self) -> Any:
        """查询账户余额（USDT等）"""
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_account_info(self) -> Any:
        """获取账户信息（含总权益、已实现盈亏等）"""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_position_info(self, symbol: str) -> Any:
        """获取指定交易对持仓信息（含未实现盈亏等）"""
        params = {"symbol": symbol}
        data = self._request("GET", "/fapi/v2/positionRisk", params, signed=True)
        if isinstance(data, list):
            for pos in data:
                if pos.get("symbol") == symbol:
                    return pos
        elif isinstance(data, dict) and data.get("symbol") == symbol:
            return data
        raise ValueError(f"Position info for {symbol} not found")

    def get_symbol_info(self, symbol: str) -> dict:
        """获取交易对的精度和最小下单量等规则"""
        data = self._request("GET", "/fapi/v1/exchangeInfo")
        for s in data["symbols"]:
            if s["symbol"] == symbol:
                lot_size = next(f for f in s["filters"] if f["filterType"] == "LOT_SIZE")
                price_filter = next(f for f in s["filters"] if f["filterType"] == "PRICE_FILTER")
                return {
                    "step_size": lot_size["stepSize"],
                    "min_qty": lot_size["minQty"],
                    "price_tick": price_filter["tickSize"]
                }
        raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
