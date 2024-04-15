// Crear a Order Type

export interface OrderJsonData {
  id: number;
  buy_price: number;
  sell_price: number;
  sold_price: number;
  status: string;
  profit?: number;
  amount: number;
}

export interface OrderExcelFile {
  id: number;
  type: string;
  symbol: string;
  side: string;
  amount: number;
  total_price: number;
  commission: number;
  price: number;
  profit?: number;
}
