import { OrderExcelFile } from "../../types/orders";

export type AddOrderToExcelT = {
  order: OrderExcelFile;
  fileName: string;
};

export type CreateOrdersFileNameT = {
  botRun: "base" | "bollinger";
};
