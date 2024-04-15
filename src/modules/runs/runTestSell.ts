require("dotenv").config();
import { colors, logColor, log } from "../../utils/logger";
import client from "../binance";
import { NewOrderSpot, OrderType } from "binance-api-node";
import { addOrderToExcel, createOrdersFileName } from "../../utils/files";

const ordersFileName = createOrdersFileName();
const market = `${process.env.MARKET1}${process.env.MARKET2}`;
const amount = process.env.BUY_ORDER_AMOUNT as unknown as number;

const sell = async (): Promise<void> => {
  try {
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

    const orderData = {
      symbol: market,
      side: "SELL",
      quantity,
      type: OrderType.MARKET,
    };

    const order = await client.order(orderData as NewOrderSpot);

    await addOrderToExcel(
      {
        ...orderData,
        id: order.orderId,
        total_price: parseFloat(order.cummulativeQuoteQty),
        status: order.status,
        commission: (order.fills && parseFloat(order.fills[0].commission)) || 0,
        buy_price: 0,
        sell_price: 0,
        sold_price: (order.fills && parseFloat(order.fills[0].price)) || 0,
        amount: parseFloat(quantity),
      },
      ordersFileName
    );

    logColor(colors.green, `Order placed: ${order.orderId}`);
  } catch (error: any) {
    logColor(colors.red, `Error placing order: ${error.message}`);
  }
};

sell();
