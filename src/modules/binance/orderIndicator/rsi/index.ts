import { rsi } from "indicatorts";
import { GetRsiValuesT } from "../../types/rsi";

const getRsiValues = ({ candleValues }: GetRsiValuesT) => {
  const defaultConfig = { period: 14 };
  const result = rsi(candleValues, defaultConfig);

  return result;
};
export { getRsiValues };
