import asyncio
import logging
import os
import time
from collections import deque
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "9002976959:AAF-D--huVymGwOBxuKrJxgoJ4mK_rybS3c"

bot = Bot(token=BOT_TOKEN)




logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class SettingsState(StatesGroup):
    waiting_long_min = State()
    waiting_long_pct = State()
    waiting_short_min = State()
    waiting_short_pct = State()


config = {
    "running": True,
    "chat_id": None,
    "long_pct": 2.0,
    "long_min": 2,
    "short_pct": 10.0,
    "short_min": 20,
    "bybit": True,
    "bingx": True,
    "long_on": True,
    "short_on": True,
    "cooldown": 180
}

price_history = {}
last_alerts = {}
signals_24h = {}

exchange_stats = {
    "ByBit": "Ждём первый запрос...",
    "BingX": "Ждём первый запрос..."
}


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📈 Период лонг"),
                KeyboardButton(text="➕ Процент лонг")
            ],
            [
                KeyboardButton(text="📉 Период шорт"),
                KeyboardButton(text="➖ Процент шорт")
            ],
            [
                KeyboardButton(text=f"Bybit: {'✅' if config['bybit'] else '❌'}"),
                KeyboardButton(text=f"BingX: {'✅' if config['bingx'] else '❌'}")
            ],
            [
                KeyboardButton(text=f"Лонг: {'✅' if config['long_on'] else '❌'}"),
                KeyboardButton(text=f"Шорт: {'✅' if config['short_on'] else '❌'}")
            ],
            [
                KeyboardButton(text="📊 Текущие настройки"),
                KeyboardButton(text="📡 Статус бирж")
            ]
        ],
        resize_keyboard=True
    )


def get_status_text() -> str:
    return (
        f"⚙️ **Настройки памп-скринера**\n\n"
        f"🟢 **Лонг:** +{config['long_pct']}% за {config['long_min']}м ({'Вкл' if config['long_on'] else 'Выкл'})\n"
        f"🔴 **Шорт:** -{config['short_pct']}% за {config['short_min']}м ({'Вкл' if config['short_on'] else 'Выкл'})\n"
        f"🏦 **Биржи:** Bybit ({'✅' if config['bybit'] else '❌'}) | BingX ({'✅' if config['bingx'] else '❌'})"
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    config["chat_id"] = message.chat.id
    config["running"] = True
    await message.answer(
        "✅ **Скринер запущен!** Сигналы будут приходить в этот чат.\n\n" + get_status_text(),
        reply_markup=get_settings_keyboard(),
        parse_mode="Markdown"
    )


@dp.message(F.text == "📊 Текущие настройки")
async def show_settings(message: types.Message, state: FSMContext):
    await state.clear()
    config["chat_id"] = message.chat.id
    await message.answer(get_status_text(), reply_markup=get_settings_keyboard(), parse_mode="Markdown")


@dp.message(F.text == "📡 Статус бирж")
async def show_exchange_status(message: types.Message):
    config["chat_id"] = message.chat.id
    bybit_pairs = sum(1 for ex, _ in price_history.keys() if ex == "ByBit")
    bingx_pairs = sum(1 for ex, _ in price_history.keys() if ex == "BingX")

    max_move = 0.0
    top_coin = "пока нет данных"
    for (ex, sym), hist in price_history.items():
        if len(hist) >= 2:
            old_p = next(iter(hist))
            cur_p = hist[-1]
            pct = ((cur_p - old_p) / old_p) * 100
            if abs(pct) > abs(max_move):
                max_move = pct
                top_coin = f"{sym} ({ex})"

    text = (
        f"📡 **Память и статус бирж**\n\n"
        f"🟡 **ByBit:** в памяти `{bybit_pairs}` монет\n"
        f"Статус: `{exchange_stats['ByBit']}`\n\n"
        f"🔵 **BingX:** в памяти `{bingx_pairs}` монет\n"
        f"Статус: `{exchange_stats['BingX']}`\n\n"
        f"🔥 **Топ движение в памяти:** `{top_coin}` → **{max_move:+.2f}%**"
    )
    await message.answer(text, reply_markup=get_settings_keyboard(), parse_mode="Markdown")


@dp.message(F.text.startswith("Bybit:"))
async def toggle_bybit(message: types.Message):
    config["bybit"] = not config["bybit"]
    await message.answer(get_status_text(), reply_markup=get_settings_keyboard(), parse_mode="Markdown")


@dp.message(F.text.startswith("BingX:"))
async def toggle_bingx(message: types.Message):
    config["bingx"] = not config["bingx"]
    await message.answer(get_status_text(), reply_markup=get_settings_keyboard(), parse_mode="Markdown")


@dp.message(F.text.startswith("Лонг:"))
async def toggle_long(message: types.Message):
    config["long_on"] = not config["long_on"]
    await message.answer(get_status_text(), reply_markup=get_settings_keyboard(), parse_mode="Markdown")


@dp.message(F.text.startswith("Шорт:"))
async def toggle_short(message: types.Message):
    config["short_on"] = not config["short_on"]
    await message.answer(get_status_text(), reply_markup=get_settings_keyboard(), parse_mode="Markdown")
@dp.message(F.text == "📈 Период лонг")
async def ask_long_min(message: types.Message, state: FSMContext):
    await state.set_state(SettingsState.waiting_long_min)
    await message.answer(f"Текущий период лонга: **{config['long_min']} мин**.\nВведите новое число минут:", parse_mode="Markdown")


@dp.message(SettingsState.waiting_long_min)
async def set_long_min(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if 1 <= val <= 120:
            config["long_min"] = val
            await state.clear()
            await message.answer(f"✅ Период лонга: **{val} мин**.", reply_markup=get_settings_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        pass
    await message.answer("❌ Введите целое число от 1 до 120.")


@dp.message(F.text == "➕ Процент лонг")
async def ask_long_pct(message: types.Message, state: FSMContext):
    await state.set_state(SettingsState.waiting_long_pct)
    await message.answer(f"Текущий процент лонга: **{config['long_pct']}%**.\nВведите новый процент:", parse_mode="Markdown")


@dp.message(SettingsState.waiting_long_pct)
async def set_long_pct(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", ".").strip())
        if 0.05 <= val <= 100:
            config["long_pct"] = val
            await state.clear()
            await message.answer(f"✅ Процент лонга: **+{val}%**.", reply_markup=get_settings_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        pass
    await message.answer("❌ Введите корректное число (например, 2.5).")


@dp.message(F.text == "📉 Период шорт")
async def ask_short_min(message: types.Message, state: FSMContext):
    await state.set_state(SettingsState.waiting_short_min)
    await message.answer(f"Текущий период шорта: **{config['short_min']} мин**.\nВведите новое число минут:", parse_mode="Markdown")


@dp.message(SettingsState.waiting_short_min)
async def set_short_min(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if 1 <= val <= 120:
            config["short_min"] = val
            await state.clear()
            await message.answer(f"✅ Период шорта: **{val} мин**.", reply_markup=get_settings_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        pass
    await message.answer("❌ Введите целое число от 1 до 120.")


@dp.message(F.text == "➖ Процент шорт")
async def ask_short_pct(message: types.Message, state: FSMContext):
    await state.set_state(SettingsState.waiting_short_pct)
    await message.answer(f"Текущий процент шорта: **{config['short_pct']}%**.\nВведите новый процент:", parse_mode="Markdown")


@dp.message(SettingsState.waiting_short_pct)
async def set_short_pct(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", ".").strip())
        if 0.05 <= val <= 100:
            config["short_pct"] = val
            await state.clear()
            await message.answer(f"✅ Процент шорта: **-{val}%**.", reply_markup=get_settings_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        pass
    await message.answer("❌ Введите корректное число (например, 10).")


async def fetch_bybit_prices(session: aiohttp.ClientSession) -> dict:
    urls = [
        "https://bybit.com",
        "https://bytick.com"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    prices = {}
    for url in urls:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    for item in data.get("result", {}).get("list", []):
                        symbol = item.get("symbol", "")
                        if symbol.endswith("USDT"):
                            prices[symbol] = float(item["lastPrice"])
                    exchange_stats["ByBit"] = f"OK ({len(prices)} монет)"
                    return prices
                else:
                    exchange_stats["ByBit"] = f"HTTP {resp.status}"
        except Exception as e:
            exchange_stats["ByBit"] = f"Ошибка: {str(e)[:30]}"
    return prices



async def fetch_bingx_prices(session: aiohttp.ClientSession) -> dict:
    url = "https://bingx.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    prices = {}
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                exchange_stats["BingX"] = f"HTTP {resp.status}"
                return prices
            data = await resp.json(content_type=None)
            for item in data.get("data", []):
                symbol = item.get("symbol", "").replace("-", "")
                if symbol.endswith("USDT"):
                    prices[symbol] = float(item["lastPrice"])
            exchange_stats["BingX"] = f"OK ({len(prices)} монет)"
    except Exception as e:
        exchange_stats["BingX"] = f"Ошибка: {str(e)[:30]}"
    return prices




async def check_signals(exchange: str, prices: dict, now: float):
    max_window = max(config["long_min"], config["short_min"]) * 60 + 60

    for symbol, current_price in prices.items():
        if current_price <= 0:
            continue

        key = (exchange, symbol)
        if key not in price_history:
            price_history[key] = deque()

        history = price_history[key]
        history.append((now, current_price))

        while history and (now - next(iter(history))) > max_window:
            history.popleft()

        if config["long_on"]:
            target_time = now - (config["long_min"] * 60)
            past_prices = [p for t, p in history if t >= target_time]
            if len(past_prices) >= 2:
                base_price = next(iter(past_prices))
                change_pct = ((current_price - base_price) / base_price) * 100
                if change_pct >= config["long_pct"]:
                    await send_alert(exchange, symbol, "LONG", change_pct, config["long_min"], base_price, current_price, now)

        if config["short_on"]:
            target_time = now - (config["short_min"] * 60)
            past_prices = [p for t, p in history if t >= target_time]
            if len(past_prices) >= 2:
                base_price = next(iter(past_prices))
                change_pct = ((current_price - base_price) / base_price) * 100
                if change_pct <= -config["short_pct"]:
                    await send_alert(exchange, symbol, "SHORT", change_pct, config["short_min"], base_price, current_price, now)


def format_price(price: float) -> str:
    return f"{price:.8f}".rstrip("0").rstrip(".")


async def send_alert(exchange: str, symbol: str, direction: str, pct: float, minutes: int, old_p: float, new_p: float, now: float):
    alert_key = (exchange, symbol, direction)
    if now - last_alerts.get(alert_key, 0) < config["cooldown"]:
        return

    last_alerts[alert_key] = now
    if not config["chat_id"]:
        return

    if symbol not in signals_24h:
        signals_24h[symbol] = deque()
    signals_24h[symbol].append(now)
    while signals_24h[symbol] and (now - next(iter(signals_24h[symbol]))) > 86400:
        signals_24h[symbol].popleft()
    count_24h = len(signals_24h[symbol])

    ex_icon = "🟡" if exchange == "ByBit" else "🔵"
    action_icon = "📈" if direction == "LONG" else "📉"
    action_label = "Pump" if direction == "LONG" else "Dump"

    text = (
        f"{ex_icon} {exchange} – {minutes}м – `{symbol}`\n"
        f"{action_icon} {action_label}: **{abs(pct):.2f}%** ({format_price(old_p)}-{format_price(new_p)})\n"
        f"🧬 Signal 24h: {count_24h}"
    )

    try:
        await bot.send_message(config["chat_id"], text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка отправки: {e}")


async def screener_loop():
    while True:
        if config["running"] and config["chat_id"]:
            now = time.time()
            if config["bybit"] and live_prices["ByBit"]:
                await check_signals("ByBit", dict(live_prices["ByBit"]), now)
            if config["bingx"] and live_prices["BingX"]:
                await check_signals("BingX", dict(live_prices["BingX"]), now)
        await asyncio.sleep(5)


async def handle_ping(request):
    return web.Response(text="Bot is alive!")


async def main():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    asyncio.create_task(bybit_ws_worker())
    asyncio.create_task(bingx_ws_worker())
    asyncio.create_task(screener_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

