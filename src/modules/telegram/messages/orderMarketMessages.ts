import { sendMessage } from ".";
import { SendOrderMarketSoldT } from "../types/messages";

const sendOrderMarketSold = ({
  symbol,
  price,
  amount,
  profit,
  totalSoldProfit,
}: SendOrderMarketSoldT) => {
  const message = `
🚀 Successful Sale! 🎉

Hooray! A sale has been successfully executed!

📊 Symbol: ${symbol}
💰 Price: $${price.toFixed(8)}
📈 Amount: ${amount}
💸 Profit: $${profit.toFixed(8)}
📈 Real Profit: $${totalSoldProfit.toFixed(8)}
`;

  sendMessage(message);
};

export { sendOrderMarketSold };
