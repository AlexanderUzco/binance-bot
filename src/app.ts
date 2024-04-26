import {
  initBase,
  initBollinger,
  initBollingerMa,
  initRsi,
} from "./modules/runs";
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
  case "bollinger-ma":
    initBollingerMa();
    break;
  case "rsi":
    initRsi();
    break;
  default:
    console.log("Type run not found");
    break;
}
