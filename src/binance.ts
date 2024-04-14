import Binance from 'binance-api-node';

const client = Binance({
    apiKey: process.env.APIKEY,
    apiSecret: process.env.SECRET,
    getTime: () => Date.now(),
});

export default client;