import asyncio
import os
import qrcode
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import MessageEntityTextUrl, MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityUnderline, MessageEntityStrike
import time
import requests
import json
import uuid
import random
import re
from typing import Optional, Dict, Any, List, Tuple
import warnings
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime, timedelta

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
    '@oasis_musp'
]

TARGET_CHANNEL = '@reklamaomg'  # Твой канал (куда постим)

# ========== НАСТРОЙКИ ДЛЯ РАЗНЫХ КАНАЛОВ ==========

# Канал-исключение (100% публикация, без стоп-слов)
EXCEPTION_CHANNEL = '@oasis_musp'

# Стоп-слова (не работают для канала-исключения)
IGNORE_WORDS = [
    'реклама', 'реклам', 'промокод', 'скидка',
    'акция', 'спонсор', 'купон', 'партнерский', '#реклама', 'СЛУШАТЬ!', 'ГРЯДУЩИЕ НОВИНКИ'
]

# НАСТРОЙКИ ПО УМОЛЧАНИЮ (для всех каналов, кроме исключения)
DEFAULT_POST_PROBABILITY = 0.6  # 60% постов
DEFAULT_REWRITE_PROBABILITY = 0.8  # 80% рерайт

# НАСТРОЙКИ ДЛЯ КАНАЛА-ИСКЛЮЧЕНИЯ
EXCEPTION_POST_PROBABILITY = 1.0  # 100% постов
EXCEPTION_REWRITE_PROBABILITY = 0.8  # 80% рерайт
EXCEPTION_IGNORE_WORDS = []  # Нет стоп-слов

# =================================================

# 👇 НАСТРОЙКА ПУБЛИКАЦИИ ПОСТОВ БЕЗ ТЕКСТА
ALLOW_NO_TEXT_POSTS = False

# ========== НАСТРОЙКА GIGACHAT ==========
USE_GIGACHAT = True

# Данные для авторизации
GIGACHAT_CLIENT_ID = '019ce2bd-3dd4-7673-91c1-1197d552d34c'
GIGACHAT_CLIENT_SECRET = 'aaf4b627-fa9d-4572-a358-9ed5a96e3ee4'
GIGACHAT_AUTH_DATA = 'MDE5Y2UyYmQtM2RkNC03NjczLTkxYzEtMTE5N2Q1NTJkMzRjOmFhZjRiNjI3LWZhOWQtNDU3Mi1hMzU4LTllZDVhOTZlM2VlNA=='
GIGACHAT_SCOPE = 'GIGACHAT_API_PERS'

# ========== НАСТРОЙКА МОДЕЛЕЙ И ЭКОНОМИИ ТОКЕНОВ ==========

MODELS_CONFIG = {
    "GigaChat": {
        "name": "GigaChat",
        "description": "Базовая модель, быстрая и экономичная",
        "daily_limit": 900000,
        "cost_per_request": 100,
        "quality": "medium",
        "recommended_for": "обычные посты"
    },
    "GigaChat-Pro": {
        "name": "GigaChat-Pro",
        "description": "Улучшенная модель, лучше следует инструкциям",
        "daily_limit": 49123,
        "cost_per_request": 300,
        "quality": "high",
        "recommended_for": "важные посты, сложный рерайт"
    },
    "GigaChat-Max": {
        "name": "GigaChat-Max",
        "description": "Максимальное качество для сложных задач",
        "daily_limit": 36791,
        "cost_per_request": 500,
        "quality": "very_high",
        "recommended_for": "очень важные посты, креативные задачи"
    }
}

SELECTED_MODEL = "GigaChat"

# ========== НАСТРОЙКИ ЭКОНОМИИ ТОКЕНОВ ==========
MIN_TEXT_LENGTH_FOR_REWRITE = 50
MAX_TEXT_LENGTH = 1500
USE_SMART_MODEL_SELECTION = False
DAILY_TOKEN_LIMIT = 100000
daily_tokens_used = 0
last_token_reset = datetime.now()
USE_CACHE = True
rewrite_cache = {}
CACHE_MAX_SIZE = 100
ALBUM_WAIT_TIME = 1.5

# ================================

class TextFormatter:
    """Класс для работы с форматированием текста"""
    
    @staticmethod
    def preserve_formatting(text: str, entities: List) -> str:
        """
        Сохраняет форматирование из entities
        """
        if not entities:
            return text
        
        # Сортируем сущности в обратном порядке
        sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)
        
        formatted_text = text
        for entity in sorted_entities:
            start = entity.offset
            end = start + entity.length
            entity_text = formatted_text[start:end]
            
            if isinstance(entity, MessageEntityBold):
                formatted_text = formatted_text[:start] + f'**{entity_text}**' + formatted_text[end:]
            elif isinstance(entity, MessageEntityItalic):
                formatted_text = formatted_text[:start] + f'__{entity_text}__' + formatted_text[end:]
            elif isinstance(entity, MessageEntityUnderline):
                formatted_text = formatted_text[:start] + f'__{entity_text}__' + formatted_text[end:]
            elif isinstance(entity, MessageEntityStrike):
                formatted_text = formatted_text[:start] + f'~{entity_text}~' + formatted_text[end:]
            elif isinstance(entity, MessageEntityTextUrl):
                formatted_text = formatted_text[:start] + f'[{entity_text}]({entity.url})' + formatted_text[end:]
        
        return formatted_text

class GigaChatAPI:
    """Класс для работы с GigaChat API"""
    
    def __init__(self, auth_data: str, scope: str, model_configs: Dict, selected_model: str):
        self.auth_data = auth_data
        self.scope = scope
        self.model_configs = model_configs
        self.selected_model = selected_model
        self.current_model = selected_model
        self.access_token = None
        self.token_expires = 0
        self.total_tokens_used = 0
        self.requests_count = 0
        self.daily_tokens = 0
        self.last_reset = datetime.now()
        self.model_stats = {model: {"requests": 0, "tokens": 0} for model in model_configs}
        
    def _reset_daily_counter(self):
        now = datetime.now()
        if now.date() > self.last_reset.date():
            self.daily_tokens = 0
            self.last_reset = now
            print("📊 Дневной лимит токенов сброшен")
    
    def _check_daily_limit(self) -> bool:
        self._reset_daily_counter()
        return self.daily_tokens < DAILY_TOKEN_LIMIT
    
    def get_access_token(self) -> Optional[str]:
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
                    print("ℹ️ Токен получен (срок не указан, использую 30 минут)")
                    self.token_expires = time.time() + 1800 - 60
                
                return self.access_token
            else:
                print(f"❌ Ошибка получения токена GigaChat: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка подключения к GigaChat: {e}")
            return None
    
    def _get_cache_key(self, text: str) -> str:
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()
    
    def rewrite_text(self, text: str) -> Optional[str]:
        """Отправка текста на рерайт"""
        
        if not text or len(text.strip()) < MIN_TEXT_LENGTH_FOR_REWRITE:
            print(f"⏭️ Текст слишком короткий ({len(text)} символов), пропускаю рерайт")
            return text
        
        if not self._check_daily_limit():
            print("⚠️ Дневной лимит токенов превышен, пропускаю рерайт")
            return text
        
        # Проверка кэша
        if USE_CACHE:
            cache_key = self._get_cache_key(text)
            if cache_key in rewrite_cache:
                print("📦 Использую кэшированный результат")
                return rewrite_cache[cache_key]
        
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
        
        system_prompt = """Ты помогаешь переписывать тексты. 
Твоя задача: перефразировать текст, сохраняя смысл, но меняя форму изложения.
Не добавляй ничего от себя, не удаляй важную информацию, особенно цитаты.
Сохраняй все эмодзи и ссылки без изменений."""

        user_prompt = f"""Перепиши следующий текст, сохраняя все эмодзи. Не трогай цитаты или строчки песен!:

{text}"""
        
        data = {
            "model": self.selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.8,
            "max_tokens": 1000,
        }
        
        try:
            print(f"🔄 Отправляю запрос в GigaChat...")
            response = requests.post(url, headers=headers, json=data, verify=False, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if 'usage' in result:
                    tokens_used = result['usage'].get('total_tokens', 0)
                    self.total_tokens_used += tokens_used
                    self.daily_tokens += tokens_used
                    self.requests_count += 1
                    print(f"📊 Токенов использовано: {tokens_used}")
                
                if 'choices' in result and len(result['choices']) > 0:
                    rewritten = result['choices'][0]['message']['content']
                    rewritten = rewritten.strip('"').strip("'")
                    
                    if USE_CACHE and len(rewrite_cache) < CACHE_MAX_SIZE:
                        rewrite_cache[self._get_cache_key(original_text)] = rewritten
                    
                    if rewritten != original_text:
                        print(f"✨ Текст успешно обработан GigaChat")
                        return rewritten
                    else:
                        return original_text
            else:
                print(f"❌ Ошибка GigaChat API: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка при рерайте: {e}")
            
        return original_text

# Инициализируем GigaChat
if USE_GIGACHAT:
    gigachat = GigaChatAPI(GIGACHAT_AUTH_DATA, GIGACHAT_SCOPE, MODELS_CONFIG, SELECTED_MODEL)
    print(f"🤖 GigaChat инициализирован")
    print(f"   Выбранная модель: {SELECTED_MODEL}")
    
    print(f"\n📊 НАСТРОЙКИ КАНАЛОВ:")
    print(f"   📍 По умолчанию для всех каналов:")
    print(f"      • Вероятность поста: {DEFAULT_POST_PROBABILITY*100}%")
    print(f"      • Вероятность рерайта: {DEFAULT_REWRITE_PROBABILITY*100}%")
    print(f"   ⭐ Исключение для {EXCEPTION_CHANNEL}:")
    print(f"      • Вероятность поста: {EXCEPTION_POST_PROBABILITY*100}%")
    print(f"      • Вероятность рерайта: {EXCEPTION_REWRITE_PROBABILITY*100}%")
    print(f"      • Стоп-слова: ❌ ОТКЛЮЧЕНЫ")
else:
    gigachat = None

user_client = TelegramClient('user_session_oasismus', API_ID, API_HASH)
media_groups = {}
is_running = True
reconnect_delay = 5
processed_messages = set()  # Для отслеживания обработанных сообщений


def is_exception_channel(channel_name: str) -> bool:
    """Проверяет, является ли канал исключением"""
    return channel_name == EXCEPTION_CHANNEL

def get_post_probability(channel_name: str) -> float:
    """Получает вероятность публикации для канала"""
    if is_exception_channel(channel_name):
        return EXCEPTION_POST_PROBABILITY
    return DEFAULT_POST_PROBABILITY

def get_rewrite_probability(channel_name: str) -> float:
    """Получает вероятность рерайта для канала"""
    if is_exception_channel(channel_name):
        return EXCEPTION_REWRITE_PROBABILITY
    return DEFAULT_REWRITE_PROBABILITY

def get_ignore_words(channel_name: str) -> List[str]:
    """Получает список стоп-слов для канала"""
    if is_exception_channel(channel_name):
        return EXCEPTION_IGNORE_WORDS
    return IGNORE_WORDS

def should_post(channel_name: str) -> bool:
    """Определяет, нужно ли постить пост из этого канала"""
    probability = get_post_probability(channel_name)
    
    if probability >= 1.0:
        return True
    
    return random.random() < probability

def should_rewrite(channel_name: str) -> bool:
    """Определяет, нужно ли рерайтить пост из этого канала"""
    # Даже для исключения рерайт 80%
    probability = get_rewrite_probability(channel_name)
    
    if probability >= 1.0:
        return True
    
    return random.random() < probability

def check_ignore_words(text: str, channel_name: str) -> bool:
    """Проверка текста на наличие стоп-слов с учетом канала"""
    if not text: 
        return False
    
    ignore_words = get_ignore_words(channel_name)
    
    # Если для канала нет стоп-слов, сразу возвращаем False
    if not ignore_words:
        return False
    
    text_lower = text.lower()
    for word in ignore_words:
        if word.lower() in text_lower:
            return True
    return False

async def process_text(text: str, channel_name: str, original_entities: List = None) -> str:
    """Обработка текста через GigaChat с учетом настроек канала"""
    
    if USE_GIGACHAT and gigachat and text and len(text.strip()) > MIN_TEXT_LENGTH_FOR_REWRITE:
        if should_rewrite(channel_name):
            try:
                loop = asyncio.get_event_loop()
                rewritten = await loop.run_in_executor(None, gigachat.rewrite_text, text)
                
                if rewritten and rewritten != text:
                    print("✏️ Текст изменен GigaChat")
                    return rewritten
                else:
                    print("⏭️ Текст не изменен")
                    if original_entities:
                        return TextFormatter.preserve_formatting(text, original_entities)
                    return text
            except Exception as e:
                print(f"⚠️ Ошибка при рерайте: {e}")
                if original_entities:
                    return TextFormatter.preserve_formatting(text, original_entities)
                return text
        else:
            print("⏭️ Пропускаю рерайт (настройки канала)")
            if original_entities:
                return TextFormatter.preserve_formatting(text, original_entities)
            return text
    else:
        if original_entities:
            return TextFormatter.preserve_formatting(text, original_entities)
        return text

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
    if grouped_id not in media_groups:
        return
    
    album_data = media_groups[grouped_id]
    messages = album_data['messages']
    
    messages.sort(key=lambda m: m.id)
    
    text_message = None
    for msg in messages:
        if msg.text:
            text_message = msg
            break
    
    if not ALLOW_NO_TEXT_POSTS and not text_message:
        print(f"⏭️ Пропускаю альбом из {source_name} (нет текста)")
        del media_groups[grouped_id]
        return
    
    if text_message and text_message.text and check_ignore_words(text_message.text, source_name):
        print(f"🚫 Игнорирую альбом из {source_name} (есть стоп-слово)")
        del media_groups[grouped_id]
        return
    
    print(f"📦 Копирую альбом из {len(messages)} элементов из {source_name}")
    
    caption = None
    if text_message and text_message.text:
        caption = await process_text(text_message.text, source_name, text_message.entities)
        if caption != text_message.text:
            print("✏️ Текст альбома изменен GigaChat")
    
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
    
    for file_path in files:
        if isinstance(file_path, str) and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Не удалось удалить файл {file_path}: {e}")
    
    del media_groups[grouped_id]

async def run_bot():
    global is_running, processed_messages
    
    while is_running:
        try:
            print("\n" + "="*60)
            print("🔄 ЗАПУСК БОТА ДЛЯ КОПИРОВАНИЯ ПОСТОВ")
            print("="*60)
            print(f"🤖 GigaChat: {'✅ ВКЛЮЧЕН' if USE_GIGACHAT else '❌ ВЫКЛЮЧЕН'}")
            if USE_GIGACHAT:
                print(f"   Модель: {SELECTED_MODEL}")
            
            print(f"\n📊 НАСТРОЙКИ КАНАЛОВ:")
            print(f"   📍 По умолчанию для всех каналов:")
            print(f"      • Вероятность поста: {DEFAULT_POST_PROBABILITY*100}%")
            print(f"      • Вероятность рерайта: {DEFAULT_REWRITE_PROBABILITY*100}%")
            print(f"   ⭐ Исключение для {EXCEPTION_CHANNEL}:")
            print(f"      • Вероятность поста: {EXCEPTION_POST_PROBABILITY*100}%")
            print(f"      • Вероятность рерайта: {EXCEPTION_REWRITE_PROBABILITY*100}%")
            print(f"      • Стоп-слова: ❌ ОТКЛЮЧЕНЫ")
            
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
            
            print("\n🔄 Проверяю каналы-источники:")
            valid_channels = []
            for channel in SOURCE_CHANNELS:
                try:
                    entity = await user_client.get_entity(channel)
                    print(f"   ✅ Найден: {channel}")
                    valid_channels.append(entity)
                except Exception as e:
                    print(f"   ❌ Ошибка с {channel}: {e}")
            
            if not valid_channels:
                print("❌ Нет доступных каналов для отслеживания!")
                return
            
            print(f"\n📢 Отслеживаю каналы: {', '.join(SOURCE_CHANNELS)}")
            print(f"📨 Канал-приемник: {TARGET_CHANNEL}")
            print("🟢 Бот работает... (нажми Ctrl+C для остановки)\n")

            @user_client.on(events.NewMessage(chats=valid_channels))
            async def handle_message(event):
                try:
                    message = event.message
                    
                    # Пропускаем уже обработанные сообщения
                    if message.id in processed_messages:
                        return
                    
                    chat = await event.get_chat()
                    source_name = getattr(chat, 'username', str(chat.id))

                    # Проверяем вероятность публикации
                    if not should_post(source_name):
                        prob = get_post_probability(source_name) * 100
                        print(f"⏭️ Пропускаю пост из {source_name} (вероятность {prob}%)")
                        processed_messages.add(message.id)
                        return
                    
                    # Проверяем стоп-слова с учетом канала
                    if check_ignore_words(message.text or "", source_name):
                        print(f"🚫 Игнорирую пост из {source_name} (есть стоп-слово)")
                        processed_messages.add(message.id)
                        return
                    
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
                        
                        processed_messages.add(message.id)
                        return
                    
                    if not ALLOW_NO_TEXT_POSTS and not message.text:
                        print(f"⏭️ Пропускаю пост из {source_name} (нет текста)")
                        processed_messages.add(message.id)
                        return
                    
                    print(f"📥 Копирую пост из {source_name}")
                    
                    processed_text = await process_text(message.text or "", source_name, message.entities)
                    
                    if processed_text != message.text:
                        print("✏️ Текст изменен GigaChat")
                    
                    if message.media:
                        from telethon.types import MessageMediaDocument
                        is_video = isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/')
                        
                        if is_video:
                            await user_client.send_file(
                                TARGET_CHANNEL,
                                message,
                                caption=processed_text,
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
                                    caption=processed_text,
                                    parse_mode='md'
                                )
                                print(f"✅ Фото скопировано")
                            finally:
                                if file_path and os.path.exists(file_path):
                                    try:
                                        os.remove(file_path)
                                    except Exception as e:
                                        print(f"⚠️ Не удалось удалить файл: {e}")
                    
                    elif message.text:
                        await user_client.send_message(
                            TARGET_CHANNEL,
                            processed_text,
                            parse_mode='md'
                        )
                        print(f"✅ Текстовый пост скопирован")
                    
                    processed_messages.add(message.id)
                    
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
    global is_running
    try:
        await run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    finally:
        is_running = False
        await user_client.disconnect()
        if USE_GIGACHAT and gigachat:
            print("\n" + "="*50)
            print("📊 ИТОГОВАЯ СТАТИСТИКА")
            print("="*50)
            print(f"Всего запросов: {gigachat.requests_count}")
            print(f"Всего токенов использовано: {gigachat.total_tokens_used}")
        print("👋 Сессия закрыта")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        input("Нажми Enter для выхода...")