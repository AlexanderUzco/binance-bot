import * as ExcelJS from "exceljs";
import * as fs from "fs";
import { OrderExcelFile } from "../types/orders";

const addOrderToExcel = async (order: OrderExcelFile, fileName: string) => {
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
      { header: "Type", key: "type", width: 10 },
      { header: "Symbol", key: "symbol", width: 10 },
      { header: "Quantity", key: "amount", width: 10 },
      { header: "Market_Price", key: "sold_price", width: 15 },
      { header: "Total_Price", key: "total_price", width: 15 },
    ];
  }

  const rowData = [
    order.id,
    order.type,
    order.symbol,
    order.amount,
    order.sold_price,
    order.total_price,
  ];

  console.log(rowData);

  worksheet.addRow(rowData);

  await workbook.xlsx.writeFile(fileName).catch((error) => {
    console.log("Error saving the file", error);
    logError(error);
  });

  console.log(`Order saved to ${fileName}`);
};

const createOrdersFileName = (): string => {
  const ordersFolder = "./orders";

  if (!fs.existsSync(ordersFolder)) {
    fs.mkdirSync(ordersFolder);
  }

  const ordersFileName = `${ordersFolder}/orders_${Date.now()}.xlsx`;

  return ordersFileName;
};

const logError = (error: Error | Record<string, any>) => {
  let errorMessage = "";

  if (error instanceof Error) {
    errorMessage = `${new Date().toISOString()}: ${error.message}\n`;
  } else if (typeof error === "object") {
    errorMessage = `${new Date().toISOString()}: ${JSON.stringify(error)}\n`;
  } else {
    errorMessage = `${new Date().toISOString()}: Unknown error type\n`;
  }

  fs.appendFileSync("error.log", errorMessage);
};

export { addOrderToExcel, createOrdersFileName, logError };
