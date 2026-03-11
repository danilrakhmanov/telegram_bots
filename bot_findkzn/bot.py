import asyncio
import os
import qrcode
import re
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import time

# ========== НАСТРОЙКИ ==========
API_ID = 32031396
API_HASH = '78266115dee64cff8e1fa7b509202756'
PHONE_NUMBER = '+79274449798'

BOT_TOKEN = '8590879937:AAGkSIRqQSi7VGZWpBg9e4bp20Ii1TfRAnQ'

# СПИСОК КАНАЛОВ-ИСТОЧНИКОВ (можно добавлять сколько угодно)
SOURCE_CHANNELS = [
    '@kazan_itch',
    '@poisk_kzn1166',
]

TARGET_CHANNEL = '@findkzn'  # Твой канал (куда постим)

DELAY = 0  # Задержка между постами

# 👇 ИСПРАВЛЕННАЯ ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ НЕНУЖНОЙ ФРАЗЫ
def remove_unwanted_text(text):
    """Удаляет ненужные фразы из текста"""
    if not text:
        return text
    
    original_text = text
    
    # Вариант 1: Удаляем фразу с эмодзи и ссылками (полная версия)
    text = re.sub(r'🫶Подпишись на ИТК \(https://t\.me/poisk_kzn1166\)\n👉Предлагай поиск \(https://t\.me/poisk_kznbot\)', '', text)
    
    # Вариант 2: Удаляем фразу с эмодзи без ссылок
    text = re.sub(r'🫶Подпишись на ИТК\s*\n👉Предлагай поиск', '', text)
    
    # Вариант 3: Удаляем фразу с дефисами (как в твоем примере)
    text = re.sub(r'- Подпишись на ИТК\s*\n- Предлагай поиск', '', text)
    
    # Вариант 4: Удаляем любые строки, содержащие эти фразы
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        line_lower = line.lower()
        # Пропускаем строки с нежелательным содержанием
        if any(phrase in line_lower for phrase in [
            'подпишись на итк',
            'предлагай поиск',
            '- подпишись',
            '- предлагай',
            '🫶подпишись',
            '👉предлагай',
        ]):
            continue
        filtered_lines.append(line)
    
    text = '\n'.join(filtered_lines)
    
    # Удаляем "Источник: @..." если оно появится
    text = re.sub(r'\n?Источник: @\w+', '', text)
    text = re.sub(r'\n?📱 Источник: @\w+', '', text)
    
    # Удаляем блок "Ищу тебя | Казань" (из твоего скриншота)
    text = re.sub(r'\n?Ищу тебя \| Казань.*?\n.*?Предложить поиск.*?@poisk_kznbot.*?\n.*?Поможем найти.*?\n', '', text, flags=re.DOTALL)
    
    # Удаляем "ОТКРЫТЬ КАНАЛ"
    text = re.sub(r'\n?\*\*ОТКРЫТЬ КАНАЛ\*\*', '', text)
    text = re.sub(r'\n?ОТКРЫТЬ КАНАЛ', '', text)
    
    # Чистим лишние пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    # Если текст изменился, сообщаем об этом
    if text != original_text:
        print("✂️ Текст очищен от лишней информации")
    
    return text
# 👆 КОНЕЦ ИСПРАВЛЕННОЙ ФУНКЦИИ

# Слова для игнорирования (посты с этими словами НЕ копируются)
IGNORE_WORDS = [
    'реклама',
    'реклам',
    'промокод',
    'скидка',
    'акция',
    'спонсор',
    'купон',
    'партнерский',
    '#реклама',
]
# ================================

# В Docker сессии лучше хранить в отдельной папке
user_client = TelegramClient('sessions/user_session', API_ID, API_HASH)
bot_client = TelegramClient('sessions/bot_session', API_ID, API_HASH)

def check_ignore_words(text):
    """Проверяет наличие слов для игнорирования"""
    if not text: return False
    text_lower = text.lower()
    for word in IGNORE_WORDS:
        if word.lower() in text_lower:
            return True
    return False

def print_qr(url):
    """Создает и выводит QR-код в консоль"""
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    
    matrix = qr.get_matrix()
    print("\n" + "=" * 50)
    for row in matrix:
        line = ""
        for cell in row:
            line += "██" if cell else "  "
        print(line)
    print("=" * 50)

async def qr_login_method():
    """Вход через QR-код"""
    print("\n📱 Вход по QR-коду:")
    print("1. Открой Telegram на телефоне")
    print("2. Настройки → Устройства")
    print("3. Нажми 'Сканировать QR-код'")
    print("4. Наведи камеру на QR-код ниже\n")
    
    qr_login = await user_client.qr_login()
    print_qr(qr_login.url)
    print(f"\n🔗 Ссылка: {qr_login.url}")
    print("\n⏳ Ожидание сканирования... (30 секунд)")
    
    try:
        await qr_login.wait(30)
        print("✅ QR-код отсканирован!")
        return True
    except SessionPasswordNeededError:
        print("\n🔐 Требуется пароль двухфакторки")
        password = input("Введи пароль от Telegram: ")
        await user_client.sign_in(password=password)
        print("✅ Пароль принят!")
        return True
    except asyncio.TimeoutError:
        print("\n⏰ Время вышло")
        return False
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        return False

async def code_login_method():
    """Вход по коду из Telegram"""
    print("\n📱 Вход по коду:")
    try:
        await user_client.send_code_request(PHONE_NUMBER)
        print("✅ Код отправлен! Проверь Telegram/SMS")
        
        code = input("👉 Введи код: ").strip()
        
        try:
            await user_client.sign_in(PHONE_NUMBER, code)
            print("✅ Вход выполнен!")
            return True
        except SessionPasswordNeededError:
            password = input("🔑 Введи пароль: ")
            await user_client.sign_in(password=password)
            print("✅ Вход выполнен!")
            return True
    except FloodWaitError as e:
        wait = e.seconds
        hours = wait // 3600
        minutes = (wait % 3600) // 60
        print(f"\n⚠️ Нужно подождать {hours}ч {minutes}м")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

async def main():
    print("🔄 Запуск бота с очисткой текста...")
    
    await user_client.connect()
    
    if not await user_client.is_user_authorized():
        print("\n📱 Выбери способ входа:")
        print("1 - QR-код (рекомендуется)")
        print("2 - Код из Telegram/SMS")
        
        choice = input("\nТвой выбор (1/2): ").strip()
        
        success = False
        if choice == "1":
            for attempt in range(3):
                print(f"\n🔄 Попытка {attempt + 1}/3")
                success = await qr_login_method()
                if success:
                    break
                if attempt < 2:
                    print("Пробую снова...")
                    await asyncio.sleep(2)
        else:
            success = await code_login_method()
        
        if not success:
            print("\n❌ Не удалось войти")
            return
        
        print("✅ Авторизация успешна!")
    
    print("✅ Юзер-клиент авторизован")
    
    # Запускаем бота
    try:
        await bot_client.start(bot_token=BOT_TOKEN)
        print("✅ Бот-клиент авторизован")
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")
        return
    
    # Выводим информацию о каналах
    print(f"\n📢 Каналы-источники ({len(SOURCE_CHANNELS)} шт.):")
    for i, channel in enumerate(SOURCE_CHANNELS, 1):
        print(f"   {i}. {channel}")
    print(f"📨 Канал-приемник: {TARGET_CHANNEL}")
    print(f"🚫 Игнорируемые слова: {', '.join(IGNORE_WORDS)}")
    print("🟢 Бот работает...\n")

    # Создаем обработчик для ВСЕХ каналов из списка
    @user_client.on(events.NewMessage(chats=SOURCE_CHANNELS))
    async def copy_message(event):
        try:
            message = event.message
            message_text = message.text or ""
            
            # Получаем информацию об источнике (только для лога)
            chat = await event.get_chat()
            source_name = getattr(chat, 'username', str(chat.id))
            
            # Проверяем на игнорируемые слова
            if check_ignore_words(message_text):
                print(f"🚫 Игнорирую пост из {source_name} (есть стоп-слово)")
                return
            
            # Удаляем ненужную фразу из текста
            cleaned_text = remove_unwanted_text(message_text)
            
            await asyncio.sleep(DELAY)
            print(f"📥 Новый пост из канала @{source_name}")
            
            # Копируем пост БЕЗ добавления "Источник:"
            if message.media:
                file_path = await message.download_media()
                
                # Отправляем только очищенный текст, без источника
                await bot_client.send_file(
                    TARGET_CHANNEL,
                    file=file_path,
                    caption=cleaned_text if cleaned_text else None
                )
                
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    
                print(f"✅ Пост с медиа скопирован из {source_name}")
            else:
                if cleaned_text:
                    # Отправляем только очищенный текст, без источника
                    await bot_client.send_message(TARGET_CHANNEL, cleaned_text)
                    print(f"✅ Текстовый пост скопирован из {source_name}")
                    
        except FloodWaitError as e:
            print(f"⚠️ Флуд-контроль: ждем {e.seconds}с")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"❌ Ошибка копирования: {e}")
    
    try:
        await user_client.run_until_disconnected()
    except Exception as e:
        print(f"❌ Соединение потеряно: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        input("Нажми Enter для выхода...")