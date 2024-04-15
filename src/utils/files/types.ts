import { OrderExcelFile } from "../../types/orders";

export type AddOrderToExcelT = {
  order: OrderExcelFile;
  fileName: string;
};
