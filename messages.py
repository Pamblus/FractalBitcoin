import hashlib
import ecdsa
import base58
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import time
import requests

# Токен вашего бота
TOKEN = "TOKEN BOT"
# ID беседы, откуда бот берет сообщения (например, @pambluschat)
SOURCE_CHAT_ID = "@pambluschat"
# ID канала, куда бот публикует результаты (например, @TON_OPEN_TON)
TARGET_CHANNEL_ID = "@TON_OPEN_TON"
# Ваш личный username для отправки сообщений
YOUR_USERNAME = "@pamblus"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Русский алфавит
russian_alphabet = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
# Английский алфавит
english_alphabet = "abcdefghijklmnopqrstuvwxyz"

# Функция для получения номера буквы в русском алфавите
def get_russian_alphabet_number(letter):
    return russian_alphabet.index(letter) + 1

# Функция для получения номера буквы в английском алфавите
def get_english_alphabet_number(letter):
    return english_alphabet.index(letter) + 1

# Функция для преобразования слова в число (конкатенация номеров букв)
def word_to_number(word):
    number_str = ""
    for letter in word.lower():
        if letter in russian_alphabet:
            number_str += f"{get_russian_alphabet_number(letter):02d}"  # Двузначные числа
        elif letter in english_alphabet:
            number_str += f"{get_english_alphabet_number(letter):02d}"  # Двузначные числа
    return int(number_str) if number_str else 0

# Функция для сокращения числа (первые 3 и последние 3 цифры)
def shorten_number(number):
    num_str = str(number)
    if len(num_str) > 10:
        return f"{num_str[:3]}...{num_str[-3:]}"
    return num_str

# Функция для генерации приватного ключа на основе числа
def generate_private_key(number):
    # Преобразуем число в 256-битное число
    private_key_int = number % (2**256)  # Ограничиваем диапазон
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

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Проверяем, что сообщение пришло из указанной беседы
        if update.message.chat.username != SOURCE_CHAT_ID.strip("@"):
            return

        # Получаем текст сообщения
        text = update.message.text
        if not text:
            return

        # Преобразуем текст в число (конкатенация номеров букв)
        number = word_to_number(text)

        # Сокращаем число для отображения в посте
        shortened_number = shorten_number(number)

        # Генерация приватного ключа на основе числа
        private_key = generate_private_key(number)

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
            f"Сообщение\n"  # Указываем, что пост создан на основе сообщения
            f"Число: {shortened_number}\n"
            f"Эмодзи-графика:\n```\n{emoji_grid}\n```\n"
            f"Приватный ключ: `{private_key_hex}`\n"
            f"Адрес Bitcoin: `{address}`\n"
            f"Баланс Bitcoin: {btc_balance} сатоши\n"
            f"Транзакции Bitcoin: {btc_transactions}\n"
            f"Баланс Bitcoin Cash: {bch_balance} сатоши\n"
        )

        # Логика публикации
        if btc_balance > 0 or bch_balance > 0:
            # Если баланс больше 0, отправляем в личные сообщения
            await context.bot.send_message(chat_id=YOUR_USERNAME, text=message, parse_mode="Markdown")
        else:
            # Если баланс равен 0, публикуем в канал
            await context.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=message, parse_mode="Markdown")

        # Пауза 5 секунд между постами
        time.sleep(5)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()
