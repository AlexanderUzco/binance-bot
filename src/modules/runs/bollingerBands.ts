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
  BOLLINGER_BANDS_PERCENT_SELL,
  BOLLINGER_BANDS_PERCENT_BUY,
} from "../../environments";
import { colors, logColor, log, logProfit, logLogo } from "../../utils/logger";
import { createOrdersFileName, logErrorFile } from "../../utils/files";
import {
  checkBalance,
  getCandles,
  getPrice,
  verifyStopLoss,
  verifyTakeProfit,
} from "../../modules/binance/binanceFunctions";
import { bot as TelegramBot } from "../../modules/telegram";
import { clearStart, sleep } from "../../utils/bot";
import {
  applyBollingerStrategy,
  bollingerOrderBuy,
  bollingerOrderSell,
} from "../binance/orderIndicator/bollinger";

let Storage = require("node-storage");
const store = new Storage(`./analytics/data/${MARKET}-bollinger.json`);
const ordersFileName = createOrdersFileName({ botRun: "bollinger" });

const broadcast = async () => {
  while (true) {
    try {
      const marketPrice = await getPrice();
      const startPrice = parseFloat(store.get("start_price"));

      const candleValues = await getCandles({
        symbol: MARKET,
        interval: "1m",
        limit: 20,
        candleType: "close",
      });

      if (marketPrice) {
        console.clear();

        logLogo();

        log("=====================================================");

        logColor(colors.green, "Bot: Bollinger");

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
            (await verifyTakeProfit({ store, marketPrice }))) ||
          false;
        const stopLossActivated =
          (STOP_LOSS_BOT && (await verifyStopLoss({ store, marketPrice }))) ||
          false;

        if (takeProfitActivated || stopLossActivated) break;

        const bollinger = await applyBollingerStrategy({
          candleValues,
        });

        if (bollinger) {
          const { currentLower, currentUpper, currentMiddle } = bollinger;

          const targetPrice =
            currentLower - currentLower * (BOLLINGER_BANDS_PERCENT_BUY / 100);

          const soldPrice =
            currentLower + currentLower * (BOLLINGER_BANDS_PERCENT_SELL / 100);

          //Log bolinger all values
          log("=====================================================");
          log("Bollinger Bands values");
          logColor(colors.green, `Current upper: ${currentUpper} ${MARKET2}`);

          logColor(
            colors.orange,
            `Current middle: ${currentMiddle} ${MARKET2}`
          );
          logColor(colors.green, `Current lower: ${currentLower} ${MARKET2}`);
          log("=====================================================");
          if (marketPrice < currentLower) {
            let factor = startPrice - marketPrice;
            let percentage = (factor / startPrice) * 100;

            logColor(
              colors.red,
              `Price: ${marketPrice.toFixed(
                8
              )} ${MARKET2} ==> -${percentage.toFixed(8)}%`
            );

            store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

            if (marketPrice <= targetPrice) {
              await bollingerOrderBuy({
                priceToSell: soldPrice,
                marketPrice,
                store,
                ordersFileName,
              });
            }
          }

          let factor = marketPrice - startPrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.orange,
            `Price: ${marketPrice.toFixed(8)} ${MARKET2}`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          await bollingerOrderSell({
            marketPrice,
            store,
            ordersFileName,
          });
        }
      }
    } catch (error: any) {
      console.log(error);
      logErrorFile(error);
    }

    await sleep(SLEEP_TIME as unknown as number);
  }
};

const initBollinger = async () => {
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

export default initBollinger;
