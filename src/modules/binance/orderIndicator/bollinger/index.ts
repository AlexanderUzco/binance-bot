import {
  APPLY_RSI,
  BOLLIINGER_MA_STOP_LOSS,
  BOLLINGER_BANDS_STOP_LOSS_ORDER,
  BUY_ORDER_AMOUNT,
  MARKET,
  MARKET1,
  MARKET2,
  RSI_RESISTANCE,
  RSI_SUPPORT,
} from "../../../../environments";
import {
  calculateProfit,
  getQuantity,
  getRealProfits,
  newPriceReset,
  updateBalances,
} from "../../binanceFunctions";
import { bb } from "indicatorts";
import {
  ApplyBollingerStrategyT,
  BollingerCheckMAT,
  BollingerCheckOrdersT,
  BollingerOrderBuyT,
  BollingerOrderBuyWithMaT,
  BollingerOrderSellT,
  BollingerSellByOrderT,
} from "../../types/bollingerBands";
import { colors, log, logColor } from "../../../../utils/logger";
import { marketBuy } from "../../orderType/market/buyOrder";
import {
  BollingOrderJsonData,
  OrderExcelFile,
  OrderJsonData,
} from "../../../../types/orders";
import { addOrderToExcel } from "../../../../utils/files";
import { getToSold, marketSell } from "../../orderType/market/sellOrder";
import { sendOrderMarketSold } from "../../../telegram/messages/orderMarketMessages";
import { startStopLossCooldown } from "../../../../utils/commons";

const applyBollingerStrategy = async ({
  candleValues,
}: ApplyBollingerStrategyT) => {
  try {
    const defaultConfig = { period: 20 };

    const { upper, middle, lower } = bb(candleValues, defaultConfig);

    const currentUpper = upper[upper.length - 1];
    const currentMiddle = middle[middle.length - 1];
    const currentLower = lower[lower.length - 1];

    return {
      currentUpper,
      currentMiddle,
      currentLower,
    };
  } catch (error) {
    console.error("Error al aplicar la estrategia de Bollinger:", error);
  }
};

const bollingerOrderBuy = async ({
  priceToSell,
  marketPrice,
  store,
  ordersFileName,
  rsi,
}: BollingerOrderBuyT) => {
  if (rsi && rsi > RSI_SUPPORT) return;

  if (
    parseFloat(store.get(`${MARKET2?.toLocaleLowerCase()}_balance`)) >
    BUY_ORDER_AMOUNT * marketPrice
  ) {
    let orders = store.get("orders");

    log(`
    Type: Bollinger Bands
    Buying ${MARKET1}
    ==============================================
    Amount In: ${(BUY_ORDER_AMOUNT * marketPrice).toFixed(2)} ${MARKET2}
    Amount Out: ${BUY_ORDER_AMOUNT} ${MARKET1}
    `);

    const buyOrder = await marketBuy({
      amount: BUY_ORDER_AMOUNT.toString(),
    });

    if (buyOrder.status === "FILLED") {
      let orderBuyPrice = buyOrder.fills
        ? parseFloat(buyOrder.fills[0].price)
        : marketPrice;

      let order: BollingOrderJsonData = {
        id: buyOrder.orderId,
        buy_price: orderBuyPrice,
        sell_price: priceToSell,
        sold_price: 0,
        status: "bought",
        profit: 0,
        amount: buyOrder.fills
          ? parseFloat(buyOrder.executedQty) -
            (buyOrder.fills[0].commission as unknown as number)
          : parseFloat(buyOrder.executedQty),
        sl_price:
          orderBuyPrice -
          orderBuyPrice * (BOLLINGER_BANDS_STOP_LOSS_ORDER / 100),
        ma_check: null,
      };

      let orderExcel: OrderExcelFile = {
        ...order,
        price: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].price)
          : marketPrice,
        type: "MARKET",
        symbol: MARKET,
        side: "BUY",
        total_price: parseFloat(buyOrder.cummulativeQuoteQty),
        commission: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].commission)
          : 0,
      };

      orders.push(order);
      store.put("orders", orders);
      store.put("start_price", order.buy_price);

      await updateBalances({ store });

      logColor(colors.green, "====================");
      logColor(
        colors.green,
        `Bought ${order.amount} ${MARKET1} for ${(
          order.amount * marketPrice
        ).toFixed(2)} ${MARKET2}, Price: ${order.buy_price}\n`
      );
      logColor(colors.green, "====================");

      await calculateProfit({ store });

      await addOrderToExcel({
        order: orderExcel,
        fileName: ordersFileName,
      });
    } else
      newPriceReset({
        currentMarket: 1,
        store,
        marketPrice: marketPrice,
      });
  } else
    newPriceReset({
      currentMarket: 1,
      store,
      marketPrice: marketPrice,
    });
};

const bollingerOrderBuyWithMa = async ({
  marketPrice,
  store,
  ordersFileName,
}: BollingerOrderBuyWithMaT) => {
  if (
    parseFloat(store.get(`${MARKET2?.toLocaleLowerCase()}_balance`)) >
    BUY_ORDER_AMOUNT * marketPrice
  ) {
    let orders = store.get("orders");

    log(`
    Type: Bollinger Bands
    Buying ${MARKET1}
    ==============================================
    Amount In: ${(BUY_ORDER_AMOUNT * marketPrice).toFixed(2)} ${MARKET2}
    Amount Out: ${BUY_ORDER_AMOUNT} ${MARKET1}
    `);

    const buyOrder = await marketBuy({
      amount: BUY_ORDER_AMOUNT.toString(),
    });

    if (buyOrder.status === "FILLED") {
      let orderBuyPrice = buyOrder.fills
        ? parseFloat(buyOrder.fills[0].price)
        : marketPrice;

      let slOrder =
        orderBuyPrice - orderBuyPrice * (BOLLINGER_BANDS_STOP_LOSS_ORDER / 100);

      let totalAmoutToken =
        buyOrder.fills && buyOrder.fills.length > 0
          ? parseFloat(buyOrder.executedQty) -
            buyOrder.fills.reduce(
              (acc, fill) => acc + parseFloat(fill.commission),
              0
            )
          : parseFloat(buyOrder.executedQty);

      let order: BollingOrderJsonData = {
        id: buyOrder.orderId,
        buy_price: orderBuyPrice,
        sell_price: 0,
        sold_price: 0,
        status: "bought",
        profit: 0,
        amount: totalAmoutToken,
        sl_price: slOrder,
        ma_check: null,
        allData: buyOrder,
      };

      let orderExcel: OrderExcelFile = {
        ...order,
        price: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].price)
          : marketPrice,
        type: "MARKET",
        symbol: MARKET,
        side: "BUY",
        total_price: parseFloat(buyOrder.cummulativeQuoteQty),
        commission: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].commission)
          : 0,
      };

      orders.push(order);
      store.put("orders", orders);
      store.put("start_price", order.buy_price);

      await updateBalances({ store });

      logColor(colors.green, "====================");
      logColor(
        colors.green,
        `Bought ${order.amount} ${MARKET1} for ${(
          order.amount * marketPrice
        ).toFixed(2)} ${MARKET2}, Price: ${order.buy_price}\n`
      );
      logColor(colors.green, "====================");

      await calculateProfit({ store });

      await addOrderToExcel({
        order: orderExcel,
        fileName: ordersFileName,
      });
    } else
      newPriceReset({
        currentMarket: 1,
        store,
        marketPrice: marketPrice,
      });
  } else
    newPriceReset({
      currentMarket: 1,
      store,
      marketPrice: marketPrice,
    });
};

const bollingerOrderSell = async ({
  marketPrice,
  store,
  ordersFileName,
  rsi,
}: BollingerOrderSellT) => {
  if (rsi && rsi < RSI_RESISTANCE) return;
  const orders = store.get("orders");
  const toSold = getToSold({
    store,
    price: marketPrice,
    changeStatus: true,
    rsi,
  });

  if (toSold.length > 0) {
    const totalAmount = toSold.reduce(
      (acc: number, order: any) => acc + order.amount,
      0
    );

    if (
      totalAmount > 0 &&
      parseFloat(store.get(`${MARKET1?.toLocaleLowerCase()}_balance`)) >=
        totalAmount
    ) {
      const lotQuantity = await getQuantity({ amount: totalAmount });
      const sellOrder = await marketSell({
        amount: lotQuantity.toString(),
      });

      if (sellOrder.status === "FILLED") {
        const promises: Promise<void>[] = [];

        let currentOrder: OrderJsonData;

        orders.forEach((o: any, i: number) => {
          let order = orders[i];
          toSold.forEach((tsorder: OrderJsonData, index) => {
            if (order.id === tsorder.id) {
              currentOrder = order;

              currentOrder.profit =
                tsorder.amount * marketPrice -
                tsorder.amount * tsorder.buy_price;
              currentOrder.status = "sold";
              orders[i] = currentOrder;

              const orderExcel: OrderExcelFile = {
                ...currentOrder,
                price: sellOrder.fills
                  ? parseFloat(sellOrder.fills[0].price)
                  : marketPrice,
                type: "MARKET",
                symbol: MARKET,
                side: "SELL",
                total_price: parseFloat(sellOrder.cummulativeQuoteQty),
                commission: sellOrder.fills
                  ? parseFloat(sellOrder.fills[0].commission)
                  : 0,
              };

              promises.push(
                addOrderToExcel({
                  order: orderExcel,
                  fileName: ordersFileName,
                })
              );

              const totalSoldProfit = getRealProfits({
                price: marketPrice,
                store,
              });

              sendOrderMarketSold({
                symbol: MARKET,
                price: sellOrder.fills
                  ? parseFloat(sellOrder.fills[0].price)
                  : marketPrice,
                amount: tsorder.amount,
                profit: currentOrder.profit,
                totalSoldProfit,
              });
            }
          });
        });

        await Promise.all(promises);

        store.put("orders", orders);
        store.put("start_price", marketPrice);
        await updateBalances({ store });

        logColor(colors.green, "====================");
        logColor(
          colors.green,
          `Sold ${totalAmount} ${MARKET1} for ${
            totalAmount * marketPrice
          } ${MARKET2}, Price: ${marketPrice}\n`
        );
        logColor(colors.green, "====================");

        await calculateProfit({ store });

        let i = orders.length;

        while (i--) {
          if (orders[i].status === "sold") {
            orders.splice(i, 1);
          }
        }
      } else store.put("start_price", marketPrice);
    } else store.put("start_price", marketPrice);
  } else store.put("start_price", marketPrice);
};

const bollingerSellByOrder = async ({
  marketPrice,
  store,
  ordersFileName,
  order,
}: BollingerSellByOrderT) => {
  if (
    parseFloat(store.get(`${MARKET1?.toLocaleLowerCase()}_balance`)) >=
    order.amount
  ) {
    let orders = store.get("orders");
    const sellOrder = await marketSell({
      amount: order.amount.toString(),
    });

    if (sellOrder.status === "FILLED") {
      let currentOrder = order;

      currentOrder.profit =
        currentOrder.amount * marketPrice -
        currentOrder.amount * currentOrder.buy_price;
      currentOrder.status = "sold";

      const orderExcel: OrderExcelFile = {
        ...currentOrder,
        price: sellOrder.fills
          ? parseFloat(sellOrder.fills[0].price)
          : marketPrice,
        type: "MARKET",
        symbol: MARKET,
        side: "SELL",
        total_price: parseFloat(sellOrder.cummulativeQuoteQty),
        commission: sellOrder.fills
          ? parseFloat(sellOrder.fills[0].commission)
          : 0,
      };

      const totalSoldProfit = getRealProfits({
        price: marketPrice,
        store,
      });

      await addOrderToExcel({
        order: orderExcel,
        fileName: ordersFileName,
      });

      sendOrderMarketSold({
        symbol: MARKET,
        price: sellOrder.fills
          ? parseFloat(sellOrder.fills[0].price)
          : marketPrice,
        amount: currentOrder.amount,
        profit: currentOrder.profit,
        totalSoldProfit,
      });

      store.put("start_price", marketPrice);

      await updateBalances({ store });

      logColor(colors.green, "====================");
      logColor(
        colors.green,
        `Sold ${currentOrder.amount} ${MARKET1} for ${
          currentOrder.amount * marketPrice
        } ${MARKET2}, Price: ${marketPrice}\n`
      );
      logColor(colors.green, "====================");

      await calculateProfit({ store });

      let i = orders.length;

      while (i--) {
        if (orders[i].status === "sold") {
          orders.splice(i, 1);
        }
      }

      store.put("orders", orders);
    } else store.put("start_price", marketPrice);
  } else store.put("start_price", marketPrice);
};

const bollingerCheckOrders = async ({
  marketPrice,
  store,
  ordersFileName,
  currentMiddle,
}: BollingerCheckOrdersT) => {
  const orders = store.get("orders");
  await Promise.all(
    orders.map(async (order: BollingOrderJsonData) => {
      if (order.status === "bought") {
        const { id, sl_price, ma_check } = order;

        // Verify Stop Loss Order
        if (marketPrice <= sl_price) {
          logColor(colors.red, `Stop loss order activated for order ${id}`);

          store.put("stop_loss_cooldown", startStopLossCooldown());

          await bollingerSellByOrder({
            marketPrice,
            store,
            ordersFileName,
            order,
          });
        }

        // Verify MA check Stop Loss
        if (!ma_check) return;

        if (BOLLIINGER_MA_STOP_LOSS) {
          const maStopLoss =
            ma_check - ma_check * (BOLLIINGER_MA_STOP_LOSS / 100);

          if (marketPrice <= maStopLoss) {
            logColor(
              colors.red,
              `MA Stop loss order activated for order ${id}`
            );

            await bollingerSellByOrder({
              marketPrice,
              store,
              ordersFileName,
              order,
            });
          }
        }

        if (ma_check <= currentMiddle) {
          logColor(colors.red, `MA Sell order activated for order ${id}`);

          await bollingerSellByOrder({
            marketPrice,
            store,
            ordersFileName,
            order,
          });
        }
      }
    })
  );
};

const bollingerCheckMA = ({
  store,
  currentMiddle,
  marketPrice,
}: BollingerCheckMAT) => {
  const orders: BollingOrderJsonData[] = store.get("orders");
  let orderToUpdate: BollingOrderJsonData[] = [];

  orders.forEach((order) => {
    let newOrder = order;

    if (order.status === "bought") {
      // Set MA check
      if (order.ma_check === null && marketPrice > currentMiddle) {
        order.ma_check = marketPrice;
        return orderToUpdate.push(order);
      }

      if (!order.ma_check) return;

      let newMaCheck = order.ma_check + order.ma_check * (0.2 / 100);

      marketPrice >= newMaCheck && (newOrder.ma_check = newMaCheck);

      return orderToUpdate.push(newOrder);
    }
  });

  if (orderToUpdate.length > 0) {
    let newOrders = orders.map((o) => {
      let order = orderToUpdate.find((ot) => ot.id === o.id);
      return order ? order : o;
    });

    store.put("orders", newOrders);
  }
};

export {
  applyBollingerStrategy,
  bollingerOrderBuy,
  bollingerOrderSell,
  bollingerSellByOrder,
  bollingerCheckOrders,
  bollingerOrderBuyWithMa,
  bollingerCheckMA,
};
