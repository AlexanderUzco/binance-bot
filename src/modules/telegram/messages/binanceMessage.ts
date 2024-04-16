import { sendMessage } from ".";
import { SendProfitUpdateMessageT } from "../types/messages";

const sendProfitUpdateMessage = ({
  realProfit,
  totalSold,
  totalAmount,
  price,
  type,
}: SendProfitUpdateMessageT) => {
  const existTotalSold = totalSold
    ? `💰Total Sold: $${totalSold.toFixed(8)} USDT ${
        totalAmount ? `${totalAmount} x ${price}` : ""
      }`
    : "";
  const existTotalAmount = totalAmount
    ? `📈Total Amount: ${totalAmount} BONK`
    : "";

  const message = `
🤖 Bin-Bot: OFF 🛑

📈 ${type === "takeProfit" ? "Take profit" : "Stop loss"} Update:
💸Total Profit: $${realProfit.toFixed(8)}USDT
${existTotalSold}
${existTotalAmount}
🚀 Thank you for using our Binance Bot! Happy trading! 📊
  `;

  sendMessage(message);
};

export { sendProfitUpdateMessage };
