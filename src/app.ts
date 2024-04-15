require("dotenv").config();
import * as fs from "fs";
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
  SLEEP_TIME,
  SELL_ALL_ON_START,
  MIN_PRICE_TRANSACTION,
} from "./environments";
import { colors, logColor, log, logProfit, logFail } from "./utils/logger";
import client from "./modules/binance";
import { createOrdersFileName, logErrorFile } from "./utils/files";
import {
  checkBalance,
  getBalances,
  getPrice,
  getQuantity,
} from "./modules/binance/binanceFunctions";
import {
  getMinBuy,
  marketOrderBuy,
} from "./modules/binance/orderType/market/buyOrder";
import {
  marketOrderSell,
  marketSell,
} from "./modules/binance/orderType/market/sellOrder";

let Storage = require("node-storage");
const store = new Storage(`./analytics/data/${MARKET}.json`);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const ordersFileName = createOrdersFileName();

const closeBot = async () => {
  try {
    fs.unlinkSync(`./data/${MARKET}.json`);
  } catch (ee) {}
};

const clearStart = async () => {
  await closeBot();

  const balances = await getBalances();

  const totalAmount = balances[MARKET1];

  const price = await getPrice();

  const minSell = (await getMinBuy()) / price;

  if (totalAmount >= minSell) {
    try {
      const lotQuantity = await getQuantity({
        amount: totalAmount,
      });

      const res = await marketSell({
        amount: lotQuantity,
      });

      if (res && res.status === "FILLED") {
        logColor(colors.green, "Iniciando en modo limpio...");
        await sleep(3000);
      } else {
        logFail();
      }
    } catch (err) {
      logFail();
    }
  }
};

const broadcast = async () => {
  while (true) {
    try {
      const prices = await client.prices({ symbol: MARKET });
      const markePrice = parseFloat(prices[MARKET]);
      const startPrice = parseFloat(store.get("start_price"));

      if (markePrice) {
        console.clear();

        log("=====================================================");
        logProfit({
          store,
          price: markePrice,
        });
        log("=====================================================");

        const entryPrice = store.get("entry_price") as number;
        const entryFactor = markePrice - entryPrice;
        const entryPercent = ((100 * entryFactor) / entryPrice).toFixed(2);
        log(
          `Entry price: ${entryPrice} ${MARKET2} (${
            parseInt(entryPercent) <= 0 ? "" : "+"
          }${entryPercent}%)`
        );
        log("=====================================================");

        log(`Prev price: ${startPrice} ${MARKET2}`);
        if (markePrice < startPrice) {
          let factor = startPrice - markePrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.red,
            `New price: ${markePrice} ${MARKET2} ==> -${percentage.toFixed(3)}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= PRICE_PERCENT) {
            await marketOrderBuy({
              price: markePrice,
              amount: BUY_ORDER_AMOUNT,
              store,
              ordersFileName,
            });
          }
        } else if (markePrice > startPrice) {
          let factor = markePrice - startPrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.green,
            `New price: ${markePrice} ${MARKET2} ==> +${percentage.toFixed(3)}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= PRICE_PERCENT) {
            await marketOrderSell({
              price: markePrice,
              store,
              ordersFileName,
            });
          }
        } else {
          logColor(colors.gray, "Change: 0.000% ==> $0.000");
          store.put("percentage", 0);
        }
      }
    } catch (error: any) {
      console.log(error);
      logErrorFile(error);
    }

    await sleep(SLEEP_TIME as unknown as number);
  }
};

const init = async () => {
  if (process.argv[2] === "resumen") {
    if (SELL_ALL_ON_START) await clearStart();

    const price = await getPrice();

    const balances = await checkBalance();

    store.put("start_price", price);
    store.put("entry_price", price);
    store.put("orders", []);
    store.put("total_profit", 0);
    store.put(
      `${MARKET1?.toLocaleLowerCase()}_balance`,
      balances[MARKET1]?.free
    );
    store.put(
      `${MARKET2?.toLocaleLowerCase()}_balance`,
      balances[MARKET2]?.free
    );
    store.put(
      `initial_${MARKET1.toLowerCase()}_balance`,
      store.get(`${MARKET1.toLowerCase()}_balance`)
    );
    store.put(
      `initial_${MARKET2.toLowerCase()}_balance`,
      store.get(`${MARKET2.toLowerCase()}_balance`)
    );

    //TODO: Verify if the order amount is less than $1
    if (price * BUY_ORDER_AMOUNT < MIN_PRICE_TRANSACTION) {
      const requiredAmount = (1 / price).toFixed(8);
      logColor(
        colors.red,
        `Order amount (${BUY_ORDER_AMOUNT}) is less than $1. Required amount should be at least ${requiredAmount}. Bot will not proceed.`
      );
      return;
    }
  }

  broadcast();
};

init();
