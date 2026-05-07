"""
TradingView → MT5 Pivot Signals Bridge
=======================================
Recibe alertas JSON desde TradingView y las almacena.
El EA de MT5 consulta cada 2 segundos para obtener señales nuevas.

Endpoints:
  GET  /health              ← verificar que está online
  POST /webhook             ← TradingView envía la señal
  GET  /signals/{symbol}    ← MT5 EA consulta (con ?session_id=)
  POST /errors              ← MT5 EA reporta errores
  GET  /errors              ← ver últimos errores
"""

from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os

app = FastAPI(title="TradingView-MT5 Pivot Bridge")

API_KEY = os.environ.get("API_KEY", "changeme")

# Almacenamiento en memoria (Railway mantiene el proceso vivo)
signals_store: dict = {}   # symbol -> última SignalBatch
errors_store: list  = []   # últimos errores del EA


# ── Modelos ──────────────────────────────────────────────────────────────────

class Order(BaseModel):
    type: str          # "BUY_STOP" | "SELL_STOP"
    entry: float
    sl: float
    tp: float

class SignalBatch(BaseModel):
    symbol: str
    session_id: str
    reference_pivot: str
    risk_mode: str     # "USD" | "PCT"
    risk_value: float
    orders: List[Order]
    timestamp: Optional[str] = None

class ErrorReport(BaseModel):
    symbol: str
    error_code: int
    error_message: str
    order_type: Optional[str] = None
    timestamp: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def check_api_key(header_key: Optional[str], query_key: Optional[str] = None):
    if header_key == API_KEY or query_key == API_KEY:
        return
    raise HTTPException(status_code=401, detail="API key inválida")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "online",
        "time": datetime.utcnow().isoformat(),
        "symbols_tracked": list(signals_store.keys()),
    }


@app.post("/webhook")
def receive_signal(
    batch: SignalBatch,
    x_api_key: Optional[str] = Header(default=None),
    api_key:   Optional[str] = Query(default=None),
):
    """TradingView envía la señal aquí vía webhook."""
    check_api_key(x_api_key, api_key)

    if batch.timestamp is None:
        batch.timestamp = datetime.utcnow().isoformat()

    signals_store[batch.symbol.upper()] = batch
    print(f"[{batch.timestamp}] ▸ Señal recibida: {batch.symbol} | pivote: {batch.reference_pivot} | {len(batch.orders)} órdenes")
    return {"ok": True, "symbol": batch.symbol, "session_id": batch.session_id}


@app.get("/signals/{symbol}")
def get_signal(
    symbol: str,
    session_id: Optional[str] = None,
    x_api_key: Optional[str] = Header(default=None),
    api_key:   Optional[str] = Query(default=None),
):
    """
    MT5 EA consulta aquí cada 2 segundos.
    Si pasa session_id y ya lo procesó, responde 'no_new'.
    """
    check_api_key(x_api_key, api_key)

    sym = symbol.upper()
    batch = signals_store.get(sym)

    if batch is None:
        return {"new_signal": False}

    if session_id and session_id == batch.session_id:
        return {"new_signal": False}

    return {"new_signal": True, "signal": batch}


@app.post("/errors")
def report_error(
    report: ErrorReport,
    x_api_key: Optional[str] = Header(default=None),
    api_key:   Optional[str] = Query(default=None),
):
    """MT5 EA reporta un error al intentar colocar una orden."""
    check_api_key(x_api_key, api_key)

    if report.timestamp is None:
        report.timestamp = datetime.utcnow().isoformat()

    errors_store.append(report.model_dump())
    if len(errors_store) > 100:
        errors_store.pop(0)

    print(f"[{report.timestamp}] ✗ Error EA: {report.symbol} | {report.error_code} | {report.error_message}")
    return {"ok": True}


@app.get("/errors")
def get_errors(
    x_api_key: Optional[str] = Header(default=None),
    api_key:   Optional[str] = Query(default=None),
):
    """Ver los últimos errores reportados por el EA."""
    check_api_key(x_api_key, api_key)
    return errors_store[-50:]
