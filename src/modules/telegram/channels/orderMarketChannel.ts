import { bot } from "../";
import { TELEGRAM_CHAT_ID } from "../../../environments";
import { SendOrderMarketSoldT } from "../types/channels";

const sendMessage = (message: string) => {
  if (!bot || !TELEGRAM_CHAT_ID) return;

  bot.sendMessage(TELEGRAM_CHAT_ID, message);
};

const sendOrderMarketSold = ({
  symbol,
  price,
  amount,
  profit,
}: SendOrderMarketSoldT) => {
  const message = `
🚀 Successful Sale! 🎉

Hooray! A sale has been successfully executed!

📊 Symbol: ${symbol}
💰 Price: $${price.toFixed(8)}
📈 Amount: ${amount}
💸 Profit: $${profit.toFixed(8)}
`;

  sendMessage(message);
};

export { sendOrderMarketSold, sendMessage };
