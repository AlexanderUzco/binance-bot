export type ApplyBollingerStrategyT = {
  candleValues: number[];
};

export type BollingerOrderBuyT = {
  marketPrice: number;
  priceToSell: number;
  store: any;
  ordersFileName: string;
  rsi?: number;
};

export type BollingerOrderSellT = {
  marketPrice: number;
  store: any;
  ordersFileName: string;
  rsi?: number;
};
