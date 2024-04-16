import * as fs from "fs";
import { MARKET, MARKET1 } from "../../environments";
import {
  getBalances,
  getPrice,
  getQuantity,
} from "../../modules/binance/binanceFunctions";
import { getMinBuy } from "../../modules/binance/orderType/market/buyOrder";
import { marketSell } from "../../modules/binance/orderType/market/sellOrder";
import { colors, logColor, logFail } from "../logger";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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

export { clearStart, closeBot, sleep };
