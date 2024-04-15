import * as ExcelJS from "exceljs";
import * as fs from "fs";
import { OrderExcelFile } from "../../types/orders";
import { MARKET } from "../../environments";
import { AddOrderToExcelT } from "./types";

const addOrderToExcel = async ({ fileName, order }: AddOrderToExcelT) => {
  const workbook = new ExcelJS.Workbook();
  let worksheet: ExcelJS.Worksheet;

  let existingWorkbook: ExcelJS.Workbook | null = null;
  if (fs.existsSync(fileName)) {
    existingWorkbook = await workbook.xlsx.readFile(fileName);
  }

  if (
    existingWorkbook &&
    existingWorkbook.getWorksheet("Orders") !== undefined
  ) {
    worksheet = existingWorkbook.getWorksheet("Orders") as ExcelJS.Worksheet;
  } else {
    worksheet = workbook.addWorksheet("Orders");
    worksheet.columns = [
      { header: "ID", key: "id", width: 10 },
      { header: "Order", key: "side", width: 10 },
      { header: "Market", key: "symbol", width: 10 },
      { header: "Token_Quantity", key: "amount", width: 10 },
      { header: "Market_Price", key: "price", width: 15 },
      { header: "Commission", key: "commission", width: 15 },
      { header: "Total_Price", key: "total_price", width: 15 },
      { header: "Profit", key: "profit", width: 15 },
    ];
  }

  const rowData = [
    order.id,
    order.side,
    order.symbol,
    order.amount,
    order.price,
    order.commission,
    order.total_price,
    order.profit,
  ];

  console.log(rowData);

  worksheet.addRow(rowData);

  await workbook.xlsx.writeFile(fileName).catch((error) => {
    console.log("Error saving the file", error);
    logErrorFile(error);
  });

  console.log(`Order saved to ${fileName}`);
};

const createOrdersFileName = (): string => {
  const ordersFolder = "./analytics/orders";

  if (!fs.existsSync(ordersFolder)) {
    fs.mkdirSync(ordersFolder);
  }

  const ordersFileName = `${ordersFolder}/orders_${MARKET}_${Date.now()}.xlsx`;

  return ordersFileName;
};

const logErrorFile = (error: Error | Record<string, any>) => {
  let errorMessage = "";

  if (error instanceof Error) {
    errorMessage = `${new Date().toISOString()}: ${error.message}\n`;
  } else if (typeof error === "object") {
    errorMessage = `${new Date().toISOString()}: ${JSON.stringify(error)}\n`;
  } else {
    errorMessage = `${new Date().toISOString()}: Unknown error type\n`;
  }

  fs.appendFileSync("./analytics/error.log", errorMessage);
};

export { addOrderToExcel, createOrdersFileName, logErrorFile };
