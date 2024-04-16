export type GetQuantityT = {
  amount: number;
};

export type NewPriceResetT = {
  currentMarket: number;
  store: any;
  marketPrice: number;
};

export type UpdateBalancesT = {
  store: any;
};

export type CalculateProfitT = {
  store: any;
};

export type GetOrderIdT = {
  store: any;
};

export type MarketOrderT = {
  side: "SELL" | "BUY";
  amount: string;
};

export type GetRealProfitsT = {
  store: any;
  price: number;
};
