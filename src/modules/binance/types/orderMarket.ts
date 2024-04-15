export type MarketBuyT = {
  amount: string;
};

export type MarketOrderBuyT = {
  price: number;
  amount: number;
  store: any;
  ordersFileName: string;
};

export type MarketSellT = {
  amount: string;
};

export type GetToSoldT = {
  store: any;
  price: number;
  changeStatus: boolean;
};

export type MarketOrderSellT = {
  price: number;
  store: any;
  ordersFileName: string;
};
