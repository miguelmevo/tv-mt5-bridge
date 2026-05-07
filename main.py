from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os

app = FastAPI(title="TradingView-MT5 Bridge")

API_KEY = os.environ.get("API_KEY", "changeme")

signals_store = {}
errors_store  = []

# ── Modelos ───────────────────────────────────────────────────────────────────
class Order(BaseModel):
    type:  str    # BUY_STOP / SELL_STOP
    entry: float
    sl:    float
    tp:    float

class SignalBatch(BaseModel):
    symbol:          str
    session_id:      str
    reference_pivot: str
    risk_mode:       str    # percent / usd
    risk_value:      float
    orders:          List[Order]
    timestamp:       Optional[str] = None

class ErrorReport(BaseModel):
    symbol:        str
    error_code:    int
    error_message: str
    order_type:    Optional[str] = None
    timestamp:     Optional[str] = None

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/webhook")
def receive_webhook(signal: SignalBatch, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    signal.timestamp     = datetime.utcnow().isoformat()
    signals_store[signal.symbol] = signal
    return {"status": "received", "symbol": signal.symbol, "session_id": signal.session_id}

@app.get("/signals/{symbol}")
def get_signals(symbol: str, session_id: str = "", x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if symbol not in signals_store:
        return {"has_new": False, "session_id": None}
    stored = signals_store[symbol]
    if stored.session_id == session_id:
        return {"has_new": False, "session_id": stored.session_id}
    return {"has_new": True, "session_id": stored.session_id, "data": stored.dict()}

@app.post("/errors")
def report_error(error: ErrorReport, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    error.timestamp = datetime.utcnow().isoformat()
    errors_store.append(error.dict())
    if len(errors_store) > 100:
        errors_store.pop(0)
    return {"status": "recorded"}

@app.get("/errors")
def get_errors(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"errors": errors_store[-20:]}
