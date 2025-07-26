import os
import logging
import asyncio
from typing import Optional
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes, 
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GeminiTelegramBot:
    def __init__(self, telegram_token: str, gemini_api_key: str):
        """
        Инициализация Telegram бота с Gemini AI
        
        Args:
            telegram_token: Токен Telegram бота
            gemini_api_key: API ключ для Gemini
        """
        self.telegram_token = telegram_token
        
        # Настройка Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.vision_model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Хранение истории чатов для каждого пользователя
        self.chat_history = {}
        
    def list_available_models(self):
        """Показать доступные модели Gemini"""
        try:
            models = genai.list_models()
            print("🤖 Доступные модели Gemini:")
            for model in models:
                if 'generateContent' in model.supported_generation_methods:
                    print(f"   • {model.name}")
        except Exception as e:
            print(f"❌ Ошибка получения моделей: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        keyboard = [
            [InlineKeyboardButton("🤖 Новый чат", callback_data='new_chat')],
            [InlineKeyboardButton("📋 Помощь", callback_data='help')],
            [InlineKeyboardButton("🔧 Настройки", callback_data='settings')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🤖 **Добро пожаловать в Gemini AI Bot!**

Я умею:
• 💬 Отвечать на любые вопросы
• 🖼️ Анализировать изображения
• 📝 Помогать с текстами
• 🧠 Решать задачи

Просто напишите мне сообщение или отправьте фото!
        """
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
🔍 **Команды бота:**

/start - Запуск бота
/help - Эта справка
/new - Новый чат (очистить историю)
/image - Анализ изображения (отправьте фото)

📝 **Как использовать:**
• Просто напишите вопрос
• Отправьте фото для анализа
• Используйте /new для сброса контекста

🎯 **Примеры вопросов:**
• "Объясни квантовую физику"
• "Напиши код на Python"
• "Переведи текст на английский"
• "Придумай историю про робота"
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def new_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /new - новый чат"""
        user_id = update.effective_user.id
        self.chat_history[user_id] = []
        
        await update.message.reply_text(
            "🔄 **История чата очищена!**\n\nТеперь можете начать новый разговор.",
            parse_mode='Markdown'
        )

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        user_id = update.effective_user.id
        user_text = update.message.text
        
        # Отправляем индикатор "печатает"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action='typing'
        )
        
        try:
            # Инициализация истории для нового пользователя
            if user_id not in self.chat_history:
                self.chat_history[user_id] = []
            
            # Добавляем сообщение пользователя в историю
            self.chat_history[user_id].append({
                'role': 'user',
                'parts': [user_text]
            })
            
            # Создаем чат с историей
            chat = self.model.start_chat(history=self.chat_history[user_id][:-1])
            
            # Получаем ответ от Gemini
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: chat.send_message(user_text)
            )
            
            # Добавляем ответ в историю
            self.chat_history[user_id].append({
                'role': 'model',
                'parts': [response.text]
            })
            
            # Ограничиваем историю (последние 10 сообщений)
            if len(self.chat_history[user_id]) > 20:
                self.chat_history[user_id] = self.chat_history[user_id][-20:]
            
            # Отправляем ответ пользователю
            await self.send_long_message(update, response.text)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
            await update.message.reply_text(
                f"❌ **Произошла ошибка:**\n`{str(e)}`\n\nПопробуйте еще раз.",
                parse_mode='Markdown'
            )

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка изображений"""
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action='typing'
        )
        
        try:
            # Получаем фото
            photo = update.message.photo[-1]  # Берем фото наибольшего размера
            photo_file = await photo.get_file()
            
            # Скачиваем временно
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                await photo_file.download_to_drive(tmp_file.name)
                
                # Анализируем изображение
                import PIL.Image
                img = PIL.Image.open(tmp_file.name)
                
                # Получаем описание изображения (или используем caption пользователя)
                prompt = update.message.caption or "Опиши подробно что видишь на этом изображении"
                
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.vision_model.generate_content([prompt, img])
                )
                
                await self.send_long_message(update, f"🖼️ **Анализ изображения:**\n\n{response.text}")
                
                # Удаляем временный файл
                os.unlink(tmp_file.name)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения: {e}")
            await update.message.reply_text(
                f"❌ **Ошибка при анализе изображения:**\n`{str(e)}`",
                parse_mode='Markdown'
            )

    async def send_long_message(self, update: Update, text: str):
        """Отправка длинных сообщений с разбивкой"""
        max_length = 4096
        
        if len(text) <= max_length:
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            # Разбиваем на части
            parts = []
            while text:
                if len(text) <= max_length:
                    parts.append(text)
                    break
                
                # Ищем подходящее место для разрыва
                cut_pos = max_length
                while cut_pos > 0 and text[cut_pos] not in ['\n', '.', '!', '?', ' ']:
                    cut_pos -= 1
                
                if cut_pos == 0:
                    cut_pos = max_length
                
                parts.append(text[:cut_pos])
                text = text[cut_pos:].lstrip()
            
            # Отправляем части
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(part, parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"*...продолжение ({i+1}/{len(parts)})*\n\n{part}", parse_mode='Markdown')

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'new_chat':
            user_id = update.effective_user.id
            self.chat_history[user_id] = []
            await query.edit_message_text("🔄 **История чата очищена!**", parse_mode='Markdown')
        
        elif query.data == 'help':
            help_text = """
🔍 **Команды бота:**

/start - Запуск бота
/help - Справка
/new - Новый чат

📝 **Как использовать:**
• Напишите вопрос
• Отправьте фото для анализа
            """
            await query.edit_message_text(help_text, parse_mode='Markdown')
        
        elif query.data == 'settings':
            await query.edit_message_text("⚙️ **Настройки пока недоступны**", parse_mode='Markdown')

    def run(self):
        """Запуск бота"""
        # Создаем приложение
        application = Application.builder().token(self.telegram_token).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("new", self.new_chat_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo_message))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Запускаем бота
        print("🤖 Бот запущен! Нажмите Ctrl+C для остановки.")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    # Конфигурация
    TELEGRAM_TOKEN = "8479475949:AAG8rD6FqSvLBDqmSyIgwid0njehFnzGzjI"  # Замените на токен вашего бота
    GEMINI_API_KEY = "AIzaSyCz94WXNGjtkQjb7jGfw_8iAwXF4c3Z0Ds"  # Ваш Gemini API ключ
    
    # Проверка токенов
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("❌ Ошибка: Укажите токен Telegram бота!")
        print("📝 Получите токен у @BotFather в Telegram")
        return
    
    try:
        # Создаем бота и проверяем доступные модели
        bot = GeminiTelegramBot(TELEGRAM_TOKEN, GEMINI_API_KEY)
        bot.list_available_models()  # Показать доступные модели
        bot.run()
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        print("💡 Попробуйте другую модель или проверьте API ключ")

if __name__ == "__main__":
    main()