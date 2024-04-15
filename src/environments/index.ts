require("dotenv").config();

// Set Markets
const MARKET1 = process.env.MARKET1 as any;
const MARKET2 = process.env.MARKET2 as any;
const MARKET = `${MARKET1}${MARKET2}`;

const BUY_ORDER_AMOUNT = process.env.BUY_ORDER_AMOUNT as unknown as number;
const PRICE_PERCENT = process.env.PRICE_PERCENT as unknown as number;

const STOP_LOSS_GRID_IS_FIFO = process.env
  .STOP_LOSS_GRID_IS_FIFO as unknown as boolean;

const SLEEP_TIME = process.env.SLEEP_TIME as unknown as number;

const SELL_ALL_ON_START =
  process.env.SELL_ALL_ON_START || (false as unknown as boolean);

const MIN_PRICE_TRANSACTION = process.env
  .MIN_PRICE_TRANSACTION as unknown as number;

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
};
