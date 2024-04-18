import {
  BOLLINGER_BANDS_PERCENT_BUY,
  BUY_ORDER_AMOUNT,
  MARKET,
  MARKET1,
  MARKET2,
} from "../../../../environments";
import {
  calculateProfit,
  getCandles,
  getQuantity,
  getRealProfits,
  newPriceReset,
  updateBalances,
} from "../../binanceFunctions";
import { bb } from "indicatorts";
import {
  ApplyBollingerStrategyT,
  BollingerOrderBuyT,
  BollingerOrderSellT,
} from "../../types/bollingerBands";
import { colors, log, logColor } from "../../../../utils/logger";
import { marketBuy } from "../../orderType/market/buyOrder";
import { OrderExcelFile, OrderJsonData } from "../../../../types/orders";
import { addOrderToExcel } from "../../../../utils/files";
import { getToSold, marketSell } from "../../orderType/market/sellOrder";
import { sendOrderMarketSold } from "../../../telegram/messages/orderMarketMessages";

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
}: BollingerOrderBuyT) => {
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
      let order: OrderJsonData = {
        id: buyOrder.orderId,
        buy_price: buyOrder.fills
          ? parseFloat(buyOrder.fills[0].price)
          : marketPrice,
        sell_price: priceToSell,
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
}: BollingerOrderSellT) => {
  const orders = store.get("orders");
  const toSold = getToSold({ store, price: marketPrice, changeStatus: true });

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
export { applyBollingerStrategy, bollingerOrderBuy, bollingerOrderSell };
