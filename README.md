# Binance Trading Bot v2

Bot de trading automatizado para Binance. Reescrito en Python con WebSocket real-time, SQLite para persistencia, deteccion automatica de regimen de mercado, y 8 estrategias de trading.

> **Advertencia:** Este bot ha sido desarrollado para propositos educativos y experimentales. El uso de este bot implica riesgos inherentes debido a la naturaleza volatil del mercado de criptomonedas. Opera bajo tu propio riesgo.

## Cambios vs v1 (TypeScript)

| Aspecto | v1 (TS) | v2 (Python) |
|---------|---------|-------------|
| Precio | REST polling cada N segundos | WebSocket real-time + REST fallback |
| Estado | JSON files (node-storage) | SQLite con WAL mode |
| Indicadores | Libreria externa (indicatorts) | Implementacion propia (sin numpy) |
| Estrategias | 4 (en procesos separados) | 8 (seleccionable por CLI) + modo composite |
| Risk mgmt | TP/SL global basico | Per-position SL/TP, ATR sizing, circuit breaker |
| Regimen | Ninguno | ADX-based: ranging/trending/volatile auto-detection |
| CLI | Scripts npm separados | CLI unificado con subcomandos |
| Notificaciones | Telegram | Telegram + Email |
| Dependencias | ~15 packages | 4 packages |

## Requisitos

- Python 3.11+
- Cuenta Binance con API key

## Instalacion

```bash
cd binance-bot
pip install -e .

cp .env.example .env
# Editar .env con tus API keys y configuracion
```

## Configuracion (.env)

### Binance API

```env
APIKEY=tu_api_key
SECRET=tu_api_secret
BINANCE_TESTNET=false   # true para usar testnet
```

### Par de trading

```env
MARKET1=BONK    # Crypto base
MARKET2=USDT    # Quote (stablecoin)
```

### Estrategia

```env
BUY_ORDER_AMOUNT=50000       # Cantidad por orden (unidades de MARKET1)
MIN_PRICE_TRANSACTION=1      # Valor minimo de orden en MARKET2

# Base (price action)
PRICE_PERCENT=0.5            # % de cambio para trigger

# Bollinger Bands
BOLLINGER_BANDS_PERCENT_BUY=0.1
BOLLINGER_BANDS_PERCENT_SELL=0.5
BOLLINGER_BANDS_STOP_LOSS_ORDER=0.2
BOLLIINGER_MA_STOP_LOSS=0.2

# RSI (filtro opcional)
APPLY_RSI=true
RSI_SUPPORT=30
RSI_RESISTANCE=70
```

### Risk Management

```env
STOP_LOSS_BOT=3       # % perdida total para apagar el bot
TAKE_PROFIT_BOT=3     # % ganancia total para apagar el bot
MAX_OPEN_ORDERS=10    # Max posiciones abiertas
MAX_POSITION_PCT=30   # Max % del balance por posicion
```

### Ejecucion

```env
SLEEP_TIME=2000            # Intervalo del loop en ms
SELL_ALL_ON_START=false
SELL_ALL_ON_CLOSE=true
```

### Notificaciones (opcionales)

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_ENABLED=false
EMAIL_TO=tu@email.com
```

## Uso

### CLI — Single pair

```bash
# Modo composite (recomendado) - auto-selecciona estrategia segun mercado
python -m binance_bot run

# Elegir estrategia especifica
python -m binance_bot run --strategy grid
python -m binance_bot run --strategy smart_dca
python -m binance_bot run --strategy supertrend
python -m binance_bot run --strategy bollinger_ma

# Con opciones
python -m binance_bot run -s composite --log-level DEBUG --log-file bot.log

# Sin WebSocket (usa REST polling)
python -m binance_bot run --no-websocket

# Usar otro .env
python -m binance_bot run --env .env.testnet
```

### Web Dashboard — Multi pair

Dashboard web para monitorear y operar multiples pares simultaneamente. SSR con FastAPI + Jinja2 + HTMX. Sin build de JS.

```bash
# Iniciar dashboard (default: http://localhost:8080)
python -m binance_bot web

# Con opciones
python -m binance_bot web --port 9090 --env .env.testnet --pairs pairs.json
```

Los pares se configuran en `pairs.json` (raiz del proyecto):

```json
{
  "pairs": [
    {
      "market1": "DOGE",
      "market2": "USDT",
      "strategy": "composite",
      "buy_order_amount": 10.0,
      "enabled": true
    },
    {
      "market1": "BTC",
      "market2": "USDT",
      "strategy": "composite",
      "buy_order_amount": 0.001,
      "enabled": false
    }
  ]
}
```

El dashboard muestra:
- Balance global y P&L total
- Card por cada par con precio, P&L realizado/no realizado, posiciones abiertas
- Start/Stop individual por par
- Vista de detalle con operacion en vivo: event feed, regimen de mercado, uptime
- Tabla de posiciones abiertas y trades recientes

Arquitectura interna: un `PairOrchestrator` gestiona N instancias de `TradingEngine` como asyncio tasks, compartiendo un solo `BinanceClient` y una sola base de datos SQLite.

### Consultar estado

```bash
python -m binance_bot status
python -m binance_bot stats
python -m binance_bot positions
python -m binance_bot trades
python -m binance_bot trades --limit 50
```

### Detener el bot

`Ctrl+C` - Shutdown graceful:
1. Si `SELL_ALL_ON_CLOSE=true`, vende todas las posiciones abiertas
2. Envia notificacion de shutdown con resumen
3. Cierra conexiones

## Estrategias

### Modo Composite (`composite`) — Recomendado

Auto-selecciona la estrategia optima basado en el regimen de mercado actual:

| Regimen | Deteccion | Estrategia activa |
|---------|-----------|-------------------|
| Ranging | ADX < 25 | Grid Trading |
| Caida volatil | RSI < 35 + precio bajo BB | Smart DCA |
| Tendencia alcista | ADX > 25, +DI > -DI | Supertrend |
| Tendencia bajista | ADX > 25, -DI > +DI | Hold (no compra) |

El motor compuesto mantiene posiciones existentes bajo la estrategia que las abrio, independientemente del regimen actual. Solo las nuevas entradas se enrutan al strategy activo.

### Grid Trading (`grid`)

Coloca ordenes de compra/venta escalonadas en un rango de precio. Cada ciclo buy-sell captura el spacing como ganancia.

- Grid geometrico (% spacing) con 10 niveles
- Spacing basado en ATR (se adapta a volatilidad)
- **Filtro ADX < 25**: solo opera en mercados laterales
- Auto-rebalanceo si el precio sale del rango
- Retorno esperado: 15-25% anual en mercados con rango

### Smart DCA (`smart_dca`)

Dollar Cost Averaging inteligente con Safety Orders (patron 3Commas).

- **Trigger**: RSI < 35 + precio <= BB inferior
- Base order + hasta 5 safety orders
- Cada SO es 1.5x mas grande que el anterior
- Step entre SOs: 1.5% * 1.2^n (se amplia)
- **Take profit**: 1.5% sobre el entry promediado
- **Hard stop loss**: -10% sobre el entry promediado
- Win rate: 85-95%, pero el SL protege contra caidas catastroficas

### Supertrend (`supertrend`)

Trend following basado en ATR con trailing stop integrado.

- Indicador Supertrend (ATR period=10, multiplier=3.0)
- **Filtro ADX > 25**: solo opera cuando hay tendencia real
- Compra: precio cruza arriba de linea Supertrend (flip bullish)
- Venta: precio cruza abajo (flip bearish) o trailing SL
- SL trailing: la linea Supertrend sube automaticamente
- TP: 3:1 risk-reward ratio
- Filtro RSI: no compra si RSI > 75

### Price Action (`price_action`)

Estrategia original v1. Compra cuando el precio baja X%, vende cuando sube X%.

### Bollinger Bands (`bollinger`)

Compra en banda inferior, vende al rebotar. RSI como filtro opcional.

### Bollinger MA (`bollinger_ma`)

Bollinger para entrada + MA trailing para salida. Captura tendencias largas.

### EMA Crossover (`ema_crossover`)

Golden/death cross de EMA 9/21 con EMA 50 como filtro de tendencia.

## Indicadores tecnicos

Todos implementados en pure Python (sin numpy/pandas):

- **RSI** (14) — Wilder's smoothing
- **Bollinger Bands** (20, 2 std) — con %B
- **MACD** (12/26/9)
- **EMA** (9, 21, 50, 200)
- **ATR** (14) — Wilder's smoothing
- **ADX + DI** (14) — Average Directional Index con +DI/-DI
- **Supertrend** (10, 3.0) — ATR-based trend indicator
- **Market Regime Detector** — ADX + BB + RSI + ATR combinados

## Arquitectura

```
binance_bot/
├── __init__.py
├── __main__.py             # Entry point
├── cli.py                  # CLI unificado (run, web, status, stats, ...)
├── config.py               # Dataclass config desde .env
├── database.py             # SQLite + WAL mode
├── engine.py               # Loop principal (soporta shared client/db)
├── notifications.py        # Telegram + Email
├── services/
│   ├── binance_client.py   # REST + WebSocket client
│   ├── indicators.py       # Todos los indicadores tecnicos
│   ├── order_executor.py   # Ejecucion de ordenes
│   ├── position_manager.py # Tracking de posiciones, P&L
│   └── risk_manager.py     # Circuit breaker, sizing, limits
├── strategies/
│   ├── base.py             # BaseStrategy ABC
│   ├── composite.py        # Auto-switching por regimen
│   ├── grid.py             # Grid trading
│   ├── smart_dca.py        # DCA con safety orders
│   ├── supertrend.py       # Supertrend trend following
│   ├── price_action.py     # Estrategia original v1
│   ├── bollinger.py        # Bollinger Bands + RSI
│   ├── bollinger_ma.py     # Bollinger + MA trailing
│   └── ema_crossover.py    # EMA crossover
├── web/
│   ├── app.py              # FastAPI factory, lifespan, rutas
│   ├── orchestrator.py     # PairOrchestrator: N engines como asyncio tasks
│   ├── templates/          # Jinja2: base, dashboard, pair detail, partials
│   └── static/style.css    # Dark theme
└── utils/
```

### Flujo del engine

```
1. Inicializa DB, Binance client, carga 150 klines
2. Conecta WebSocket para precio real-time
3. Loop cada SLEEP_TIME ms:
   a. Precio actual (WS o REST)
   b. Refresca klines cada 5 min
   c. Verifica risk limits del portfolio (TP/SL global)
   d. Ejecuta exits pendientes (per-position SL/TP)
   e. Actualiza trailing data (MA checks, Supertrend SL)
   f. [Composite] Detecta regimen → selecciona estrategia
   g. Evalua estrategia para nueva senal
   h. Si buy: verifica risk manager → ejecuta
   i. Si sell: ejecuta → registra trade → notifica
```

### Base de datos

SQLite con WAL mode. Tablas:
- `positions`: posiciones con strategy tag, SL/TP, metadata
- `orders`: historial de ordenes (binance order IDs)
- `trades`: trades completados con P&L y profit %
- `bot_state`: key-value para estado del bot

## Dependencias

Core (4 packages):
- `httpx` — HTTP async para Binance REST API
- `websockets` — WebSocket para streams real-time
- `aiosqlite` — SQLite async
- `python-dotenv` — Carga .env

Web dashboard (3 packages adicionales):
- `fastapi` — Framework web async
- `uvicorn` — ASGI server
- `jinja2` — Templates SSR
