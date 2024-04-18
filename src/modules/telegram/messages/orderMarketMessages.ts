import { sendMessage } from ".";
import { SendBotActivatedT, SendOrderMarketSoldT } from "../types/messages";

let sendedFirstMessage = false;

const sendBotActivated = ({ botRun }: SendBotActivatedT) => {
  const message = `
  🚀 Bot: (${botRun}) has been activated! 🎉`;
  sendMessage(message);
};

const sendOrderMarketSold = ({
  symbol,
  price,
  amount,
  profit,
  totalSoldProfit,
}: SendOrderMarketSoldT) => {
  const message = `
  ${
    !sendedFirstMessage
      ? ` 
🚀 Successful Sale! 🎉

Hooray! A sale has been successfully executed! (${symbol}) 🎉
`
      : `
Sold order has been executed! (${symbol}) 🎉
`
  }

💰 Price: $${price.toFixed(8)}
📈 Tokens: ${amount}
📈 Amount: $${(price * amount).toFixed(8)}
💸 Profit: $${profit.toFixed(8)}
📈 Real Profit: $${totalSoldProfit.toFixed(8)}
`;
  if (!sendedFirstMessage) sendedFirstMessage = true;

  sendMessage(message);
};

export { sendOrderMarketSold, sendBotActivated };
