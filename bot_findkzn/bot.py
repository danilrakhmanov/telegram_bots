import asyncio
import os
import qrcode
import re
import random
import logging
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import signal
import sys
import traceback

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
# Отключаем лишние логи Telethon
logging.getLogger('telethon').setLevel(logging.WARNING)

# Настраиваем основной логгер
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# ============================================

# ========== НАСТРОЙКИ ==========
API_ID = 32031396
API_HASH = '78266115dee64cff8e1fa7b509202756'
PHONE_NUMBER = '+79274449798'

BOT_TOKEN = '8590879937:AAGkSIRqQSi7VGZWpBg9e4bp20Ii1TfRAnQ'

# СПИСОК КАНАЛОВ-ИСТОЧНИКОВ (можно добавлять сколько угодно)
SOURCE_CHANNELS = [
    '@kazan_itch',
    '@poisk_kzn1166',
    '@findkzn_post',
]

TARGET_CHANNEL = '@findkzn'  # Твой канал (куда постим)

DELAY = 0  # Задержка между постами

# 👇 НАСТРОЙКА ПРОЦЕНТА ПОСТОВ
POST_PROBABILITY = 0.3  # 30% постов будут скопированы

# Канал с 100% копированием постов
FULL_COPY_CHANNEL = '@findkzn_post'

# 👇 НАСТРОЙКИ ПЕРЕПОДКЛЮЧЕНИЯ
RECONNECT_DELAY = 5  # Задержка перед переподключением (сек)
# =================================

# ========== НАСТРОЙКИ ГИПЕРССЫЛОК ==========
# Фраза с гиперссылками для добавления в конец каждого поста (в Markdown формате)
PROMO_TEXT = '\n\n[Найдись Казань](https://t.me/findkzn) / [Предлагай запись](https://t.me/findkzn_bot)'

# Включить/выключить добавление ссылок
ADD_PROMO_ENABLED = True

# Добавлять ссылки только если в тексте нет похожих (чтобы избежать дублирования)
AVOID_DUPLICATES = True
# ==========================================

# 👇 ФУНКЦИЯ ДЛЯ УДАЛЕНИЯ НЕНУЖНЫХ ФРАЗ
def remove_unwanted_text(text):
    """Удаляет ненужные фразы из текста"""
    if not text:
        return text
    
    original_text = text
    
    # Удаляем фразу с эмодзи и ссылками
    text = re.sub(r'🫶Подпишись на ИТК \(https://t\.me/poisk_kzn1166\)\n👉Предлагай поиск \(https://t\.me/poisk_kznbot\)', '', text)
    text = re.sub(r'🫶Подпишись на ИТК\s*\n👉Предлагай поиск', '', text)
    text = re.sub(r'- Подпишись на ИТК\s*\n- Предлагай поиск', '', text)
    
    # Удаляем строки с подписками
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        line_lower = line.lower()
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
    
    # Удаляем другие лишние блоки
    text = re.sub(r'\n?Ищу тебя \| Казань.*?\n.*?Предложить поиск.*?@poisk_kznbot.*?\n.*?Поможем найти.*?\n', '', text, flags=re.DOTALL)
    text = re.sub(r'\n?\*\*ОТКРЫТЬ КАНАЛ\*\*', '', text)
    text = re.sub(r'\n?ОТКРЫТЬ КАНАЛ', '', text)
    
    # Удаляем "Источник: @..." если оно появится
    text = re.sub(r'\n?Источник: @\w+', '', text)
    text = re.sub(r'\n?📱 Источник: @\w+', '', text)
    
    # Чистим лишние пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    if text != original_text:
        print("✂️ Текст очищен от лишней информации")
    
    return text

# 👇 ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ ГИПЕРССЫЛОК
def add_promo_links(text):
    """Добавляет промо-ссылки в конец текста"""
    if not text or not ADD_PROMO_ENABLED:
        return text
    
    # Проверяем на дубликаты (чтобы не добавлять дважды)
    if AVOID_DUPLICATES:
        # Проверяем, есть ли уже ссылка на канал или бот в тексте
        if 'findkzn' in text or 'Найдись Казань' in text:
            print("🔗 Промо-ссылки уже есть в тексте, пропускаем добавление")
            return text
    
    # Добавляем промо-текст в конец
    return text + PROMO_TEXT

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
user_client = TelegramClient('user_session_findkzn', API_ID, API_HASH)
bot_client = TelegramClient('bot_session_findkzn', API_ID, API_HASH)

# Флаг для graceful shutdown
is_running = True

def check_ignore_words(text):
    """Проверяет наличие слов для игнорирования"""
    if not text: return False
    text_lower = text.lower()
    for word in IGNORE_WORDS:
        if word.lower() in text_lower:
            return True
    return False

def should_take_post(source_name=None):
    """Определяет, нужно ли взять пост"""
    # Если это канал с полным копированием - берём всегда
    if source_name == FULL_COPY_CHANNEL:
        return True
    return random.random() < POST_PROBABILITY

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

async def shutdown(signal=None):
    """Корректное завершение работы"""
    global is_running
    print("\n🛑 Получен сигнал завершения. Останавливаю бота...")
    is_running = False
    
    # Отключаем клиентов
    try:
        await asyncio.wait_for(user_client.disconnect(), timeout=5.0)
        await asyncio.wait_for(bot_client.disconnect(), timeout=5.0)
        print("✅ Соединения закрыты")
    except asyncio.TimeoutError:
        print("⚠️ Таймаут при отключении, принудительно завершаю")
    except Exception as e:
        print(f"❌ Ошибка при отключении: {e}")

async def run_bot():
    """Основная функция с автоматическим переподключением"""
    global is_running
    
    while is_running:
        try:
            print("\n🔄 Запуск бота с очисткой текста и промо-ссылками...")
            print(f"📊 Режим: копируем только {POST_PROBABILITY*100}% постов")
            
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
            
            print("✅ Юзер-клиент авторизован")
            
            # Запускаем бота
            try:
                await bot_client.start(bot_token=BOT_TOKEN)
                print("✅ Бот-клиент авторизован")
            except Exception as e:
                print(f"❌ Ошибка запуска бота: {e}")
                return
            
            # Проверяем каналы-источники
            print("\n🔄 Проверяю каналы-источники:")
            valid_channels = []
            for channel in SOURCE_CHANNELS:
                try:
                    entity = await user_client.get_entity(channel)
                    print(f"   ✅ Найден: {channel} (ID: {entity.id})")
                    valid_channels.append(entity)
                except Exception as e:
                    print(f"   ❌ Ошибка с {channel}: {e}")
            
            if not valid_channels:
                print("❌ Нет доступных каналов для отслеживания!")
                return
            
            # Выводим информацию о каналах
            print(f"\n📢 Каналы-источники ({len(SOURCE_CHANNELS)} шт.):")
            for i, channel in enumerate(SOURCE_CHANNELS, 1):
                if channel == FULL_COPY_CHANNEL:
                    print(f"   {i}. {channel} (100% копирование)")
                else:
                    print(f"   {i}. {channel}")
            print(f"📨 Канал-приемник: {TARGET_CHANNEL}")
            print(f"🚫 Игнорируемые слова: {', '.join(IGNORE_WORDS)}")
            print(f"🔗 Добавление промо-ссылок: {'ВКЛ' if ADD_PROMO_ENABLED else 'ВЫКЛ'}")
            print(f"📊 Копируем {POST_PROBABILITY*100}% постов (случайно)")
            print("🟢 Бот работает... (нажми Ctrl+C для остановки)\n")

            # Создаем обработчик для ВСЕХ каналов из списка
            @user_client.on(events.NewMessage(chats=valid_channels))
            async def copy_message(event):
                if not is_running:
                    return
                    
                try:
                    message = event.message
                    message_text = message.text or ""
                    
                    # Получаем информацию об источнике
                    chat = await event.get_chat()
                    source_name = getattr(chat, 'username', str(chat.id))
                    
                    # Решаем, брать пост или нет
                    if not should_take_post(source_name):
                        prob = 100 if source_name == FULL_COPY_CHANNEL else POST_PROBABILITY * 100
                        print(f"⏭️ Пропускаю пост из {source_name} (не попал в {prob}%)")
                        return
                    
                    # Проверяем на игнорируемые слова
                    if check_ignore_words(message_text):
                        print(f"🚫 Игнорирую пост из {source_name} (есть стоп-слово)")
                        return
                    
                    # Удаляем ненужные фразы из текста
                    cleaned_text = remove_unwanted_text(message_text)
                    
                    # Добавляем промо-ссылки в конец текста
                    final_text = add_promo_links(cleaned_text)
                    
                    await asyncio.sleep(DELAY)
                    prob = 100 if source_name == FULL_COPY_CHANNEL else POST_PROBABILITY * 100
                    print(f"📥 Копирую пост из {source_name} (попал в {prob}%)")
                    
                    # Копируем пост с промо-ссылками
                    if message.media:
                        # Проверяем тип медиа
                        from telethon.types import MessageMediaDocument
                        is_video = isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/')
                        
                        if is_video:
                            # Для видео используем прямую пересылку
                            await bot_client.send_file(
                                TARGET_CHANNEL,
                                message,
                                caption=final_text if final_text else None,
                                parse_mode='md',
                                link_preview=False
                            )
                            print(f"✅ Видео скопировано быстро из {source_name}")
                        else:
                            # Для фото скачиваем и загружаем
                            file_path = None
                            try:
                                file_path = await message.download_media()
                                await bot_client.send_file(
                                    TARGET_CHANNEL,
                                    file=file_path,
                                    caption=final_text if final_text else None,
                                    parse_mode='md',
                                    link_preview=False
                                )
                            finally:
                                if file_path and os.path.exists(file_path):
                                    try:
                                        os.remove(file_path)
                                    except Exception as e:
                                        print(f"⚠️ Не удалось удалить файл: {e}")
                            print(f"✅ Фото скопировано из {source_name}")
                    else:
                        if final_text:
                            await bot_client.send_message(
                                TARGET_CHANNEL, 
                                final_text,
                                parse_mode='md',
                                link_preview=False
                            )
                            print(f"✅ Текстовый пост скопирован из {source_name}")
                            
                except FloodWaitError as e:
                    print(f"⚠️ Флуд-контроль: ждем {e.seconds}с")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    if is_running:
                        print(f"❌ Ошибка копирования: {e}")
            
            # Ждем отключения или ошибки
            await user_client.run_until_disconnected()
            
        except (ConnectionError, OSError, errors.RPCError, asyncio.TimeoutError) as e:
            print(f"❌ Ошибка соединения: {e}")
            print(f"🔄 Переподключение через {RECONNECT_DELAY} секунд...")
            await asyncio.sleep(RECONNECT_DELAY)
            continue
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            print(f"🔄 Переподключение через {RECONNECT_DELAY} секунд...")
            await asyncio.sleep(RECONNECT_DELAY)
            continue

async def main():
    global is_running
    try:
        # Настраиваем обработку сигналов
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
                except NotImplementedError:
                    pass
        except Exception:
            pass
        
        await run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    finally:
        is_running = False
        await user_client.disconnect()
        await bot_client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        traceback.print_exc()
        input("Нажми Enter для выхода...")