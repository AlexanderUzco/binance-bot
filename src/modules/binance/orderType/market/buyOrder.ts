import client from "../..";
import {
  calculateProfit,
  marketOrder,
  newPriceReset,
  updateBalances,
} from "../../binanceFunctions";
import {
  MARKET1,
  MARKET2,
  MARKET,
  BUY_ORDER_AMOUNT,
  PRICE_PERCENT,
} from "../../../../environments";
import { MarketBuyT, MarketOrderBuyT } from "../../types/orderMarket";
import { colors, log, logColor } from "../../../../utils/logger";
import { OrderExcelFile, OrderJsonData } from "../../../../types/orders";
import { addOrderToExcel } from "../../../../utils/files";

const marketBuy = async ({ amount }: MarketBuyT) => {
  return await marketOrder({
    side: "BUY",
    amount,
  });
};

async function getMinBuy() {
  const { symbols } = await client.exchangeInfo({ symbol: MARKET });
  // TODO: Check if the minNotional is not found
  //@ts-ignore
  const { minNotional } = symbols[0].filters.find(
    //@ts-ignore
    (filter) => filter.filterType === "NOTIONAL"
  );

  return parseFloat(minNotional);
}

const marketOrderBuy = async ({
  price,
  amount,
  store,
  ordersFileName,
}: MarketOrderBuyT) => {
  if (
    parseFloat(store.get(`${MARKET2?.toLocaleLowerCase()}_balance`)) >
    BUY_ORDER_AMOUNT * price
  ) {
    let orders = store.get("orders");
    let factor = (PRICE_PERCENT * price) / 100;

    log(`
              Buying ${MARKET1}
              ==============================================
              Amount In: ${(BUY_ORDER_AMOUNT * price).toFixed(2)} ${MARKET2}
              Amount Out: ${BUY_ORDER_AMOUNT} ${MARKET1}
          `);

    const buyOrder = await marketBuy({
      amount: amount.toString(),
    });

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
        `Bought ${order.amount} ${MARKET1} for ${(order.amount * price).toFixed(
          2
        )} ${MARKET2}, Price: ${order.buy_price}\n`
      );
      logColor(colors.green, "====================");

      await calculateProfit({ store });

      await addOrderToExcel(orderExcel, ordersFileName);
    } else
      newPriceReset({
        currentMarket: 1,
        store,
        marketPrice: price,
      });
  } else
    newPriceReset({
      currentMarket: 1,
      store,
      marketPrice: price,
    });
};

export { marketBuy, marketOrderBuy, getMinBuy };
