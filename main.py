import hashlib
import ecdsa
import requests
import base58
import numpy as np
import time
import logging
import math
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext

# Токен вашего бота
TOKEN = "TOKEN BOT"
# Имя канала для публикации (например, @TON_OPEN_TON)
CHANNEL_ID = "@TON_OPEN_TON"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функция для создания симметричного узора 16x16
def create_symmetric_pattern(number, size=16):
    np.random.seed(number)

    # Создаем пустой узор 16x16
    pattern = np.zeros((size, size), dtype=int)

    # Центр узора
    center = size // 2

    # Генерация симметричного узора
    for i in range(size):
        for j in range(size):
            # Расстояние от центра
            distance = math.sqrt((i - center) ** 2 + (j - center) ** 2)

            # Используем синус и косинус для создания симметричного узора
            value = math.sin(distance + number) + math.cos(distance + number)

            # Преобразуем значение в 0 или 1
            pattern[i, j] = 1 if value > 0 else 0

    # Делаем узор симметричным относительно центра
    pattern = np.maximum(pattern, np.flip(pattern, axis=0))  # Отражение по вертикали
    pattern = np.maximum(pattern, np.flip(pattern, axis=1))  # Отражение по горизонтали

    # Преобразуем узор в строку с эмодзи
    visual_key = ""
    for row in pattern:
        visual_key += "".join(["🟩" if bit == 1 else "⬜️" for bit in row]) + "\n"

    # Преобразуем узор в 256-битный ключ
    key_data = pattern.tobytes()  # Преобразуем массив в байты
    return visual_key, key_data

# Функция для генерации приватного ключа и адреса Bitcoin
def generate_bitcoin_address(data):
    hash_object = hashlib.sha256(data)
    private_key = hash_object.digest()
    sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    public_key = b"\x04" + vk.to_string()
    sha256_bpk = hashlib.sha256(public_key).digest()
    ripemd160_bpk = hashlib.new("ripemd160", sha256_bpk).digest()
    network_byte = b"\x00"
    hashed_public_key = network_byte + ripemd160_bpk
    checksum = hashlib.sha256(hashlib.sha256(hashed_public_key).digest()).digest()[:4]
    address_bytes = hashed_public_key + checksum
    address = base58.b58encode(address_bytes).decode("utf-8")
    return private_key.hex(), address

# Функция для проверки баланса и транзакций Bitcoin через API
def check_balance_and_transactions(address):
    apis = [
        {
            "url": f"https://blockchain.info/rawaddr/{address}",
            "balance_key": "final_balance",
            "tx_key": "n_tx"
        },
        {
            "url": f"https://api.blockcypher.com/v1/btc/main/addrs/{address}",
            "balance_key": "balance",
            "tx_key": "n_tx"
        },
        {
            "url": f"https://api.bitaps.com/btc/v1/blockchain/address/state/{address}",
            "balance_key": "data.balance",
            "tx_key": "data.received_tx_count"
        },
        {
            "url": f"https://chain.api.btc.com/v3/address/{address}",
            "balance_key": "data.balance",
            "tx_key": "data.tx_count"
        },
        {
            "url": f"https://sochain.com/api/v2/get_address_balance/BTC/{address}",
            "balance_key": "data.confirmed_balance",
            "tx_key": "data.txs"
        }
    ]

    for api in apis:
        try:
            response = requests.get(api["url"], timeout=10)  # Тайм-аут 10 секунд
            if response.status_code == 200:
                data = response.json()

                # Получаем баланс
                balance = data
                for key in api["balance_key"].split("."):
                    balance = balance.get(key, 0)
                    if balance is None:
                        balance = 0
                        break

                # Получаем количество транзакций
                transactions = data
                for key in api["tx_key"].split("."):
                    transactions = transactions.get(key, 0)
                    if transactions is None:
                        transactions = 0
                        break

                return balance, transactions
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при запросе к API {api['url']}: {e}")
            continue

    return 0, 0

# Функция для проверки баланса Bitcoin Cash через API
def check_bitcoin_cash_balance(address):
    apis = [
        {
            "url": f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{address}",
            "balance_key": "data.{address}.address.balance"
        },
        {
            "url": f"https://api.bitcore.io/api/BCH/mainnet/address/{address}/balance",
            "balance_key": "balance"
        },
        {
            "url": f"https://rest.bitcoin.com/v2/address/details/{address}",
            "balance_key": "balanceSat"
        },
        {
            "url": f"https://api.blockcypher.com/v1/bch/main/addrs/{address}",
            "balance_key": "balance"
        },
        {
            "url": f"https://sochain.com/api/v2/get_address_balance/BCH/{address}",
            "balance_key": "data.confirmed_balance"
        }
    ]

    for api in apis:
        try:
            response = requests.get(api["url"], timeout=10)  # Тайм-аут 10 секунд
            if response.status_code == 200:
                data = response.json()

                # Получаем баланс
                balance = data
                for key in api["balance_key"].split("."):
                    balance = balance.get(key, 0)
                    if balance is None:
                        balance = 0
                        break

                return balance
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при запросе к API {api['url']}: {e}")
            continue

    return 0

# Функция для публикации в канал
async def post_to_channel(context: ContextTypes.DEFAULT_TYPE, message: str):
    await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")

# Команда /pattern
async def pattern_generate(update: Update, context: CallbackContext):
    try:
        number = int(context.args[0]) if context.args else 1  # По умолчанию число 1

        while True:
            # Генерация узора
            visual_key, key_data = create_symmetric_pattern(number)
            private_key, address = generate_bitcoin_address(key_data)
            balance, transactions = check_balance_and_transactions(address)
            bch_balance = check_bitcoin_cash_balance(address)

            # Форматируем сообщение с использованием ```
            message = (
                f"```\n"
                f"Число: {number}\n"
                f"Узор:\n{visual_key}\n"
                f"Приватный ключ: {private_key}\n"
                f"Адрес Bitcoin: {address}\n"
                f"Баланс Bitcoin: {balance} сатоши\n"
                f"Количество транзакций Bitcoin: {transactions}\n"
                f"Баланс Bitcoin Cash: {bch_balance} сатоши\n"
                f"```\n"
                f"[Обозреватель Bitcoin](https://www.blockchain.com/explorer/addresses/btc/{address})"
            )

            if balance == 0 and transactions == 0 and bch_balance == 0:
                # Постим в канал, если баланс нулевой
                await post_to_channel(context, message)
            else:
                # Отправляем в личные сообщения, если баланс ненулевой
                await update.message.reply_text(message, parse_mode="Markdown")

            # Увеличиваем число на 1
            number += 1
            time.sleep(5)  # Пауза между постами

    except (IndexError, ValueError) as e:
        await update.message.reply_text(f"Ошибка: {e}. Использование: /pattern <число>")
    except Exception as e:
        logger.error(f"Ошибка в команде /pattern: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для генерации Bitcoin-адресов на основе симметричных узоров.\n"
        "Доступные команды:\n"
        "/pattern <число> - Генерация на основе симметричных узоров\n"
        "/stop - Остановить генерацию\n"
        "/help - Показать список команд"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/pattern <число> - Генерация на основе симметричных узоров\n"
        "/stop - Остановить генерацию\n"
        "/help - Показать список команд"
    )

# Команда /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Генерация остановлена.")
    context.application.stop()

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pattern", pattern_generate))
    application.add_handler(CommandHandler("stop", stop))

    # Регистрация обработчика ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    application.run_polling()

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

if __name__ == "__main__":
    main()
