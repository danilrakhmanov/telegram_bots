import asyncio
import os
import qrcode
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import time

# ========== НАСТРОЙКИ ==========
API_ID = 32031396
API_HASH = '78266115dee64cff8e1fa7b509202756'
PHONE_NUMBER = '+79274449798'

# Токен бота - брать из переменной окружения BOT_TOKEN
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8590879937:AAGkSIRqQSi7VGZWpBg9e4bp20Ii1TfRAnQ')

# СПИСОК КАНАЛОВ-ИСТОЧНИКОВ
SOURCE_CHANNELS = [
    '@stereoNWS',
]

TARGET_CHANNEL = '@oasis_mus'  # Твой канал (куда постим)

# Слова для игнорирования
IGNORE_WORDS = [
    'реклама', 'реклам', 'промокод', 'скидка',
    'акция', 'спонсор', 'купон', 'партнерский', '#реклама'
]

# 👇 НАСТРОЙКА ПУБЛИКАЦИИ ПОСТОВ БЕЗ ТЕКСТА
ALLOW_NO_TEXT_POSTS = False  # False = не публиковать посты без текста, True = публиковать

# Время ожидания для сбора альбома (сек)
ALBUM_WAIT_TIME = 1.5
# ================================

user_client = TelegramClient('user_session_oasismus', API_ID, API_HASH)
media_groups = {}

# Флаг для работы
is_running = True
reconnect_delay = 5  # Задержка перед переподключением (сек)

def check_ignore_words(text):
    if not text: return False
    text_lower = text.lower()
    for word in IGNORE_WORDS:
        if word.lower() in text_lower:
            return True
    return False

def print_qr(url):
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

async def process_album(grouped_id, source_name):
    """Обрабатывает альбом после сбора всех сообщений"""
    if grouped_id not in media_groups:
        return
    
    album_data = media_groups[grouped_id]
    messages = album_data['messages']
    
    # Сортируем сообщения по ID
    messages.sort(key=lambda m: m.id)
    
    # Находим сообщение с текстом (обычно первое)
    text_message = None
    for msg in messages:
        if msg.text:
            text_message = msg
            break
    
    # 👇 ПРОВЕРКА НА НАЛИЧИЕ ТЕКСТА
    if not ALLOW_NO_TEXT_POSTS and not text_message:
        print(f"⏭️ Пропускаю альбом из {source_name} (нет текста)")
        del media_groups[grouped_id]
        return
    
    # Проверяем текст на стоп-слова
    if text_message and text_message.text and check_ignore_words(text_message.text):
        print(f"🚫 Игнорирую альбом из {source_name} (есть стоп-слово)")
        del media_groups[grouped_id]
        return
    
    print(f"📦 Копирую альбом из {len(messages)} элементов из {source_name}")
    
    # Скачиваем все медиафайлы с определением типа
    files = []
    from telethon.types import MessageMediaDocument
    
    for msg in messages:
        if msg.media:
            # Определяем тип медиа
            is_video = isinstance(msg.media, MessageMediaDocument) and msg.media.document.mime_type.startswith('video/')
            
            if is_video:
                # Для видео используем прямую пересылку (быстро)
                files.append(msg)
            else:
                # Для фото скачиваем
                file_path = await msg.download_media()
                files.append(file_path)
    
    # Отправляем как альбом
    if files:
        if text_message and text_message.text:
            # Если есть текст, отправляем с ним
            await user_client.send_file(
                TARGET_CHANNEL,
                files,
                caption=text_message.text,
                parse_mode='md'
            )
        else:
            # Если текста нет, но разрешено, отправляем без caption
            if ALLOW_NO_TEXT_POSTS:
                await user_client.send_file(TARGET_CHANNEL, files)
            else:
                print(f"⏭️ Альбом без текста пропущен (настройки)")
        
        print(f"✅ Альбом из {len(files)} элементов скопирован")
    
    # Удаляем временные файлы (только фото)
    for file_path in files:
        if isinstance(file_path, str) and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Не удалось удалить файл {file_path}: {e}")
    
    del media_groups[grouped_id]

async def run_bot():
    """Основная функция с автоматическим переподключением"""
    global is_running
    
    while is_running:
        try:
            print("\n🔄 Запуск бота для красивого копирования постов...")
            print(f"📝 Посты без текста: {'❌ ЗАПРЕЩЕНЫ' if not ALLOW_NO_TEXT_POSTS else '✅ РАЗРЕШЕНЫ'}")
            
            await user_client.connect()
            
            if not await user_client.is_user_authorized():
                print("\n📱 Выбери способ входа:")
                print("1 - QR-код")
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
            
            print(f"\n📢 Отслеживаю каналы: {', '.join(SOURCE_CHANNELS)}")
            print(f"📨 Канал-приемник: {TARGET_CHANNEL}")
            print(f"🚫 Игнорируемые слова: {', '.join(IGNORE_WORDS)}")
            print(f"📝 Посты без текста: {'❌ ЗАПРЕЩЕНЫ' if not ALLOW_NO_TEXT_POSTS else '✅ РАЗРЕШЕНЫ'}")
            print("🟢 Бот работает... (нажми Ctrl+C для остановки)\n")

            @user_client.on(events.NewMessage(chats=valid_channels))
            async def handle_message(event):
                try:
                    message = event.message
                    chat = await event.get_chat()
                    source_name = getattr(chat, 'username', str(chat.id))
                    
                    # Если это часть альбома
                    if message.grouped_id:
                        grouped_id = message.grouped_id
                        
                        # Создаем или обновляем запись об альбоме
                        if grouped_id not in media_groups:
                            media_groups[grouped_id] = {
                                'messages': [message],
                                'source': source_name
                            }
                            
                            # Запускаем таймер для обработки альбома
                            asyncio.create_task(delayed_process(grouped_id, source_name))
                        else:
                            media_groups[grouped_id]['messages'].append(message)
                        
                        return
                    
                    # Одиночное сообщение (не альбом)
                    
                    # 👇 ПРОВЕРКА НА НАЛИЧИЕ ТЕКСТА
                    if not ALLOW_NO_TEXT_POSTS and not message.text:
                        print(f"⏭️ Пропускаю пост из {source_name} (нет текста)")
                        return
                    
                    # Проверяем текст на стоп-слова
                    if check_ignore_words(message.text or ""):
                        print(f"🚫 Игнорирую пост из {source_name} (есть стоп-слово)")
                        return
                    
                    print(f"📥 Копирую пост из {source_name}")
                    
                    # Если есть медиа
                    if message.media:
                        # Определяем тип медиа
                        from telethon.types import MessageMediaDocument
                        is_video = isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/')
                        
                        if is_video:
                            # Для видео используем прямую пересылку (быстро)
                            await user_client.send_file(
                                TARGET_CHANNEL,
                                message,  # Передаем само сообщение
                                caption=message.text or "",
                                parse_mode='md'
                            )
                            print(f"✅ Видео скопировано быстро")
                        else:
                            # Для фото скачиваем и загружаем
                            file_path = None
                            try:
                                file_path = await message.download_media()
                                await user_client.send_file(
                                    TARGET_CHANNEL,
                                    file_path,
                                    caption=message.text or "",
                                    parse_mode='md'
                                )
                            finally:
                                if file_path and os.path.exists(file_path):
                                    try:
                                        os.remove(file_path)
                                    except Exception as e:
                                        print(f"⚠️ Не удалось удалить файл: {e}")
                            print(f"✅ Фото скопировано")
                    
                    # Если только текст
                    elif message.text:
                        # Отправляем текст с Markdown форматированием
                        await user_client.send_message(
                            TARGET_CHANNEL,
                            message.text,
                            parse_mode='md'
                        )
                        print(f"✅ Текстовый пост скопирован")
                            
                except FloodWaitError as e:
                    print(f"⚠️ Флуд-контроль: ждем {e.seconds}с")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

            async def delayed_process(grouped_id, source_name):
                """Задержка перед обработкой альбома"""
                await asyncio.sleep(ALBUM_WAIT_TIME)
                await process_album(grouped_id, source_name)
            
            # Ждем отключения или ошибки
            await user_client.run_until_disconnected()
            
        except (ConnectionError, OSError, errors.RPCError) as e:
            print(f"❌ Ошибка соединения: {e}")
            print(f"🔄 Переподключение через {reconnect_delay} секунд...")
            await asyncio.sleep(reconnect_delay)
            continue
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            print(f"🔄 Переподключение через {reconnect_delay} секунд...")
            await asyncio.sleep(reconnect_delay)
            continue

async def main():
    global is_running
    try:
        await run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    finally:
        is_running = False
        await user_client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        input("Нажми Enter для выхода...")