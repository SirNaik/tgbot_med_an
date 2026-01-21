import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
import tempfile
from docx import Document
from PyPDF2 import PdfReader
import openpyxl
from PIL import Image
import io

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Initialize GigaChat client
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE")

if GIGACHAT_CREDENTIALS and GIGACHAT_SCOPE:
    giga = GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False,
    )
else:
    logger.warning("GigaChat credentials not found. Please set GIGACHAT_CREDENTIALS and GIGACHAT_SCOPE environment variables.")

def log_user_interaction(user_id, user_name, username=None, file_type=None):
    """Log user interaction to users.txt file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if this is the user's first request
    is_first_request = True
    request_count = 1
    
    # Read existing data to check if user already exists
    if os.path.exists('users.txt'):
        with open('users.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split('|')
                if len(parts) >= 3 and parts[0] == str(user_id):
                    is_first_request = False
                    # Get the current count and increment
                    request_count = int(parts[6]) + 1 if len(parts) >= 7 else 2
                    break
    
    request_type = "first" if is_first_request else "repeat"
    
    # Format: user_id|user_name|username|timestamp|file_type|request_type|total_requests
    log_entry = f"{user_id}|{user_name}|{username or 'N/A'}|{timestamp}|{file_type or 'N/A'}|{request_type}|{request_count}\n"
    
    with open('users.txt', 'a', encoding='utf-8') as f:
        f.write(log_entry)

class MedicalAnalysisBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when the command /start is issued."""
        user = update.effective_user
        
        # Log user interaction
        log_user_interaction(
            user_id=user.id, 
            user_name=f"{user.first_name} {user.last_name or ''}".strip(), 
            username=user.username,
            file_type='start_command'
        )
        
        welcome_message = (
            "Привет! 🏥\n\n"
            "Этот бот умеет расшифровывать медицинские лабораторные анализы.\n"
            "Я помогу вам понять, где и какие результаты отличаются от нормы, "
            "с чем это может быть связано и на что обратить внимание.\n\n"
            "Пожалуйста, загрузите документ с результатами анализов (поддерживаются форматы: "
            "DOC, DOCX, XLS, PDF, JPEG). После загрузки я проанализирую данные и дам разъяснения."
        )
        await update.message.reply_text(welcome_message)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document uploads and send to GigaChat for analysis."""
        user = update.effective_user
        message = update.message
        
        # Log user interaction
        file_extension = os.path.splitext(message.document.file_name)[1]
        log_user_interaction(
            user_id=user.id, 
            user_name=f"{user.first_name} {user.last_name or ''}".strip(), 
            username=user.username,
            file_type=file_extension
        )
        
        # Inform user that processing has started
        processing_msg = await message.reply_text("Обрабатываю документ... Подождите немного.")
        
        try:
            # Get file from message
            file = await context.bot.get_file(message.document.file_id)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                await file.download_to_memory(temp_file)
                temp_file_path = temp_file.name
            
            # Extract text from the document based on its type
            text_content = self.extract_text_from_document(temp_file_path, message.document.file_name)
            
            if not text_content:
                await message.reply_text("Не удалось извлечь текст из документа. Попробуйте другой файл.")
                os.unlink(temp_file_path)
                return
            
            # Analyze with GigaChat
            analysis_result = self.analyze_with_gigachat(text_content)
            
            # Send the analysis result back to user
            await message.reply_text(analysis_result)
            
        except Exception as e:
            # Log document processing error to both logger and log.txt file
            error_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error processing document {message.document.file_name}: {e}"
            logger.error(error_msg)
            
            # Write to log.txt file
            with open('log.txt', 'a', encoding='utf-8') as log_file:
                log_file.write(error_msg + "\n")
                
            await message.reply_text("Произошла ошибка при обработке документа. Попробуйте снова.")
        finally:
            # Clean up temporary file
            if 'temp_file_path' in locals():
                os.unlink(temp_file_path)
            
            # Delete the processing message
            try:
                await processing_msg.delete()
            except:
                pass
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads and send to GigaChat for analysis."""
        user = update.effective_user
        message = update.message
        
        # Log user interaction
        log_user_interaction(
            user_id=user.id, 
            user_name=f"{user.first_name} {user.last_name or ''}".strip(), 
            username=user.username,
            file_type='image'
        )
        
        # Inform user that processing has started
        processing_msg = await message.reply_text("Обрабатываю изображение... Подождите немного.")
        
        try:
            # Get the largest photo from the message
            photo = message.photo[-1]  # Last item is the highest resolution
            file = await context.bot.get_file(photo.file_id)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                await file.download_to_memory(temp_file)
                temp_file_path = temp_file.name
            
            # For images, we'll just read as text (OCR would be needed for actual text extraction)
            # Here we'll convert image to base64 string to pass to GigaChat if it supports image processing
            with open(temp_file_path, 'rb') as img_file:
                img_data = img_file.read()
                
            # For now, we'll just pass a message to GigaChat indicating an image was uploaded
            text_content = f"Пользователь загрузил изображение медицинского документа с результатами анализов. Пожалуйста, предоставьте интерпретацию этих результатов."
            
            # Analyze with GigaChat
            analysis_result = self.analyze_with_gigachat(text_content)
            
            # Send the analysis result back to user
            await message.reply_text(analysis_result)
            
        except Exception as e:
            # Log photo processing error to both logger and log.txt file
            error_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error processing photo: {e}"
            logger.error(error_msg)
            
            # Write to log.txt file
            with open('log.txt', 'a', encoding='utf-8') as log_file:
                log_file.write(error_msg + "\n")
                
            await message.reply_text("Произошла ошибка при обработке изображения. Попробуйте снова.")
        finally:
            # Clean up temporary file
            if 'temp_file_path' in locals():
                os.unlink(temp_file_path)
            
            # Delete the processing message
            try:
                await processing_msg.delete()
            except:
                pass
    
    def extract_text_from_document(self, file_path, filename):
        """Extract text from various document formats."""
        _, ext = os.path.splitext(filename.lower())
        
        try:
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as file:
                    return file.read()
                    
            elif ext in ['.docx']:
                doc = Document(file_path)
                full_text = []
                for para in doc.paragraphs:
                    full_text.append(para.text)
                return '\n'.join(full_text)
                
            elif ext in ['.pdf']:
                try:
                    reader = PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    return text
                except Exception as pdf_error:
                    # Log PDF-specific error to both logger and log.txt file
                    error_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error processing PDF {filename}: {pdf_error}"
                    logger.error(error_msg)
                    
                    # Write to log.txt file
                    with open('log.txt', 'a', encoding='utf-8') as log_file:
                        log_file.write(error_msg + "\n")
                    
                    return None
                
            elif ext in ['.xls', '.xlsx']:
                workbook = openpyxl.load_workbook(file_path, data_only=True)
                sheet = workbook.active
                text = ""
                for row in sheet.iter_rows(values_only=True):
                    row_text = [str(cell) if cell is not None else "" for cell in row]
                    text += "\t".join(row_text) + "\n"
                return text
                
            elif ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
                # For images, we might want to implement OCR in the future
                # For now, just return a placeholder
                return f"Пользователь загрузил изображение файла: {filename}. Требуется OCR для извлечения текста."
                
            else:
                return None
                
        except Exception as e:
            # Log general error to both logger and log.txt file
            error_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error extracting text from {filename}: {e}"
            logger.error(error_msg)
            
            # Write to log.txt file
            with open('log.txt', 'a', encoding='utf-8') as log_file:
                log_file.write(error_msg + "\n")
                
            return None
    
    def analyze_with_gigachat(self, text_content):
        """Analyze the extracted text with GigaChat."""
        if not GIGACHAT_CREDENTIALS or not GIGACHAT_SCOPE:
            return (
                "Ошибка: Не установлены учетные данные для GigaChat. "
                "Пожалуйста, настройте переменные окружения GIGACHAT_CREDENTIALS и GIGACHAT_SCOPE."
            )
        
        try:
            # Prepare the prompt for GigaChat
            prompt = (
                f"Ты врач, который должен изучить результаты анализов пользователя и сообщить ему "
                f"где и какие результаты отличаются от референсных, с чем это может быть связано "
                f"и на что обратить внимание. Если требуется дополнительное исследование, "
                f"то дать рекомендации к этим исследованиям. Вот данные анализов:\n\n{text_content}\n\n"
                f"Но в конце обязательно добавь, что пользователь не должен заниматься самолечением, "
                f"рекомендации сформированы искусственным интеллектом и носят информационный, "
                f"а не рекомендательный характер, и ему следует консультироваться со специалистами."
            )
            
            # Create the chat message
            chat = Chat(
                messages=[
                    Messages(role=MessagesRole.USER, content=prompt)
                ]
            )
            
            # Get response from GigaChat
            response = giga.chat(chat)
            
            # Format the response with emojis and formatting
            formatted_response = self.format_gigachat_response(response.choices[0].message.content)

            return formatted_response
            
        except Exception as e:
            logger.error(f"Error calling GigaChat: {e}")
            return (
                "Произошла ошибка при обращении к GigaChat. "
                "Пожалуйста, попробуйте снова позже."
            )
    
    def format_gigachat_response(self, text):
        """Format the GigaChat response with emojis and proper formatting."""
        import re
        
        # Replace markdown headers with emojis
        text = re.sub(r'^##\s+(.*)', r'🔬 **\1**', text, flags=re.MULTILINE)
        text = re.sub(r'^###\s+(.*)', r'💊 \1', text, flags=re.MULTILINE)
        text = re.sub(r'^####\s+(.*)', r'🧪 \1', text, flags=re.MULTILINE)
        
        # Find analysis names (typically followed by numbers/values) and underline them
        # This pattern looks for capitalized words or letter combinations that are likely test names
        text = re.sub(r'([A-Z][A-Za-zА-Яа-яЁё\s\-\(\)]+?)\s*(:\s*[0-9.,\-\s\w\(\)<>≥≤\[\]]+[^\n\r]*(?:\n|$))', r'___\1___\2', text)
        
        # Find the disclaimer text about self-treatment and make it italic
        text = re.sub(
            r'(Самолечение недопустимо[^\n\r.]*[.\n\r]*)',
            r'*\1*',
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        # Look for other variations of the disclaimer
        text = re.sub(
            r'((?:пользователь\s*не\s*должен|не\s*следует\s*заниматься)\s*(?:самолечением|лечением\s*без\s*врача)[^\n\r.]*[.\n\r]*)',
            r'*\1*',
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        return text

    def run_bot(self):
        """Start the bot."""
        application = Application.builder().token(self.bot_token).build()

        # Register handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = MedicalAnalysisBot()
    bot.run_bot()