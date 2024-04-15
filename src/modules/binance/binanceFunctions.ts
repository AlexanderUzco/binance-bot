import client from ".";
import {
  CalculateProfitT,
  GetOrderIdT,
  GetQuantityT,
  MarketOrderT,
  NewPriceResetT,
  UpdateBalancesT,
} from "./types/binanceFunctions";
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
  STOP_LOSS_GRID_IS_FIFO,
} from "../../environments";
import { OrderType } from "binance-api-node";

/**
 * @returns {Object} An object containing the balances of the specified assets.
 */
const checkBalance = async () => {
  const balances = (await client.accountInfo()).balances;
  const balanceAsset1 = balances.find(
    (balance: any) => balance.asset === MARKET1
  );
  const balanceAsset2 = balances.find(
    (balance: any) => balance.asset === MARKET2
  );

  return {
    [MARKET1]: balanceAsset1,
    [MARKET2]: balanceAsset2,
  };
};

/**
 * @returns {Object} An object containing the balances of the specified assets.
 */

const getBalances = async () => {
  const assets = [MARKET1, MARKET2];
  const { balances } = await client.accountInfo();
  const _balances = balances.filter((coin) => assets.includes(coin.asset));

  let parsedBalnaces: any = {};

  assets.forEach((asset) => {
    let findAsset = _balances.find((coin) => coin.asset === asset);
    parsedBalnaces[asset] = parseFloat(findAsset ? findAsset.free : "0");
  });

  return parsedBalnaces;
};

/**
 * Retrieves the price of a symbol in the market.
 * @returns {number} The price of the symbol.
 */
const getPrice = async () => {
  return parseFloat((await client.prices({ symbol: MARKET }))[MARKET]);
};

/**
 * Retrieves the quantity of a symbol to buy.
 * @param {number} amount - The amount to buy.
 * @returns {string} The quantity to buy.
 */
const getQuantity = async ({ amount }: GetQuantityT) => {
  const { symbols } = await client.exchangeInfo({ symbol: MARKET });

  // TODO: Check if the stepSize is not found
  //@ts-ignore
  const { stepSize } = symbols[0].filters.find(
    (filter) => filter.filterType === "LOT_SIZE"
  );

  let quantity = (amount / stepSize).toFixed(symbols[0].baseAssetPrecision);

  if (amount % stepSize !== 0) {
    quantity = (parseInt(quantity) * stepSize).toFixed(
      symbols[0].baseAssetPrecision
    );
  }

  return quantity;
};

const newPriceReset = async ({
  currentMarket,
  store,
  marketPrice,
}: NewPriceResetT) => {
  const market = currentMarket === 1 ? MARKET1 : MARKET2;

  if (
    !(
      parseFloat(store.get(`${market?.toLocaleLowerCase()}_balance`)) >
      BUY_ORDER_AMOUNT
    )
  )
    store.put("start_price", marketPrice);
};

/**
 * @param {Object} store - The store object.
 * @returns {Promise<void>} - A promise that resolves when the balances are updated.
 */
const updateBalances = async ({ store }: UpdateBalancesT) => {
  const balances = await checkBalance();

  store.put(`${MARKET1?.toLocaleLowerCase()}_balance`, balances[MARKET1]?.free);
  store.put(`${MARKET2?.toLocaleLowerCase()}_balance`, balances[MARKET2]?.free);
};

/**
 * @param {Object} store - The store object.
 * @returns {Promise<void>} - A promise that resolves when the profit is calculated.
 */
const calculateProfit = async ({ store }: CalculateProfitT) => {
  const orders = store.get("orders");
  const solds = orders.filter((order: any) => order.status === "sold");
  const totalSoldProfit =
    solds.length > 0
      ? solds.reduce((acc: number, order: any) => acc + order.profit, 0)
      : 0;

  store.put(
    "total_profit",
    totalSoldProfit + parseFloat(store.get("total_profit"))
  );
};

/**
 * @param {Object} store - The store object.
 * @returns {number} - The order id.
 */
const getOrderId = ({ store }: GetOrderIdT) => {
  const fifoStrategy = STOP_LOSS_GRID_IS_FIFO;
  const orders = store.get("orders");
  const index = fifoStrategy ? 0 : orders.length - 1;

  return store.get("orders")[index].id;
};

/**
 * @param {Object} side - The side of the order.
 * @param {Object} amount - The amount of the order.
 * @returns {Object} - The order object.
 */
const marketOrder = async ({ side, amount }: MarketOrderT) => {
  return await client.order({
    symbol: MARKET,
    side,
    quantity: amount,
    type: OrderType.MARKET,
  });
};

export {
  getBalances,
  getPrice,
  getQuantity,
  checkBalance,
  newPriceReset,
  updateBalances,
  calculateProfit,
  getOrderId,
  marketOrder,
};
