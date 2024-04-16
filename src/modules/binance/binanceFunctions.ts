import client from ".";
import {
  CalculateProfitT,
  GetOrderIdT,
  GetQuantityT,
  GetRealProfitsT,
  MarketOrderT,
  NewPriceResetT,
  UpdateBalancesT,
} from "./types/binanceFunctions";
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  STOP_LOSS_GRID_IS_FIFO,
  STOP_LOSS_BOT,
  TAKE_PROFIT_BOT,
  SELL_ALL_ON_CLOSE,
} from "../../environments";
import { OrderType } from "binance-api-node";
import { colors, logColor } from "../../utils/logger";
import { closeBot } from "../../utils/bot";
import { sellAll } from "./orderType/market/sellOrder";
import { sendProfitUpdateMessage } from "../telegram/messages/binanceMessage";

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

const getRealProfits = ({ price, store }: GetRealProfitsT) => {
  const m1Balance = parseFloat(store.get(`${MARKET1.toLowerCase()}_balance`));
  const m2Balance = parseFloat(store.get(`${MARKET2.toLowerCase()}_balance`));

  const initialBalance1 = parseFloat(
    store.get(`initial_${MARKET1.toLowerCase()}_balance`)
  );
  const initialBalance2 = parseFloat(
    store.get(`initial_${MARKET2.toLowerCase()}_balance`)
  );

  const totalProfit =
    (m1Balance - initialBalance1) * price + (m2Balance - initialBalance2);

  return totalProfit;
};

const verifyTakeProfit = async ({ store, marketPrice }: any) => {
  const totalProfits = getRealProfits({
    store,
    price: marketPrice,
  });

  if (!isNaN(totalProfits)) {
    const totalProfitsPercent = (
      (100 * totalProfits) /
      store.get(`initial_${MARKET2.toLowerCase()}_balance`)
    ).toFixed(3);

    STOP_LOSS_BOT &&
      logColor(
        totalProfits < 0
          ? colors.red
          : totalProfits == 0
          ? colors.gray
          : colors.green,
        `Real Profits [SL = ${STOP_LOSS_BOT}%, TP = ${TAKE_PROFIT_BOT}%]: ${totalProfitsPercent}% ==> ${
          totalProfits <= 0 ? "" : "+"
        }${totalProfits.toFixed(3)} ${MARKET2}`
      );

    if (parseFloat(totalProfitsPercent) >= TAKE_PROFIT_BOT) {
      let messageData;

      logColor(colors.green, "Closing bot with profits...");

      await closeBot();

      if (SELL_ALL_ON_CLOSE) {
        logColor(colors.green, "Selling all assets...");
        const resSellAll = await sellAll();

        if (resSellAll) messageData = resSellAll;
      }

      sendProfitUpdateMessage({
        realProfit: totalProfits,
        totalSold: messageData?.totalSold,
        totalAmount: messageData?.totalAmount,
        price: messageData?.price,
        type: "takeProfit",
      });

      return;
    }
  }
};

const verifyStopLoss = async ({ store, marketPrice }: any) => {
  const totalProfits = getRealProfits({
    store,
    price: marketPrice,
  });

  const totalProfitsPercent = (
    (100 * totalProfits) /
    store.get(`initial_${MARKET2.toLowerCase()}_balance`)
  ).toFixed(3);

  if (parseFloat(totalProfitsPercent) <= -1 * STOP_LOSS_BOT) {
    let messageData;

    logColor(colors.red, "Closing bot with losses...");

    await closeBot();

    if (SELL_ALL_ON_CLOSE) {
      logColor(colors.green, "Selling all assets...");
      const resSellAll = await sellAll();

      if (resSellAll) messageData = resSellAll;
    }

    sendProfitUpdateMessage({
      realProfit: totalProfits,
      totalSold: messageData?.totalSold,
      totalAmount: messageData?.totalAmount,
      price: messageData?.price,
      type: "stopLoss",
    });

    return;
  }
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
  getRealProfits,
  verifyTakeProfit,
  verifyStopLoss,
};
