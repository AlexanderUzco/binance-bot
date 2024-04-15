import TelegramBot = require("node-telegram-bot-api");

import { TELEGRAM_BOT_TOKEN } from "../../environments";

const token = TELEGRAM_BOT_TOKEN;

let bot: TelegramBot | null = null;

if (token) {
  let currentBotInstance = new TelegramBot(token, { polling: true });

  currentBotInstance.on("message", (msg) => {
    const chatId = msg.chat.id;
    currentBotInstance.sendMessage(
      chatId,
      "Received your message, your chat id is: " + chatId
    );
  });

  bot = currentBotInstance;
}

export { bot };
