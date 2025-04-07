import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
import re

# Token del bot
TOKEN = "7722563060:AAHn9pqJsKuH7vIFrljsJmDfKsVbSBI7oq4"

# Estados para ConversationHandler
INGRESAR_MONTO = 1

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Obtener mejor precio BRL (compra) con mínimo <= 100
def obtener_mejor_precio_brl_binance():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    precios_validos = []

    for page in [1, 2]:
        payload = {
            "asset": "USDT",
            "fiat": "BRL",
            "tradeType": "BUY",
            "page": page,
            "rows": 20,
            "proMerchant": False,
            "shieldMerchant": False
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            for item in data:
                adv = item["adv"]
                if float(adv["minSingleTransAmount"]) <= 100:
                    precios_validos.append(float(adv["price"]))
        except Exception as e:
            print(f"Error BRL: {e}")

    return min(precios_validos) if precios_validos else None

# Obtener promedio BOB (venta) con mínimo <= 100
def obtener_promedio_bob_binance():
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json"}
    payload = {
        "asset": "USDT",
        "fiat": "BOB",
        "tradeType": "SELL",
        "page": 2,
        "rows": 4,
        "proMerchant": False,
        "shieldMerchant": False
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json().get("data", [])
        precios = [float(item["adv"]["price"]) for item in data if float(item["adv"]["minSingleTransAmount"]) <= 100]
        if precios:
            return (sum(precios) / len(precios)) - 0.02
    except Exception as e:
        print(f"Error BOB: {e}")

    return None

# Manejar mensaje "cambio"
async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()
    print(f"Mensaje recibido: {texto}")

    if texto == "cambio":
        brl = obtener_mejor_precio_brl_binance()
        bob = obtener_promedio_bob_binance()

        if brl is None or bob is None:
            await update.message.reply_text("⚠️ No se pudieron obtener datos de Binance.")
            return

        tipo_cambio_actual = bob / brl

        def calcular_info_cambio(monto_brl, porcentaje):
            tipo_cambio_con_margen = tipo_cambio_actual * (1 - porcentaje / 100)
            precio_venta_bob = monto_brl * tipo_cambio_con_margen
            ganancia_bob = (monto_brl * tipo_cambio_actual) - precio_venta_bob - 0.05
            ganancia_brl = ganancia_bob / tipo_cambio_actual
            return {
                "tc": round(tipo_cambio_con_margen, 2),
                "ganancia_bob": round(ganancia_bob, 2),
                "ganancia_brl": round(ganancia_brl, 2)
            }

        info_1000 = calcular_info_cambio(1000, 4)
        info_500 = calcular_info_cambio(500, 5)
        info_100 = calcular_info_cambio(100, 6)
        info_99 = calcular_info_cambio(99, 7)

        # Calculo reverso BOB -> BRL
        precio_compra_usdt_bob = bob
        precio_venta_usdt_brl = brl
        usdt_obtenidos = 1 - 0.05
        tipo_cambio_bob_brl = precio_compra_usdt_bob / (usdt_obtenidos * precio_venta_usdt_brl)

        respuesta = (
            f"💰 Mejor precio BRL (compra): R${brl}\n"
            f"💵 Promedio precio BOB (venta): Bs{bob:.2f}\n"
            f"🔁 Tipo de cambio actual: {tipo_cambio_actual:.4f} Bs/BRL\n\n"

            f"- Cambio *acima* de 1000 R$ *R$ a BS* {info_1000['tc']}\n"
            f"  → Ganancia estimada: Bs{info_1000['ganancia_bob']} | R${info_1000['ganancia_brl']}\n\n"

            f"- Cambio *acima* de 500 R$ *R$ a BS* {info_500['tc']}\n"
            f"  → Ganancia estimada: Bs{info_500['ganancia_bob']} | R${info_500['ganancia_brl']}\n\n"

            f"- Cambio *acima* de 100 R$ *R$ a BS* {info_100['tc']}\n"
            f"  → Ganancia estimada: Bs{info_100['ganancia_bob']} | R${info_100['ganancia_brl']}\n\n"

            f"- Cambio *abaixo* de 100 R$ *R$ a BS* {info_99['tc']}\n"
            f"  → Ganancia estimada: Bs{info_99['ganancia_bob']} | R${info_99['ganancia_brl']}\n\n"

            f"🔁 *Cambio BOB → BRL*: {tipo_cambio_bob_brl:.2f}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Ingresar monto en BRL", callback_data="ingresar_monto")]
        ])

        await update.message.reply_text(respuesta, parse_mode="Markdown", reply_markup=keyboard)
        return

    # Comando manual: cambiar 100 brl con 8%
    match = re.match(r"cambiar (\d+(?:\.\d+)?) brl con (\d+(?:\.\d+)?)%", texto)
    if match:
        monto_brl = float(match.group(1))
        porcentaje = float(match.group(2))

        await calcular_y_responder(update, monto_brl, porcentaje)
        return

    await update.message.reply_text("❗ Formato inválido. Usa: cambiar 100 brl con 8% o escribe 'cambio'.")

# Función de cálculo y respuesta detallada
async def calcular_y_responder(update: Update, monto_brl, porcentaje):
    brl = obtener_mejor_precio_brl_binance()
    bob = obtener_promedio_bob_binance()

    if brl is None or bob is None:
        await update.message.reply_text("⚠️ No se pudieron obtener datos de Binance.")
        return

    tipo_cambio_actual = bob / brl
    tipo_cambio_con_margen = tipo_cambio_actual * (1 - porcentaje / 100)
    precio_venta_bob = monto_brl * tipo_cambio_con_margen
    ganancia_estimada = (monto_brl * tipo_cambio_actual) - precio_venta_bob - 0.05
    ganancia_en_reales = ganancia_estimada / tipo_cambio_actual

    respuesta = (
        f"💰 Mejor precio BRL (compra): R${brl}\n"
        f"💵 Promedio precio BOB (venta): Bs{bob:.2f}\n"
        f"🔁 Tipo de cambio actual Bs/BRL: {tipo_cambio_actual:.4f}\n"
        f"🧮 Tipo de cambio con margen del {porcentaje}%: {tipo_cambio_con_margen:.4f}\n"
        f"💸 Precio de venta estimado: Bs{precio_venta_bob:.2f}\n"
        f"📈 Ganancia estimada (–0.05 USDT): Bs{ganancia_estimada:.2f}\n"
        f"🇧🇷 Ganancia estimada en reales: R${ganancia_en_reales:.2f}"
    )

    await update.message.reply_text(respuesta)

# Callback del botón
async def manejar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ingresar_monto":
        await query.message.reply_text("📩 Escribe el monto en BRL que deseas cambiar:")
        return INGRESAR_MONTO

# Función cuando el usuario ingresa un monto
async def recibir_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto_brl = float(update.message.text)
        if monto_brl > 1000:
            porcentaje = 4
        elif monto_brl > 500:
            porcentaje = 5
        elif monto_brl > 100:
            porcentaje = 6
        else:
            porcentaje = 7
        await calcular_y_responder(update, monto_brl, porcentaje)
    except ValueError:
        await update.message.reply_text("❗ Por favor, ingresa un número válido.")
    return ConversationHandler.END

# Cancelar conversación
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return ConversationHandler.END

# Main
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(manejar_callback)],
        states={
            INGRESAR_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_monto)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancelar)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))

    print("🤖 Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
