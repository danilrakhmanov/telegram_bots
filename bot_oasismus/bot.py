import asyncio
import os
import qrcode
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import time
import requests
import json
import uuid
import re
import random
from typing import Optional, Tuple, Dict, List
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Отключаем предупреждения о SSL (для GigaChat)
warnings.simplefilter('ignore', InsecureRequestWarning)

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
    'акция', 'спонсор', 'купон', 'партнерский', '#реклама', 'ГРЯДУЩИЕ НОВИНКИ'
]

# ========== НАСТРОЙКА GIGACHAT ==========
USE_GIGACHAT = True

# Данные для авторизации
GIGACHAT_AUTH_DATA = 'MDE5Y2UyYmQtM2RkNC03NjczLTkxYzEtMTE5N2Q1NTJkMzRjOmFhZjRiNjI3LWZhOWQtNDU3Mi1hMzU4LTllZDVhOTZlM2VlNA=='
GIGACHAT_SCOPE = 'GIGACHAT_API_PERS'

# 👇 ВЫБОР МОДЕЛИ GIGACHAT
GIGACHAT_MODEL = "GigaChat"  # Используем базовую модель (Lite) - 900k токенов

# 👇 ОПТИМИЗАЦИЯ РАСХОДА ТОКЕНОВ
MIN_TEXT_LENGTH_FOR_REWRITE = 50  # символов
REWRITE_PROBABILITY = 0.7  # 70% постов будем рерайтить
MAX_TEXT_LENGTH = 1000  # символов

# =========================================

# 👇 НАСТРОЙКА ПУБЛИКАЦИИ ПОСТОВ БЕЗ ТЕКСТА
ALLOW_NO_TEXT_POSTS = False

# Время ожидания для сбора альбома (сек)
ALBUM_WAIT_TIME = 1.5
# ================================

class TextProtector:
    """Класс для защиты специальных элементов текста при рерайте"""
    
    # Регулярное выражение для поиска эмодзи
    EMOJI_PATTERN = re.compile(
        '['
        '\U0001F600-\U0001F64F'  # эмоции
        '\U0001F300-\U0001F5FF'  # символы и пиктограммы
        '\U0001F680-\U0001F6FF'  # транспорт и символы
        '\U0001F700-\U0001F77F'  # алхимические символы
        '\U0001F780-\U0001F7FF'  # геометрические фигуры
        '\U0001F800-\U0001F8FF'  # дополнительные стрелки
        '\U0001F900-\U0001F9FF'  # дополнительные символы
        '\U0001FA00-\U0001FA6F'  # дополнительные пиктограммы
        '\U0001FA70-\U0001FAFF'  # дополнительные символы
        '\U00002702-\U000027B0'  # декоративные символы
        '\U000024C2-\U0001F251' 
        ']+',
        flags=re.UNICODE
    )
    
    # Регулярные выражения для кавычек разных типов
    QUOTE_PATTERNS = [
        # Двойные кавычки "текст"
        (r'"([^"\\]*(\\.[^"\\]*)*)"', '【DOUBLE_QUOTE_{}】'),
        # Одинарные кавычки 'текст'
        (r"'([^'\\]*(\\.[^'\\]*)*)'", '【SINGLE_QUOTE_{}】'),
        # Елочки «текст»
        (r'«([^»]*)»', '【ANGLE_QUOTE_{}】'),
        # Лапки „текст“
        (r'„([^“]*)“', '【LOW_QUOTE_{}】'),
        # Марровские кавычки „текст“
        (r'‚([^‘]*)‘', '【LOW_SINGLE_QUOTE_{}】'),
        # Двойные лапки "текст" (альтернатива)
        (r'“([^”]*)”', '【CURLY_DOUBLE_QUOTE_{}】'),
        # Одинарные лапки 'текст' (альтернатива)
        (r'‘([^’]*)’', '【CURLY_SINGLE_QUOTE_{}】'),
    ]
    
    @staticmethod
    def extract_all_protected(text: str) -> Tuple[str, Dict[str, str]]:
        """
        Извлекает все защищенные элементы (эмодзи и текст в кавычках)
        
        Returns:
            Tuple[str, Dict[str, str]]: (текст с плейсхолдерами, словарь {плейсхолдер: оригинал})
        """
        protected_elements = {}
        
        # Сначала защищаем эмодзи
        text, emoji_dict = TextProtector._extract_emojis(text)
        protected_elements.update(emoji_dict)
        
        # Затем защищаем текст в кавычках
        text, quotes_dict = TextProtector._extract_quotes(text)
        protected_elements.update(quotes_dict)
        
        return text, protected_elements
    
    @staticmethod
    def _extract_emojis(text: str) -> Tuple[str, Dict[str, str]]:
        """Извлекает только эмодзи"""
        emojis = {}
        emoji_list = TextProtector.EMOJI_PATTERN.findall(text)
        text_with_placeholders = text
        
        for i, emoji in enumerate(emoji_list):
            placeholder = f"【EMOJI_{i}】"
            emojis[placeholder] = emoji
            text_with_placeholders = text_with_placeholders.replace(emoji, placeholder, 1)
        
        if emojis:
            print(f"😊 Найдено эмодзи: {len(emojis)} шт.")
        
        return text_with_placeholders, emojis
    
    @staticmethod
    def _extract_quotes(text: str) -> Tuple[str, Dict[str, str]]:
        """Извлекает текст в кавычках"""
        quotes = {}
        text_with_placeholders = text
        quote_counter = 0
        
        for pattern, placeholder_template in TextProtector.QUOTE_PATTERNS:
            def replacer(match):
                nonlocal quote_counter
                full_match = match.group(0)  # Вся цитата вместе с кавычками
                placeholder = placeholder_template.format(quote_counter)
                quotes[placeholder] = full_match
                quote_counter += 1
                return placeholder
            
            # Применяем замену для текущего типа кавычек
            text_with_placeholders = re.sub(pattern, replacer, text_with_placeholders, flags=re.DOTALL)
        
        if quotes:
            quote_types = {
                'DOUBLE_QUOTE': '"',
                'SINGLE_QUOTE': "'",
                'ANGLE_QUOTE': '«»',
                'LOW_QUOTE': '„“',
                'LOW_SINGLE_QUOTE': '‚‘',
                'CURLY_DOUBLE_QUOTE': '“”',
                'CURLY_SINGLE_QUOTE': '‘’',
            }
            print(f"📝 Найдено цитат: {len(quotes)} шт.")
        
        return text_with_placeholders, quotes
    
    @staticmethod
    def restore_all(text: str, protected_elements: Dict[str, str]) -> str:
        """
        Восстанавливает все защищенные элементы
        """
        restored_text = text
        for placeholder, original in protected_elements.items():
            restored_text = restored_text.replace(placeholder, original)
        return restored_text
    
    @staticmethod
    def protect_text(func):
        """
        Декоратор для защиты всех элементов в тексте
        """
        def wrapper(self, text, *args, **kwargs):
            # Сохраняем все защищенные элементы
            text_with_placeholders, protected_elements = TextProtector.extract_all_protected(text)
            
            # Если ничего не защищали, просто обрабатываем текст
            if not protected_elements:
                return func(self, text, *args, **kwargs)
            
            print(f"🛡️ Защищено элементов: {len(protected_elements)}")
            
            # Обрабатываем текст без защищенных элементов
            result = func(self, text_with_placeholders, *args, **kwargs)
            
            # Восстанавливаем все элементы
            if result and isinstance(result, str):
                result = TextProtector.restore_all(result, protected_elements)
            
            return result
        return wrapper

class GigaChatAPI:
    """Класс для работы с GigaChat API"""
    
    def __init__(self, auth_data: str, scope: str, model: str = "GigaChat"):
        self.auth_data = auth_data
        self.scope = scope
        self.model = model
        self.access_token = None
        self.token_expires = 0
        self.total_tokens_used = 0
        self.requests_count = 0
        self.text_protector = TextProtector()
        
    def get_access_token(self) -> Optional[str]:
        """Получение access токена"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
            
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Authorization': f'Basic {self.auth_data}',
            'RqUID': str(uuid.uuid4())
        }
        
        data = {'scope': self.scope}
        
        try:
            print("🔄 Получаю токен GigaChat...")
            response = requests.post(url, headers=headers, data=data, verify=False, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                
                if 'expires_in' in token_data:
                    expires_in = token_data['expires_in']
                    self.token_expires = time.time() + expires_in - 60
                    print(f"✅ Токен GigaChat получен, действует {expires_in} сек")
                else:
                    print("⚠️ Нет информации о времени жизни токена, использую 30 минут")
                    self.token_expires = time.time() + 1800 - 60
                
                return self.access_token
            else:
                print(f"❌ Ошибка получения токена GigaChat: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка подключения к GigaChat: {e}")
            return None
    
    @TextProtector.protect_text
    def rewrite_text(self, text: str) -> Optional[str]:
        """Отправка текста на рерайт в GigaChat с защитой всех элементов"""
        if not text or len(text.strip()) < MIN_TEXT_LENGTH_FOR_REWRITE:
            return text
        
        # Случайный выбор - рерайтить или нет
        if random.random() > REWRITE_PROBABILITY:
            print("⏭️ Пропускаю рерайт (экономия токенов)")
            return text
        
        # Обрезаем длинные тексты
        original_text = text
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."
            print(f"✂️ Текст обрезан до {MAX_TEXT_LENGTH} символов")
            
        token = self.get_access_token()
        if not token:
            return text
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # Промпт с инструкцией сохранять все защищенные элементы
        system_prompt = """Ты помогаешь переписывать тексты для Telegram канала. 

ВАЖНЫЕ ПРАВИЛА:
1. Сохраняй ВСЕ эмодзи на своих местах! 😊 🎉 👍
2. Сохраняй ВЕСЬ текст в кавычках БЕЗ ИЗМЕНЕНИЙ! 
   - Текст в "двойных кавычках" должен остаться точно таким же
   - Текст в «кавычках-елочках» должен остаться точно таким же
   - Текст в 'одинарных кавычках' должен остаться точно таким же
   - Текст в „разных“ видах кавычек должен остаться без изменений
3. Меняй только обычный текст вокруг кавычек и эмодзи
4. Не удаляй и не изменяй содержимое кавычек

Перефразируй текст, сохраняя смысл, но меняя форму изложения вне кавычек."""

        user_prompt = f"""Перепиши этот текст, сохраняя ВСЕ эмодзи и ВЕСЬ текст в кавычках без изменений:

{text}"""
        
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, verify=False, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Подсчет использованных токенов
                if 'usage' in result:
                    self.total_tokens_used += result['usage'].get('total_tokens', 0)
                    self.requests_count += 1
                    print(f"📊 Токенов использовано: {result['usage'].get('total_tokens', 0)}")
                
                # Извлекаем текст
                if 'choices' in result and len(result['choices']) > 0:
                    rewritten = result['choices'][0]['message']['content']
                    rewritten = rewritten.strip('"').strip("'")
                    
                    # Проверяем, что результат не пустой
                    if rewritten and len(rewritten) > 10:
                        print("✨ Текст обработан GigaChat")
                        return rewritten
                    else:
                        print("⚠️ Результат слишком короткий, использую оригинал")
                        return original_text
            else:
                print(f"❌ Ошибка GigaChat API: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка при рерайте: {e}")
            
        return original_text

# Инициализируем GigaChat
if USE_GIGACHAT:
    gigachat = GigaChatAPI(GIGACHAT_AUTH_DATA, GIGACHAT_SCOPE, GIGACHAT_MODEL)
    print(f"🤖 GigaChat инициализирован с моделью: {GIGACHAT_MODEL}")
    print(f"😊 Защита эмодзи: ВКЛЮЧЕНА")
    print(f"📝 Защита текста в кавычках: ВКЛЮЧЕНА")
else:
    gigachat = None

user_client = TelegramClient('user_session_oasismus', API_ID, API_HASH)
media_groups = {}

# Флаг для работы
is_running = True
reconnect_delay = 5

def check_ignore_words(text):
    """Проверка текста на наличие стоп-слов"""
    if not text: 
        return False
    text_lower = text.lower()
    for word in IGNORE_WORDS:
        if word.lower() in text_lower:
            return True
    return False

async def process_text(text: str) -> str:
    """Обработка текста через GigaChat с защитой всех элементов"""
    if not USE_GIGACHAT or not gigachat:
        return text
    
    # Не обрабатываем очень короткие тексты
    if len(text.strip()) < MIN_TEXT_LENGTH_FOR_REWRITE:
        print(f"⏭️ Текст слишком короткий ({len(text)} символов), пропускаю рерайт")
        return text
    
    try:
        loop = asyncio.get_event_loop()
        rewritten = await loop.run_in_executor(None, gigachat.rewrite_text, text)
        return rewritten if rewritten else text
    except Exception as e:
        print(f"⚠️ Ошибка при рерайте: {e}")
        return text

async def test_gigachat_connection():
    """Тест подключения к GigaChat с проверкой всех защит"""
    print("\n🔍 Тестируем подключение к GigaChat...")
    
    if not USE_GIGACHAT or not gigachat:
        print("❌ GigaChat отключен в настройках")
        return False
    
    # Тестовый текст с эмодзи и разными видами кавычек
    test_text = """Привет! 👋 Это тест с "важным текстом в двойных кавычках" и 'одинарными кавычками' 
и ещё «кавычками-елочками» и „лапками“. Проверяем защиту! 🎉 Нужно сохранить всё это без изменений! 👍"""
    
    print(f"📝 Оригинальный текст: {test_text}")
    
    # Проверяем извлечение защищенных элементов
    text_with_placeholders, protected = TextProtector.extract_all_protected(test_text)
    print(f"🔍 Найдено защищенных элементов: {len(protected)}")
    for placeholder, original in list(protected.items())[:3]:  # Покажем первые 3
        print(f"   {placeholder} -> {original}")
    
    processed = await process_text(test_text)
    print(f"✨ Обработанный текст: {processed}")
    
    # Проверяем, сохранились ли эмодзи
    emojis_in_result = TextProtector.EMOJI_PATTERN.findall(processed)
    emojis_in_original = TextProtector.EMOJI_PATTERN.findall(test_text)
    if len(emojis_in_result) == len(emojis_in_original):
        print("✅ Эмодзи успешно сохранены!")
    else:
        print(f"⚠️ Эмодзи: было {len(emojis_in_original)}, стало {len(emojis_in_result)}")
    
    # Проверяем, сохранились ли кавычки
    for pattern, _ in TextProtector.QUOTE_PATTERNS:
        quotes_in_result = re.findall(pattern, processed, re.DOTALL)
        quotes_in_original = re.findall(pattern, test_text, re.DOTALL)
        if len(quotes_in_result) != len(quotes_in_original):
            print(f"⚠️ Кавычки {pattern}: было {len(quotes_in_original)}, стало {len(quotes_in_result)}")
    
    if processed != test_text:
        print("✅ GigaChat работает корректно!")
        return True
    else:
        print("❌ GigaChat не обработал текст")
        return False

async def show_token_stats():
    """Показывает статистику использования токенов"""
    if gigachat:
        print("\n" + "="*50)
        print("📊 СТАТИСТИКА ИСПОЛЬЗОВАНИЯ GIGACHAT")
        print("="*50)
        print(f"Модель: {GIGACHAT_MODEL}")
        print(f"Выполнено запросов: {gigachat.requests_count}")
        print(f"Всего токенов использовано: {gigachat.total_tokens_used}")
        
        # Оценка остатка
        if GIGACHAT_MODEL == "GigaChat" or "Lite" in GIGACHAT_MODEL:
            limit = 900000
            remaining = limit - gigachat.total_tokens_used
            print(f"Лимит: 900 000 токенов")
            print(f"Осталось примерно: {remaining} токенов")
            if remaining > 0:
                print(f"Хватит еще на ~{remaining // 500} постов")
        elif "Pro" in GIGACHAT_MODEL:
            limit = 49123
            remaining = limit - gigachat.total_tokens_used
            print(f"Лимит: 49 123 токена")
            print(f"Осталось примерно: {remaining} токенов")
            if remaining > 0:
                print(f"Хватит еще на ~{remaining // 500} постов")
        print("="*50 + "\n")

def print_qr(url):
    """Печать QR-кода в консоль"""
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
    """Вход по QR-коду"""
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
    """Вход по коду из SMS"""
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
    
    # Находим сообщение с текстом
    text_message = None
    for msg in messages:
        if msg.text:
            text_message = msg
            break
    
    # Проверка на наличие текста
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
    
    # Обрабатываем текст через GigaChat если есть
    caption = None
    if text_message and text_message.text:
        caption = await process_text(text_message.text)
        if caption != text_message.text:
            print("✏️ Текст альбома изменен GigaChat")
    
    # Скачиваем все медиафайлы
    files = []
    from telethon.types import MessageMediaDocument
    
    for msg in messages:
        if msg.media:
            is_video = isinstance(msg.media, MessageMediaDocument) and msg.media.document.mime_type.startswith('video/')
            
            if is_video:
                files.append(msg)
            else:
                file_path = await msg.download_media()
                files.append(file_path)
    
    # Отправляем как альбом
    if files:
        try:
            if caption:
                await user_client.send_file(
                    TARGET_CHANNEL,
                    files,
                    caption=caption,
                    parse_mode='md'
                )
            else:
                if ALLOW_NO_TEXT_POSTS:
                    await user_client.send_file(TARGET_CHANNEL, files)
                else:
                    print(f"⏭️ Альбом без текста пропущен (настройки)")
                    del media_groups[grouped_id]
                    return
            
            print(f"✅ Альбом из {len(files)} элементов скопирован")
        except Exception as e:
            print(f"❌ Ошибка при отправке альбома: {e}")
    
    # Удаляем временные файлы
    for file_path in files:
        if isinstance(file_path, str) and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Не удалось удалить файл {file_path}: {e}")
    
    del media_groups[grouped_id]

async def run_bot():
    """Основная функция"""
    global is_running
    
    while is_running:
        try:
            print("\n" + "="*60)
            print("🔄 ЗАПУСК БОТА ДЛЯ КОПИРОВАНИЯ ПОСТОВ")
            print("="*60)
            print(f"🤖 GigaChat: {'✅ ВКЛЮЧЕН' if USE_GIGACHAT else '❌ ВЫКЛЮЧЕН'}")
            if USE_GIGACHAT:
                print(f"   Модель: {GIGACHAT_MODEL}")
                print(f"😊 Защита эмодзи: ✅ ВКЛЮЧЕНА")
                print(f"📝 Защита кавычек: ✅ ВКЛЮЧЕНА")
                
                # Тестируем подключение
                await test_gigachat_connection()
            
            print(f"📝 Посты без текста: {'❌ ЗАПРЕЩЕНЫ' if not ALLOW_NO_TEXT_POSTS else '✅ РАЗРЕШЕНЫ'}")
            print("="*60 + "\n")
            
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
                        
                        if grouped_id not in media_groups:
                            media_groups[grouped_id] = {
                                'messages': [message],
                                'source': source_name
                            }
                            asyncio.create_task(delayed_process(grouped_id, source_name))
                        else:
                            media_groups[grouped_id]['messages'].append(message)
                        
                        return
                    
                    # Одиночное сообщение
                    if not ALLOW_NO_TEXT_POSTS and not message.text:
                        print(f"⏭️ Пропускаю пост из {source_name} (нет текста)")
                        return
                    
                    if check_ignore_words(message.text or ""):
                        print(f"🚫 Игнорирую пост из {source_name} (есть стоп-слово)")
                        return
                    
                    print(f"📥 Копирую пост из {source_name}")
                    
                    processed_text = None
                    if message.text:
                        processed_text = await process_text(message.text)
                        if processed_text != message.text:
                            print("✏️ Текст изменен GigaChat")
                    
                    if message.media:
                        from telethon.types import MessageMediaDocument
                        is_video = isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/')
                        
                        if is_video:
                            await user_client.send_file(
                                TARGET_CHANNEL,
                                message,
                                caption=processed_text or "",
                                parse_mode='md'
                            )
                            print(f"✅ Видео скопировано")
                        else:
                            file_path = None
                            try:
                                file_path = await message.download_media()
                                await user_client.send_file(
                                    TARGET_CHANNEL,
                                    file_path,
                                    caption=processed_text or "",
                                    parse_mode='md'
                                )
                                print(f"✅ Фото скопировано")
                            finally:
                                if file_path and os.path.exists(file_path):
                                    try:
                                        os.remove(file_path)
                                    except Exception as e:
                                        print(f"⚠️ Не удалось удалить файл: {e}")
                    
                    elif message.text and processed_text:
                        await user_client.send_message(
                            TARGET_CHANNEL,
                            processed_text,
                            parse_mode='md'
                        )
                        print(f"✅ Текстовый пост скопирован")
                            
                except FloodWaitError as e:
                    print(f"⚠️ Флуд-контроль: ждем {e.seconds}с")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

            async def delayed_process(grouped_id, source_name):
                await asyncio.sleep(ALBUM_WAIT_TIME)
                await process_album(grouped_id, source_name)
            
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
    """Главная функция"""
    global is_running
    try:
        await run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    finally:
        is_running = False
        await user_client.disconnect()
        await show_token_stats()
        print("👋 Сессия закрыта")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        input("Нажми Enter для выхода...")