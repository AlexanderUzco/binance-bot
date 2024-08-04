# binance-bot (BIN-BOT)

Binance bot con Typescript y API Telegram!

# Advertencia

**Aviso Importante:** Este bot de Binance ha sido desarrollado para propósitos educativos y experimentales. El uso de este bot implica riesgos inherentes debido a la naturaleza volátil del mercado de criptomonedas. El desarrollador no se hace responsable por pérdidas financieras, daños, o cualquier otra consecuencia adversa derivada del uso de este bot. Al utilizar este software, aceptas y entiendes que operas bajo tu propio riesgo y responsabilidad. Asegúrate de comprender completamente el funcionamiento del bot y de las estrategias de trading antes de utilizarlo con fondos reales.

## Variables de entorno:

### Binance API

Configuracion de las Keys de Binance para poder Operar con el bot

**APIKEY:** API Key de la configuracion de Binance.
**SECRET:** Secret Key de la configuracion de Binance.

### Configuracion de par

**MARKET1:** Primer elemento del par de Cripto.
**MARKET2:** Segundo elemento del par de Cripto.

### Base Envs

Estrategia Base: Compra y vende en base a una diferencia del precio

**PRICE_PERCENT:** Porcentaje de Compra/venta.
**MIN_PRICE_TRANSACTION:** Precio minimo para realizar una transaccion, la cantidad de tokens debe ser igual al precio minimo de transaccion que acepta Binance dependiendo del par.
**BUY_ORDER_AMOUNT:** Cantidad de Tokens a comprar.

### Bollinger Bands Envs

Estrategia con bandas de bollinger

**BOLLINGER_BANDS_PERCENT_BUY:** Porcentaje del precio de comprar de las bandas de Bollinger tomando como referencia la banda inferior.
**BOLLINGER_BANDS_PERCENT_SELL:** Porcentaje del precio de venta de las bandas de Bollinger tomando como referencia el precio comprado de la banda inferior.

### RSI Envs

Aplicar estrategia de RSI

**APPLY_RSI:** Boolean para aplicar RSI.
**RSI_SUPPORT:** Suporte del RSI.
**RSI_RESISTANCE:** Resistencia del RSI.

### Common Envs

**STOP_LOSS_BOT:** Stop Loss del bot, al llegar al limite este se detendra.
**TAKE_PROFIT_BOT:** Take Profit del bot, al llegar al limite este se detendra.
**SELL_ALL_ON_START:** Vende los tokens existentes al momento de iniciar el bot para comenzar con un historial limpio.
**SELL_ALL_ON_CLOSE:** Al momento de deternse el bot ya sea por el take profit o el stop loss vendera los tokens existente.

## Telegram API

### Para configurar el bot de Telegran puedes seguir la siguiente [guia](https://sendpulse.com/latam/knowledge-base/chatbot/telegram/create-telegram-chatbot):

**TELEGRAM_BOT_TOKEN:** Token del bot para poder enviar mensajes.
**TELEGRAM_CHAT_ID:** ID del chat de telegram.

## Instalacion de los paquetes

Solo corriendo el siguiente comando podras usarlo:

```bash
npm i
```

## Comandos para trabajar con el bot

### Bot: Base

```bash
npm run bot:run-base
```

### Bot: Bollinger Bands

```bash
npm run bot:run-bollinger
```

### Bot: Bollinger Bands (MA - Moving Average)

```bash
npm run bot:run-bollinger-ma
```

### Bot: RSI (Relative Strength Index)

```bash
npm run bot:run-rsi
```
