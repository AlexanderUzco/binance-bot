require("dotenv").config();
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
  SLEEP_TIME,
  SELL_ALL_ON_START,
  MIN_PRICE_TRANSACTION,
  STOP_LOSS_BOT,
  TAKE_PROFIT_BOT,
} from "../../environments";
import { colors, logColor, log, logProfit, logLogo } from "../../utils/logger";
import { createOrdersFileName, logErrorFile } from "../../utils/files";
import {
  checkBalance,
  getPrice,
  verifyStopLoss,
  verifyTakeProfit,
} from "../../modules/binance/binanceFunctions";
import { marketOrderBuy } from "../../modules/binance/orderType/market/buyOrder";
import { marketOrderSell } from "../../modules/binance/orderType/market/sellOrder";
import { bot as TelegramBot } from "../../modules/telegram";
import { clearStart, sleep } from "../../utils/bot";

let Storage = require("node-storage");
const store = new Storage(`./analytics/data/${MARKET}.json`);
const ordersFileName = createOrdersFileName({
  botRun: "base",
});

const broadcast = async () => {
  while (true) {
    try {
      const marketPrice = await getPrice();
      const startPrice = parseFloat(store.get("start_price"));

      if (marketPrice) {
        console.clear();

        logLogo();

        log("=====================================================");

        logColor(colors.green, "Bot: Base");

        logColor(
          TelegramBot ? colors.green : colors.gray,
          `Telegram Bot: ${TelegramBot ? "ON" : "OFF"}`
        );
        logProfit({
          store,
          price: marketPrice,
        });

        const takeProfitActivated =
          (TAKE_PROFIT_BOT &&
            (await verifyTakeProfit({ store, marketPrice, ordersFileName }))) ||
          false;
        const stopLossActivated =
          (STOP_LOSS_BOT &&
            (await verifyStopLoss({ store, marketPrice, ordersFileName }))) ||
          false;

        if (takeProfitActivated || stopLossActivated) break;

        log("=====================================================");

        const entryPrice = store.get("entry_price") as number;
        const entryFactor = marketPrice - entryPrice;
        const entryPercent = ((100 * entryFactor) / entryPrice).toFixed(2);
        logColor(
          colors.orange,
          `\nEntry price: ${entryPrice} ${MARKET2} (${
            parseInt(entryPercent) <= 0 ? "" : "+"
          }${entryPercent}%)\n`
        );
        log("=====================================================");

        log(`Prev price: ${startPrice} ${MARKET2}`);

        if (marketPrice < startPrice) {
          let factor = startPrice - marketPrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.red,
            `New price: ${marketPrice} ${MARKET2} ==> -${percentage.toFixed(
              3
            )}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= PRICE_PERCENT) {
            await marketOrderBuy({
              price: marketPrice,
              amount: BUY_ORDER_AMOUNT,
              store,
              ordersFileName,
            });
          }
        } else if (marketPrice > startPrice) {
          let factor = marketPrice - startPrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.green,
            `New price: ${marketPrice} ${MARKET2} ==> +${percentage.toFixed(
              3
            )}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= PRICE_PERCENT) {
            await marketOrderSell({
              price: marketPrice,
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
      // console.log(error);
      // logErrorFile(error);
    }

    await sleep(SLEEP_TIME as unknown as number);
  }
};

const initBase = async () => {
  if (process.argv[3] === "resumen") {
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

    //TODO: Verify if the order amount is less than MIN_PRICE_TRANSACTION
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

export default initBase;
