import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
} from "../../environments";
import { LogProfitT } from "./types";

const colors = {
  green: "\x1b[32m",
  red: "\x1b[31m",
  gray: "\x1b[90m",
  orange: "\x1b[33m",
};

// Log a message with a color
const logColor = (color: string, message: string) => {
  console.log(color, message, colors.gray);
};

// Log a message
const log = (message: string) => {
  console.log(message);
};

const logLogo = () => {
  return logColor(
    colors.green,
    `
    __             __   __  _____
    |__) | |\\ | __ |__) /  \\  | 
    |__) | | \\|    |__) \\__/  | 
    `
  );
};

const logProfit = async ({ store, price }: LogProfitT) => {
  const totalProfits = parseFloat(store.get("total_profit"));
  let isGainerProfit = totalProfits > 0 ? 1 : totalProfits < 0 ? 2 : 0;

  logColor(
    isGainerProfit === 1
      ? colors.green
      : isGainerProfit === 2
      ? colors.red
      : colors.gray,
    `Total Profit: ${totalProfits} ${MARKET2}`
  );

  const m1Balance = parseFloat(
    store.get(`${MARKET1?.toLocaleLowerCase()}_balance`)
  );
  const m2Balance = parseFloat(
    store.get(`${MARKET2?.toLocaleLowerCase()}_balance`)
  );

  const initialBalance = parseFloat(
    store.get(`initial_${MARKET2?.toLocaleLowerCase()}_balance`)
  );

  logColor(
    colors.gray,
    `Balance: ${m1Balance} ${MARKET1}, ${m2Balance.toFixed(2)} ${MARKET2}`
  );
  logColor(
    colors.gray,
    `Current: ${
      m1Balance * price + m2Balance.toFixed(2)
    } ${MARKET2}, Initial: ${initialBalance.toFixed(2)} ${MARKET2}`
  );
};

const logFail = () => {
  logColor(colors.red, "No se ha podido vender el saldo inicial.");
  logColor(colors.red, "Debes venderlo manualmente en Binance.");
  process.exit();
};

const logOrderToSell = ({ store, marketPrice }: any) => {
  const orders = store.get("orders");

  // Get first 3 orders and log them
  orders.slice(0, 3).forEach((order: any) => {
    logColor(
      colors.green,
      `Sell ${order.id} ${order.amount} ${MARKET1} for ${(
        order.amount * marketPrice
      ).toFixed(2)} ${MARKET2}, Price: ${order.sell_price}`
    );
  });
};

export { logFail, logProfit, logColor, log, logLogo, logOrderToSell, colors };
