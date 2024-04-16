require("dotenv").config();

// Binance Configs
const MARKET1 = process.env.MARKET1 as any;
const MARKET2 = process.env.MARKET2 as any;
const MARKET = `${MARKET1}${MARKET2}`;

const BUY_ORDER_AMOUNT = process.env.BUY_ORDER_AMOUNT as unknown as number;
const PRICE_PERCENT = process.env.PRICE_PERCENT as unknown as number;

// Stop Loss Configs
const STOP_LOSS_BOT = process.env.STOP_LOSS_BOT as unknown as number;

const STOP_LOSS_GRID_IS_FIFO = process.env
  .STOP_LOSS_GRID_IS_FIFO as unknown as boolean;

//Take Profit Configs
const TAKE_PROFIT_BOT = process.env.TAKE_PROFIT_BOT as unknown as number;

const SLEEP_TIME = process.env.SLEEP_TIME as unknown as number;

// Sell All Configs
const SELL_ALL_ON_START = process.env.SELL_ALL_ON_START || false;
const SELL_ALL_ON_CLOSE = process.env.SELL_ALL_ON_CLOSE || false;

const MIN_PRICE_TRANSACTION = process.env
  .MIN_PRICE_TRANSACTION as unknown as number;

// Telegram Configs
const TELEGRAM_BOT_TOKEN: string | undefined = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID: string | undefined = process.env.TELEGRAM_CHAT_ID;

export {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
  STOP_LOSS_GRID_IS_FIFO,
  SLEEP_TIME,
  SELL_ALL_ON_START,
  MIN_PRICE_TRANSACTION,
  TELEGRAM_BOT_TOKEN,
  TELEGRAM_CHAT_ID,
  STOP_LOSS_BOT,
  TAKE_PROFIT_BOT,
  SELL_ALL_ON_CLOSE,
};
