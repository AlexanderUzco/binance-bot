require("dotenv").config();
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  SLEEP_TIME,
  SELL_ALL_ON_START,
  MIN_PRICE_TRANSACTION,
  STOP_LOSS_BOT,
  TAKE_PROFIT_BOT,
  BOLLINGER_BANDS_PERCENT_BUY,
} from "../../environments";
import {
  colors,
  logColor,
  log,
  logProfit,
  logLogo,
  logOrderToSell,
} from "../../utils/logger";
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
  bollingerCheckMA,
  bollingerCheckOrders,
  bollingerOrderBuyWithMa,
} from "../binance/orderIndicator/bollinger";

let Storage = require("node-storage");
const store = new Storage(`./analytics/data/${MARKET}-bollinger.json`);
const ordersFileName = createOrdersFileName({ botRun: "bollinger" });

const broadcast = async () => {
  while (true) {
    try {
      const marketPrice = await getPrice();
      const startPrice = parseFloat(store.get("start_price"));
      const orders = store.get("orders");

      const candleValues = await getCandles({
        symbol: MARKET,
        interval: "1m",
        limit: 150,
        candleType: "close",
      });

      if (!marketPrice) {
        logColor(colors.red, "Error getting price or candle values");
        continue;
      }

      if (!candleValues) {
        logColor(colors.red, "Error getting price or candle values");
        continue;
      }

      const { closings, currentCandle, lastCandle } = candleValues;

      const entryPrice = store.get("entry_price") as number;
      const entryFactor = marketPrice - entryPrice;
      const entryPercent = ((100 * entryFactor) / entryPrice).toFixed(2);

      const takeProfitActivated =
        (TAKE_PROFIT_BOT &&
          (await verifyTakeProfit({ store, marketPrice, ordersFileName }))) ||
        false;
      const stopLossActivated =
        (STOP_LOSS_BOT &&
          (await verifyStopLoss({ store, marketPrice, ordersFileName }))) ||
        false;

      if (takeProfitActivated || stopLossActivated) break;

      const bollinger = await applyBollingerStrategy({
        candleValues: closings,
      });

      console.clear();

      logLogo();
      log("=====================================================");

      logColor(colors.green, "Bot: Bollinger (MA)");

      logColor(
        TelegramBot ? colors.green : colors.gray,
        `Telegram Bot: ${TelegramBot ? "ON" : "OFF"}`
      );

      logProfit({
        store,
        price: marketPrice,
      });

      log("=====================================================");
      logColor(
        colors.orange,
        `\nEntry price: ${entryPrice} ${MARKET2} (${
          parseInt(entryPercent) <= 0 ? "" : "+"
        }${entryPercent}%)\n`
      );
      log("=====================================================");

      if (bollinger) {
        const { currentLower, currentUpper, currentMiddle } = bollinger;

        const targetPrice =
          currentLower - currentLower * (BOLLINGER_BANDS_PERCENT_BUY / 100);

        // console.log(
        //   `Target Price: ${targetPrice} - Stop loss Order: ${stopLossOrderPrice}`
        // );

        //Log bolinger all values
        log(
          `Upper: ${currentUpper.toFixed(10)} - Middle: ${currentMiddle.toFixed(
            10
          )} - Lower: ${currentLower.toFixed(10)}`
        );
        log("=====================================================");

        logColor(colors.orange, `Price: ${marketPrice.toFixed(8)} ${MARKET2}`);

        if (orders.length > 0) {
          log("=====================================================");
          logOrderToSell({ marketPrice, store });
          log("=====================================================");
        }

        if (orders.length > 0) {
          bollingerCheckMA({
            store,
            currentMiddle,
            marketPrice,
          });

          await bollingerCheckOrders({
            marketPrice,
            store,
            ordersFileName,
            currentMiddle,
          });
        }

        const stopLossCooldown = store.get("stop_loss_cooldown");

        if (stopLossCooldown && stopLossCooldown > new Date().getTime()) {
          logColor(colors.red, "Stop loss activated");
        } else {
          store.put("stop_loss_cooldown", null);
          if (marketPrice < currentLower && marketPrice <= targetPrice) {
            await bollingerOrderBuyWithMa({
              marketPrice,
              store,
              ordersFileName,
            });
          }
        }
      }
    } catch (error: any) {
      console.log("broadcast - error", error);
      logErrorFile(error);
    }

    await sleep(SLEEP_TIME as unknown as number);
  }
};

const initBollingerMa = async () => {
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

export default initBollingerMa;
