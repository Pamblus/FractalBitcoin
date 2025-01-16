import hashlib
import ecdsa
import base58
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext
import time
import requests

# Токен вашего бота
TOKEN = "TOKEN BOT"
# Имя канала для публикации (например, @TON_OPEN_TON)
CHANNEL_ID = "@TON_OPEN_TON"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функция для генерации приватного ключа на основе числа Фибоначчи
def generate_private_key(fib_number):
    # Преобразуем число Фибоначчи в 256-битное число
    private_key_int = fib_number % (2**256)  # Ограничиваем диапазон
    # Преобразуем число в байты (32 байта)
    private_key = private_key_int.to_bytes(32, byteorder="big")
    return private_key

# Функция для создания эмодзи-графики 16x16
def create_emoji_grid(private_key):
    # Преобразуем приватный ключ в бинарную строку
    binary_string = "".join(f"{byte:08b}" for byte in private_key)
    # Создаем сетку 16x16
    grid = ""
    for i in range(16):
        for j in range(16):
            index = i * 16 + j
            if index < len(binary_string):
                # Используем эмодзи в зависимости от значения бита
                grid += "🟩" if binary_string[index] == "1" else "⬜️"
            else:
                grid += "⬜️"  # Заполняем пустые клетки
        grid += "\n"
    return grid

# Функция для генерации Bitcoin-адреса
def generate_bitcoin_address(private_key):
    # Генерация публичного ключа
    sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
    vk = sk.verifying_key
    public_key = b"\x04" + vk.to_string()  # Несжатый публичный ключ

    # Хэшируем публичный ключ
    sha256_bpk = hashlib.sha256(public_key).digest()
    ripemd160_bpk = hashlib.new("ripemd160", sha256_bpk).digest()

    # Добавляем сетевой байт (0x00 для Bitcoin)
    network_byte = b"\x00"
    hashed_public_key = network_byte + ripemd160_bpk

    # Вычисляем контрольную сумму
    checksum = hashlib.sha256(hashlib.sha256(hashed_public_key).digest()).digest()[:4]

    # Формируем финальный адрес
    address_bytes = hashed_public_key + checksum
    address = base58.b58encode(address_bytes).decode("utf-8")

    return private_key.hex(), address

# Функция для проверки баланса Bitcoin через API
def check_balance(address):
    try:
        response = requests.get(f"https://blockchain.info/rawaddr/{address}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            balance = data.get("final_balance", 0)  # Баланс в сатоши
            transactions = data.get("n_tx", 0)  # Количество транзакций
            return balance, transactions
    except Exception as e:
        logger.error(f"Ошибка при проверке баланса: {e}")
    return 0, 0

# Функция для проверки баланса Bitcoin Cash через API
def check_bitcoin_cash_balance(address):
    try:
        response = requests.get(f"https://blockchair.com/bitcoin-cash/dashboards/address/{address}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            balance = data.get("data", {}).get(address, {}).get("address", {}).get("balance", 0)
            return balance
    except Exception as e:
        logger.error(f"Ошибка при проверке баланса Bitcoin Cash: {e}")
    return 0

# Команда /start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я бот для генерации 256-битных ключей на основе чисел Фибоначчи.\n"
        "Используйте команду /fibonacci <число>, чтобы начать."
    )

# Команда /fibonacci
async def fibonacci_command(update: Update, context: CallbackContext):
    try:
        # Получаем начальное число из аргументов команды
        if not context.args:
            await update.message.reply_text("Использование: /fibonacci <начальное число>")
            return

        start_number = int(context.args[0])  # Начальное число Фибоначчи
        a, b = 0, start_number

        while True:
            # Генерация приватного ключа на основе числа Фибоначчи
            private_key = generate_private_key(b)

            # Создаем эмодзи-графику
            emoji_grid = create_emoji_grid(private_key)

            # Генерация Bitcoin-адреса
            private_key_hex, address = generate_bitcoin_address(private_key)

            # Проверяем баланс Bitcoin
            btc_balance, btc_transactions = check_balance(address)

            # Проверяем баланс Bitcoin Cash
            bch_balance = check_bitcoin_cash_balance(address)

            # Форматируем сообщение
            message = (
                f"```\n"
                f"Число Фибоначчи: {b}\n"
                f"Эквалайзер:\n{emoji_grid}\n"
                f"Приватный ключ: {private_key_hex}\n"
                f"Адрес Bitcoin: {address}\n"
                f"Баланс Bitcoin: {btc_balance} сатоши\n"
                f"Транзакции Bitcoin: {btc_transactions}\n"
                f"Баланс Bitcoin Cash: {bch_balance} сатоши\n"
                f"```\n"
                f"[Обозреватель Bitcoin](https://www.blockchain.com/explorer/addresses/btc/{address})"
            )

            # Логика публикации
            if btc_balance > 0 or bch_balance > 0:
                # Если баланс ненулевой, отправляем в личные сообщения
                await update.message.reply_text(message, parse_mode="Markdown")
            else:
                # Если баланс нулевой, публикуем в канал
                await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")

            # Увеличиваем число Фибоначчи
            a, b = b, a + b

            # Пауза между постами
            time.sleep(5)

    except Exception as e:
        logger.error(f"Ошибка в команде /fibonacci: {e}", exc_info=True)
        await update.message.reply_text(f"Произошла ошибка: {e}")

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()

    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("fibonacci", fibonacci_command))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
