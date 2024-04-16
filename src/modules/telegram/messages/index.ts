import { bot } from "..";
import { TELEGRAM_CHAT_ID } from "../../../environments";
import { SendOrderMarketSoldT } from "../types/messages";

const sendMessage = (message: string) => {
  if (!bot || !TELEGRAM_CHAT_ID) return;

  bot.sendMessage(TELEGRAM_CHAT_ID, message);
};

export { sendMessage };
