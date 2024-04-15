declare module "binance-api-node" {
  export function futuresCancelBatchOrders(options: {
    symbol: string;
    timestamp?: number;
  }): any;
}
