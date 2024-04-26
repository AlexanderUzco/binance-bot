import { BollingOrderJsonData } from "../../../types/orders";

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

export type BollingerOrderBuyWithMaT = {
  marketPrice: number;
  store: any;
  ordersFileName: string;
};

export type BollingerOrderSellT = {
  marketPrice: number;
  store: any;
  ordersFileName: string;
  rsi?: number;
};

export type BollingerSellByOrderT = {
  marketPrice: number;
  store: any;
  ordersFileName: string;
  order: BollingOrderJsonData;
};

export type BollingerCheckOrdersT = {
  marketPrice: number;
  store: any;
  ordersFileName: string;
  currentMiddle: number;
};

export type BollingerCheckMAT = {
  marketPrice: number;
  store: any;
  currentMiddle: number;
};
