import client from "../..";
import {
  calculateProfit,
  getOrderId,
  getQuantity,
  marketOrder,
  newPriceReset,
  updateBalances,
} from "../../binanceFunctions";
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
} from "../../../../environments";
import {
  GetToSoldT,
  MarketOrderSellT,
  MarketSellT,
} from "../../types/orderMarket";
import { colors, log, logColor } from "../../../../utils/logger";
import { OrderExcelFile, OrderJsonData } from "../../../../types/orders";
import { addOrderToExcel } from "../../../../utils/files";

const marketSell = async ({ amount }: MarketSellT) => {
  return await marketOrder({ side: "SELL", amount });
};

const getToSold = ({ store, price, changeStatus }: GetToSoldT) => {
  const orders = store.get("orders");
  const toSold = [];

  for (var i = 0; i < orders.length; i++) {
    var order = orders[i];
    if (
      price >= order.sell_price ||
      (getOrderId({ store }) === order.id &&
        store.get(`${MARKET2.toLowerCase()}_balance`) < BUY_ORDER_AMOUNT)
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

const marketOrderSell = async ({
  price,
  store,
  ordersFileName,
}: MarketOrderSellT) => {
  const orders = store.get("orders");
  const toSold = getToSold({ store, price, changeStatus: true });

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
      const lotQuantity = await getQuantity(totalAmount);
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
                tsorder.amount * price - tsorder.amount * tsorder.buy_price;
              currentOrder.status = "sold";
              orders[i] = currentOrder;

              const orderExcel: OrderExcelFile = {
                ...currentOrder,
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
            }
          });
        });

        await Promise.all(promises);

        store.put("orders", orders);
        store.put("start_price", price);
        await updateBalances({ store });

        logColor(colors.green, "====================");
        logColor(
          colors.green,
          `Sold ${totalAmount} ${MARKET1} for ${
            totalAmount * price
          } ${MARKET2}, Price: ${price}\n`
        );
        logColor(colors.green, "====================");

        await calculateProfit({ store });

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

export { marketSell, getToSold, marketOrderSell };
