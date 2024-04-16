export type SendOrderMarketSoldT = {
  symbol: string;
  price: number;
  amount: number;
  profit: number;
  totalSoldProfit: number;
};

export type SendProfitUpdateMessageT = {
  realProfit: number;
  type: "takeProfit" | "stopLoss";
  totalSold?: number;
  totalAmount?: number;
  price?: number;
};
