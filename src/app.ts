import initBase from "./modules/runs/base";
import initBollinger from "./modules/runs/bollingerBands";
import { sendBotActivated } from "./modules/telegram/messages/orderMarketMessages";
const typeRun = process.argv[2];

sendBotActivated({ botRun: typeRun });

switch (typeRun) {
  case "base":
    initBase();
    break;
  case "bollinger":
    initBollinger();
    break;
  default:
    console.log("Type run not found");
    break;
}
