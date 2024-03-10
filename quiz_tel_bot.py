import json
import logging
from enum import Enum
from functools import partial
from random import choice

import redis
from environs import Env
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from quiz.quiz import get_random_questions

logger = logging.getLogger(__file__)


class ButtonChat(Enum):
    New_question = 'Новый вопрос ❓'
    Surrender = 'Сдаться 🤷‍♂️'
    Score = 'Мой счет 🥇'


REPLY_KEYBOARD_NEW_QUESTION = [
    [ButtonChat.New_question.value, ButtonChat.Score.value]
]

REPLY_KEYBOARD_ANSWER_ATTEMPTS = [
    [ButtonChat.Score.value, ButtonChat.Surrender.value]
]


State = Enum('State', 'NEW_QUESTION ANSWER_ATTEMPTS')


async def start(redis_db, update: Update, context):
    chat_id = update.effective_chat.id
    if not redis_db.exists(chat_id):
        redis_db.set(chat_id, json.dumps({'score': 0}))

    reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION

    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder='Ваш выбор ...',
    )

    await update.effective_message.reply_text(
        f'Приветствую.\n'
        f'Нажми {ButtonChat.New_question.value} для начала викторины.\n'
        f'/cancel - для отмены',
        reply_markup=reply_markup,
    )

    return State.NEW_QUESTION


async def cancel(redis_db, update: Update, context):
    chat_id = update.effective_chat.id

    user_base_data = json.loads(redis_db.get(chat_id))
    if 'task' in user_base_data.keys():
        del user_base_data['task']
        redis_db.set(chat_id, json.dumps(user_base_data))

    reply_markup = ReplyKeyboardRemove()

    await update.effective_message.reply_text(
        'Всего хорошего.\n' 'Для начала викторины введите команду /start',
        reply_markup=reply_markup,
    )

    return ConversationHandler.END


async def handle_new_question_request(
    redis_db, random_questions, update: Update, context
):
    chat_id = update.effective_chat.id
    user_base_data = json.loads(redis_db.get(chat_id))

    reply_keyboard = REPLY_KEYBOARD_ANSWER_ATTEMPTS
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder='Ваш ответ ...',
    )

    question_and_answer = choice(random_questions)

    await update.effective_message.reply_text(
        f'Вопрос:\n' f'{question_and_answer["question"]}',
        reply_markup=reply_markup,
    )

    user_base_data['task'] = question_and_answer
    user_base_data['task']['count_answer'] = 0
    redis_db.set(chat_id, json.dumps(user_base_data))
    return State.ANSWER_ATTEMPTS


async def handle_surrender_request(
    redis_db, random_questions, update: Update, context
):
    chat_id = update.effective_chat.id
    user_base_data = json.loads(redis_db.get(chat_id))

    reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder='Ваш выбор ...',
    )

    await update.effective_message.reply_text(
        f'Правильный ответ 🫣:\n' f'{user_base_data["task"]["answer"]}\n\n',
        reply_markup=reply_markup,
    )

    await handle_new_question_request(
        redis_db, random_questions, update=update, context=context
    )


async def handle_score_request(redis_db, update: Update, context):
    user_base_data = json.loads(redis_db.get(update.effective_chat.id))
    reply = f'Ваш счет:\n{user_base_data["score"]} баллов.'

    await update.effective_message.reply_text(reply)


async def handle_solution_attempt(redis_db, update: Update, context):
    chat_id = update.effective_chat.id
    user_base_data = json.loads(redis_db.get(chat_id))
    text = update.effective_message.text
    if text.lower() == user_base_data['task']['answer']:
        user_base_data['score'] += 1
        del user_base_data['task']
        redis_db.set(chat_id, json.dumps(user_base_data))

        reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION
        reply_markup = ReplyKeyboardMarkup(
            reply_keyboard,
            resize_keyboard=True,
            input_field_placeholder='Ваш выбор ...',
        )

        await update.effective_message.reply_text(
            f'Правильно! 🥳 Поздравляю!\n'
            f'Для следующего вопроса нажми «{ButtonChat.New_question.value}»\n'
            f'/cancel - для отмены',
            reply_markup=reply_markup,
        )

        return State.NEW_QUESTION
    else:
        user_base_data['task']['count_answer'] += 1
        redis_db.set(chat_id, json.dumps(user_base_data))
        reply = 'Неправильно… 😪 Попробуешь ещё раз?'

        if user_base_data['task']['count_answer'] > 3:
            reply += '\nМожно сдаться.'
        await update.effective_message.reply_text(reply)
    return State.ANSWER_ATTEMPTS


def main():
    logging.basicConfig(
        level=logging.INFO,
        filename='tel_bot.log',
        filemode='w',
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    env = Env()
    env.read_env()

    token_tel_bot = env.str('TELEGRAM_BOT_TOKEN')
    quiz_files_folder = env.str('QUIZ_FOLDER', default=None)
    quiz_file_name = env.str('QUIZ_FILE', default=None)

    redis_db = redis.client.Redis(
        decode_responses=True,
        host=env.str('REDIS_HOST', default='0.0.0.0'),
        port=env.int('REDIS_PORT', default=6379),
        socket_timeout=env.int('REDIS_TIMEOUT', default=2),
        retry=redis.retry.Retry(
            redis.backoff.ExponentialBackoff(),
            env.int('REDIS_RETRY', default=3),
        ),
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
    )

    random_questions = get_random_questions(
        folder=quiz_files_folder, file_name=quiz_file_name
    )
    application = ApplicationBuilder().token(token_tel_bot).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', partial(start, redis_db))],
        states={
            State.NEW_QUESTION: [
                MessageHandler(
                    filters.Regex(ButtonChat.New_question.value),
                    partial(
                        handle_new_question_request, redis_db, random_questions
                    ),
                ),
                MessageHandler(
                    filters.Regex(ButtonChat.Score.value),
                    partial(handle_score_request, redis_db),
                ),
                CommandHandler('cancel', partial(cancel, redis_db)),
            ],
            State.ANSWER_ATTEMPTS: [
                MessageHandler(
                    filters.Regex(ButtonChat.Surrender.value),
                    partial(
                        handle_surrender_request, redis_db, random_questions
                    ),
                ),
                MessageHandler(
                    filters.Regex(ButtonChat.Score.value), handle_score_request
                ),
                CommandHandler('cancel', cancel),
                MessageHandler(
                    filters.TEXT, partial(handle_solution_attempt, redis_db)
                ),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == '__main__':
    main()
