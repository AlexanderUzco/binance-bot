require("dotenv").config();
import * as fs from "fs";
import { colors, logColor, log } from "./utils/logger";
import client from "./binance";
import {
  addOrderToExcel,
  createOrdersFileName,
  logError,
} from "./utils/fileFunctions";
import { OrderType } from "binance-api-node";
import { OrderJsonData, OrderExcelFile } from "./types/orders";

// Create order file and get the file name
const ordersFileName = createOrdersFileName();

//import store from 'node-store';
var Storage = require("node-storage");

// Set Markets
const market1 = process.env.MARKET1 as any;
const market2 = process.env.MARKET2 as any;
const market = `${market1}${market2}`;

// Set transactions constants
const buyOrderAmount = process.env.BUY_ORDER_AMOUNT as unknown as number;
const pricePercent = process.env.PRICE_PERCENT as unknown as number;

// Set store
const store = new Storage(`./data/${market}.json`);

// Confifure Sleep
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

//Configure bot functions
const closeBot = async () => {
  try {
    fs.unlinkSync(`./data/${market}.json`);
  } catch (ee) {}
};

const clearStart = async () => {
  await closeBot();
  const balances = await getBalances();
  const totalAmount = balances[market1];
  const price = await getPrice(market);
  const minSell = (await getMinBuy()) / price;
  if (totalAmount >= minSell) {
    try {
      const lotQuantity = await getQuantity(totalAmount);
      const res = await marketSell(lotQuantity);
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

const logFail = () => {
  logColor(colors.red, "No se ha podido vender el saldo inicial.");
  logColor(colors.red, "Debes venderlo manualmente en Binance.");
  process.exit();
};

const marketBuy = async (amount: string) => {
  return await marketOrder("BUY", amount);
};

// Configure Binace functions
const getBalances = async () => {
  const assets = [market1, market2];
  const { balances } = await client.accountInfo();
  const _balances = balances.filter((coin) => assets.includes(coin.asset));
  var parsedBalnaces: any = {};
  assets.forEach((asset) => {
    // @ts-ignore
    parsedBalnaces[asset] = parseFloat(
      //@ts-ignore
      _balances.find((coin) => coin.asset === asset).free
    );
  });
  return parsedBalnaces;
};

async function getMinBuy() {
  const { symbols } = await client.exchangeInfo({ symbol: market });
  // TODO: Check if the minNotional is not found
  //@ts-ignore
  const { minNotional } = symbols[0].filters.find(
    //@ts-ignore
    (filter) => filter.filterType === "NOTIONAL"
  );

  return parseFloat(minNotional);
}

const getPrice = async (symbol: string) => {
  return parseFloat((await client.prices({ symbol }))[symbol]);
};

const checkBalance = async () => {
  const balances = (await client.accountInfo()).balances;
  const balanceAsset1 = balances.find(
    (balance: any) => balance.asset === market1
  );
  const balanceAsset2 = balances.find(
    (balance: any) => balance.asset === market2
  );

  return {
    [market1]: balanceAsset1,
    [market2]: balanceAsset2,
  };
};

const newPriceReset = async (
  currentMarket: number,
  buyOrderAmount: number,
  marketPrice: any
) => {
  const market = currentMarket === 1 ? market1 : market2;

  if (
    !(
      parseFloat(store.get(`${market?.toLocaleLowerCase()}_balance`)) >
      buyOrderAmount
    )
  )
    store.put("start_price", marketPrice);
};

const updateBalances = async () => {
  const balances = await checkBalance();

  store.put(`${market1?.toLocaleLowerCase()}_balance`, balances[market1]?.free);
  store.put(`${market2?.toLocaleLowerCase()}_balance`, balances[market2]?.free);
};

const calculateProfit = async () => {
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

const logProfit = async (price: number) => {
  const totalProfits = parseFloat(store.get("total_profit"));
  let isGainerProfit = totalProfits > 0 ? 1 : totalProfits < 0 ? 2 : 0;

  logColor(
    isGainerProfit === 1
      ? colors.green
      : isGainerProfit === 2
      ? colors.red
      : colors.gray,
    `Total Profit: ${totalProfits} ${market2}`
  );

  const m1Balance = parseFloat(
    store.get(`${market1?.toLocaleLowerCase()}_balance`)
  );
  const m2Balance = parseFloat(
    store.get(`${market2?.toLocaleLowerCase()}_balance`)
  );

  const initialBalance = parseFloat(
    store.get(`initial_${market2?.toLocaleLowerCase()}_balance`)
  );

  logColor(
    colors.gray,
    `Balance: ${m1Balance} ${market1}, ${m2Balance.toFixed(2)} ${market2}`
  );
  logColor(
    colors.gray,
    `Current: ${
      m1Balance * price + m2Balance.toFixed(2)
    } ${market2}, Initial: ${initialBalance.toFixed(2)} ${market2}`
  );
};

// Order functions
const marketOrder = async (side: "SELL" | "BUY", amount: string) => {
  return await client.order({
    symbol: market,
    side,
    quantity: amount,
    type: OrderType.MARKET,
  });
};

const marketSell = async (amount: string) => {
  return await marketOrder("SELL", amount);
};

const getQuantity = async (amount: number) => {
  const { symbols } = await client.exchangeInfo({ symbol: market });
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

const buy = async (price: number, amount: number) => {
  if (
    parseFloat(store.get(`${market2?.toLocaleLowerCase()}_balance`)) >
    buyOrderAmount * price
  ) {
    let orders = store.get("orders");
    let factor = (pricePercent * price) / 100;

    log(`
            Buying ${market1}
            ==============================================
            Amount In: ${(buyOrderAmount * price).toFixed(2)} ${market2}
            Amount Out: ${buyOrderAmount} ${market1}
        `);

    const buyOrder = await marketBuy(amount.toString());

    if (buyOrder.status === "FILLED") {
      let order: OrderJsonData = {
        id: buyOrder.orderId,
        buy_price: buyOrder.fills ? parseFloat(buyOrder.fills[0].price) : price,
        sell_price: price + factor,
        sold_price: 0,
        status: "bought",
        profit: 0,
        amount: buyOrder.fills
          ? parseFloat(buyOrder.executedQty) -
            (buyOrder.fills[0].commission as unknown as number)
          : parseFloat(buyOrder.executedQty),
      };

      let orderExcel: OrderExcelFile = {
        ...order,
        type: "MARKET",
        symbol: market,
        side: "BUY",
        total_price: parseFloat(buyOrder.cummulativeQuoteQty),
        commission: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].commission)
          : 0,
      };

      orders.push(order);
      store.put("orders", orders);
      store.put("start_price", order.buy_price);

      await updateBalances();

      logColor(colors.green, "====================");
      logColor(
        colors.green,
        `Bought ${order.amount} ${market1} for ${(order.amount * price).toFixed(
          2
        )} ${market2}, Price: ${order.buy_price}\n`
      );
      logColor(colors.green, "====================");

      await calculateProfit();

      await addOrderToExcel(orderExcel, ordersFileName);
    } else newPriceReset(2, buyOrderAmount, price);
  } else newPriceReset(2, buyOrderAmount, price);
};

const getOrderId = () => {
  const fifoStrategy = process.env.STOP_LOSS_GRID_IS_FIFO;
  const orders = store.get("orders");
  const index = fifoStrategy ? 0 : orders.length - 1;

  return store.get("orders")[index].id;
};

const getToSold = (price: number, changeStatus: boolean) => {
  const orders = store.get("orders");
  const toSold = [];

  for (var i = 0; i < orders.length; i++) {
    var order = orders[i];
    if (
      price >= order.sell_price ||
      (getOrderId() === order.id &&
        store.get(`${market2.toLowerCase()}_balance`) < buyOrderAmount)
    ) {
      if (changeStatus) {
        order.sold_price = price;
        order.status = "selling";
      }
      toSold.push(order);
    }
  }

  return toSold;
};

const sell = async (price: number) => {
  const orders = store.get("orders");
  const toSold = getToSold(price, true);

  if (toSold.length > 0) {
    const totalAmount = toSold.reduce(
      (acc: number, order: any) => acc + order.amount,
      0
    );

    if (
      totalAmount > 0 &&
      parseFloat(store.get(`${market1?.toLocaleLowerCase()}_balance`)) >=
        totalAmount
    ) {
      const lotQuantity = await getQuantity(totalAmount);
      const sellOrder = await marketSell(lotQuantity);

      if (sellOrder.status === "FILLED") {
        const promises: Promise<void>[] = [];

        let currentOrder: OrderJsonData;

        orders.forEach((o: any, i: number) => {
          let order = orders[i];
          toSold.forEach((tsorder: OrderJsonData, index) => {
            if (order.id === tsorder.id) {
              currentOrder = order;

              currentOrder.profit =
                tsorder.amount * price - tsorder.amount * tsorder.buy_price;
              currentOrder.status = "sold";
              orders[i] = currentOrder;

              const orderExcel: OrderExcelFile = {
                ...currentOrder,
                type: "MARKET",
                symbol: market,
                side: "SELL",
                total_price: parseFloat(sellOrder.cummulativeQuoteQty),
                commission: sellOrder.fills
                  ? parseFloat(sellOrder.fills[0].commission)
                  : 0,
              };

              promises.push(addOrderToExcel(orderExcel, ordersFileName));
            }
          });
        });

        await Promise.all(promises);

        store.put("orders", orders);
        store.put("start_price", price);
        await updateBalances();

        logColor(colors.green, "====================");
        logColor(
          colors.green,
          `Sold ${totalAmount} ${market1} for ${
            totalAmount * price
          } ${market2}, Price: ${price}\n`
        );
        logColor(colors.green, "====================");

        await calculateProfit();

        let i = orders.length;

        while (i--) {
          if (orders[i].status === "sold") {
            orders.splice(i, 1);
          }
        }
      } else store.put("start_price", price);
    } else store.put("start_price", price);
  } else store.put("start_price", price);
};

const broadcast = async () => {
  while (true) {
    try {
      const prices = await client.prices({ symbol: market });
      const markePrice = parseFloat(prices[market]);
      const startPrice = parseFloat(store.get("start_price"));

      if (markePrice) {
        console.clear();

        log("=====================================================");
        logProfit(markePrice);
        log("=====================================================");

        const entryPrice = store.get("entry_price") as number;
        const entryFactor = markePrice - entryPrice;
        const entryPercent = ((100 * entryFactor) / entryPrice).toFixed(2);
        log(
          `Entry price: ${entryPrice} ${market2} (${
            parseInt(entryPercent) <= 0 ? "" : "+"
          }${entryPercent}%)`
        );
        log("=====================================================");

        log(`Prev price: ${startPrice} ${market2}`);
        if (markePrice < startPrice) {
          let factor = startPrice - markePrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.red,
            `New price: ${markePrice} ${market2} ==> -${percentage.toFixed(3)}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= pricePercent) {
            await buy(markePrice, buyOrderAmount);
          }
        } else if (markePrice > startPrice) {
          let factor = markePrice - startPrice;
          let percentage = (factor / startPrice) * 100;

          logColor(
            colors.green,
            `New price: ${markePrice} ${market2} ==> +${percentage.toFixed(3)}%`
          );

          store.put("percentage", `${parseFloat(percentage.toFixed(3))}`);

          if (percentage >= pricePercent) {
            await sell(markePrice);
          }
        } else {
          logColor(colors.gray, "Change: 0.000% ==> $0.000");
          store.put("percentage", 0);
        }
      }
    } catch (error: any) {
      console.log(error);
      logError(error);
    }

    await sleep(process.env.SLEEP as unknown as number);
  }
};

const init = async () => {
  if (process.argv[2] === "resumen") {
    if (process.env.SELL_ALL_ON_START) await clearStart();

    const price = await getPrice(market);
    const balances = await checkBalance();

    store.put("start_price", price);
    store.put("entry_price", price);
    store.put("orders", []);
    store.put("total_profit", 0);
    store.put(
      `${market1?.toLocaleLowerCase()}_balance`,
      balances[market1]?.free
    );
    store.put(
      `${market2?.toLocaleLowerCase()}_balance`,
      balances[market2]?.free
    );
    store.put(
      `initial_${market1.toLowerCase()}_balance`,
      store.get(`${market1.toLowerCase()}_balance`)
    );
    store.put(
      `initial_${market2.toLowerCase()}_balance`,
      store.get(`${market2.toLowerCase()}_balance`)
    );

    //TODO: Verify if the order amount is less than $1
    if (price * buyOrderAmount < 5) {
      const requiredAmount = (1 / price).toFixed(8);
      logColor(
        colors.red,
        `Order amount (${buyOrderAmount}) is less than $1. Required amount should be at least ${requiredAmount}. Bot will not proceed.`
      );
      return;
    }
  }

  broadcast();
};

init();
