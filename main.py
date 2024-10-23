from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
import aiohttp
import io
import logging
import asyncio
import ffmpeg
import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext
from pydub import AudioSegment
from pydub.utils import which
import os
import uuid

TOKEN = "7714844616:AAH37iobg77Zwe_cg4_CvN20O32Vi-hrGVU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())


class PronunciationTest(StatesGroup):
    choosing_defect = State()
    sending_word = State()
    waiting_for_audio = State()

WORDS = {
    "burr": ["рыба", "трава", "гора", "рука", "роза"],  
    "fricative": ["солнце", "сыр", "осень", "свет", "сон"] 
}


@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply(
        "Привет! Я помогу тебе улучшить твое произношение.\n\n"
        "Выберите, какой дефект вы хотите исправить:\n"
        "/burr - Ротацизм (картавость)\n"
        "/fricative - Фрикация"
    )
    await PronunciationTest.choosing_defect.set()


@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message):
    await message.reply(
        "Команды:\n\n"
        "/start - Запуск бота\n"
        "/help - Помощь\n"
        "/burr - Исправление картавости\n"
        "/fricative - Исправление фрикативности"
    )


@dp.message_handler(commands=['burr'], state='*')
async def cmd_burr(message: types.Message, state: FSMContext):
    await state.finish()  
    await state.update_data(defect='burr', word_index=0)
    word = WORDS['burr'][0]
    await message.reply(f"Произнесите слово: {word}")
    await PronunciationTest.waiting_for_audio.set()


@dp.message_handler(commands=['fricative'], state='*')
async def cmd_fricative(message: types.Message, state: FSMContext):
    await state.finish() 
    await state.update_data(defect='fricative', word_index=0)
    word = WORDS['fricative'][0]
    await message.reply(f"Произнесите слово: {word}")
    await PronunciationTest.waiting_for_audio.set()



@dp.message_handler(content_types=types.ContentType.VOICE, state=PronunciationTest.waiting_for_audio)
async def handle_voice_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    defect = data.get('defect')
    word_index = data.get('word_index', 0)
    words_list = WORDS.get(defect, [])
    current_word = words_list[word_index]

    processing_message = await message.reply("Обрабатываю ваше сообщение, подождите...")
    voice_file = await message.voice.get_file()
    voice_bytes_io = io.BytesIO()
    await bot.download_file(voice_file.file_path, voice_bytes_io)
    voice_bytes_io.seek(0)

    try:
        unique_id = uuid.uuid4().hex
        ogg_filename = f"voice_{unique_id}.ogg"
        mp3_filename = f"voice_{unique_id}.mp3"

        with open(ogg_filename, 'wb') as ogg_file:
            ogg_file.write(voice_bytes_io.read())

        loop = asyncio.get_running_loop()
        await asyncio.to_thread(
            ffmpeg.input(ogg_filename).output(mp3_filename).run, overwrite_output=True
        )

        if not os.path.exists(mp3_filename) or os.path.getsize(mp3_filename) == 0:
            logging.error("MP3 файл не создан или пустой")
            await processing_message.delete()
            await message.reply("Произошла ошибка при обработке аудио файла. Попробуйте еще раз.")
            return

        with open(mp3_filename, 'rb') as mp3_file:
            api_url = "https://yufii-speech-defects.hf.space/process-audio"
            form = aiohttp.FormData()
            form.add_field('phrase', current_word)
            form.add_field('audio', mp3_file, filename='audio.mp3', content_type='audio/mpeg')

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, data=form) as resp:
                    response_text = await resp.text()
                    await processing_message.delete()
                    if resp.status == 200:
                        api_response = await resp.json()
                        prediction = api_response.get('prediction', [])
                        match_phrase = api_response.get('match_phrase', False)
                        if match_phrase and sum(prediction[0]) > 0.5:
                            word_index += 1
                            if word_index < len(words_list):
                                await state.update_data(word_index=word_index)
                                next_word = words_list[word_index]
                                await message.reply(f"Отлично! Теперь произнесите слово: {next_word}")
                            else:
                                await message.reply("Поздравляю! Вы успешно прошли все слова.")
                                await state.finish()
                        else:
                            await message.reply(f"Попробуйте еще раз произнести слово: {current_word}")
                    else:
                        logging.error(f"Ошибка при отправке API запроса: {resp.status}, {response_text}")
                        await message.reply(f"Произошла ошибка при обработке вашего аудио. Сервер вернул {resp.status}")
    except Exception as e:
        logging.exception("Произошла непредвиденная ошибка при обработке аудио сообщения:", exc_info=e)
        await processing_message.delete()
        await message.reply("Произошла непредвиденная ошибка. Попробуйте еще раз.")
    finally:
        if os.path.exists(ogg_filename):
            os.remove(ogg_filename)
        if os.path.exists(mp3_filename):
            os.remove(mp3_filename)



            
@dp.message_handler(state=PronunciationTest.waiting_for_audio)
async def handle_unexpected_text(message: types.Message):
    await message.reply("Пожалуйста, отправьте аудио сообщение с произношением слова.")


def main():
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()