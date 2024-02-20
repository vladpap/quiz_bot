import json
import logging
from enum import Enum

import redis
from environs import Env
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (ApplicationBuilder, CommandHandler,
                          ConversationHandler, MessageHandler, filters)

from quiz.quiz import random_question

logging.basicConfig(
    level=logging.INFO,
    filename='tel_bot.log', filemode='w',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# logging.getLogger('httpx').setLevel(logging.WARNING)


class ButtonChat(Enum):
    New_question = 'Новый вопрос ❓'
    Surrender = 'Сдаться 🤷‍♂️'
    Score = 'Мой счет 🥇'


REPLY_KEYBOARD_NEW_QUESTION = [[
    ButtonChat.New_question.value, ButtonChat.Score.value]]

REPLY_KEYBOARD_ANSWER_ATTEMPTS = [[
    ButtonChat.Score.value, ButtonChat.Surrender.value]]


State = Enum('State', 'NEW_QUESTION ANSWER_ATTEMPTS')


class Singleton:
    _instance = None

    @staticmethod
    def get_connection():
        if not Singleton._instance:
            env = Env()
            env.read_env()
            Singleton._instance = redis.client.Redis(
                decode_responses=True,
                host=env.str('REDIS_HOST', default='0.0.0.0'),
                port=env.int('REDIS_PORT', default=6379),
                socket_timeout=env.int('REDIS_TIMEOUT', default=2),
                retry=redis.retry.Retry(
                    redis.backoff.ExponentialBackoff(),
                    env.int('REDIS_RETRY', default=3)),
                retry_on_error=[BusyLoadingError,
                                ConnectionError,
                                TimeoutError]
            )
        return Singleton._instance


def get_user_from_base(chat_id):
    client = Singleton.get_connection()
    return json.loads(client.get(chat_id))


def save_user_from_base(chat_id, user_base_data):
    client = Singleton.get_connection()
    client.set(chat_id, json.dumps(user_base_data))


def del_task_user_from_base(chat_id):
    user_base_data = get_user_from_base(chat_id)
    if 'task' in user_base_data.keys():
        del user_base_data['task']
        save_user_from_base(chat_id, user_base_data)


def is_task_in_base(chat_id) -> bool:
    return 'task' in get_user_from_base(chat_id).keys()


async def start(update: Update, context):
    client = Singleton.get_connection()
    chat_id = update.effective_chat.id
    if not client.exists(chat_id):
        client.set(chat_id, json.dumps({'score': 0, 'question_hashs': []}))

    reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION

    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder="Ваш выбор ...")

    await update.effective_message.reply_text(
            f'Приветствую.\n'
            f'Нажми "{ButtonChat.New_question.value}" для начала викторины.\n'
            f'/cancel - для отмены',
            reply_markup=reply_markup)

    return State.NEW_QUESTION


async def cancel(update: Update, context):
    chat_id = update.effective_chat.id

    if is_task_in_base(chat_id):
        del_task_user_from_base(chat_id)

    reply_markup = ReplyKeyboardRemove()

    await update.effective_message.reply_text(
            'Всего хорошего.\n'
            'Для начала викторины введите команду /start',
            reply_markup=reply_markup)

    return ConversationHandler.END


async def handle_new_question_request(update: Update, context):
    chat_id = update.effective_chat.id
    user_from_base = get_user_from_base(chat_id)

    reply_keyboard = REPLY_KEYBOARD_ANSWER_ATTEMPTS
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder="Ваш ответ ...")

    while True:
        question_and_answer = random_question()
        question_hash = hash(question_and_answer['question'])
        if question_hash in user_from_base['question_hashs']:
            continue

        await update.effective_message.reply_text(
                f'Вопрос:\n'
                f'{question_and_answer["question"]}',
                reply_markup=reply_markup)

        user_from_base['task'] = question_and_answer
        user_from_base['task']['count_answer'] = 0
        user_from_base['question_hashs'].append(question_hash)
        save_user_from_base(chat_id, user_from_base)
        return State.ANSWER_ATTEMPTS


async def handle_surrender_request(update: Update, context):
    chat_id = update.effective_chat.id
    user_base_data = get_user_from_base(chat_id)

    reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard,
        resize_keyboard=True,
        input_field_placeholder="Ваш выбор ...")

    await update.effective_message.reply_text(
            f'Правильный ответ 🫣:\n'
            f'{user_base_data["task"]["answer"]}\n\n',
            reply_markup=reply_markup)

    await handle_new_question_request(update=update, context=context)


async def handle_score_request(update: Update, context):
    user_base_data = get_user_from_base(update.effective_chat.id)
    reply = f'Ваш счет:\n{user_base_data["score"]} баллов.'

    await update.effective_message.reply_text(reply)


async def handle_solution_attempt(update: Update, context):
    chat_id = update.effective_chat.id
    user_base_data = get_user_from_base(chat_id)
    text = update.effective_message.text
    if text.lower() == user_base_data["task"]["answer"]:
        user_base_data["score"] += 1
        question_hash = hash(user_base_data['task']['question'])
        user_base_data['question_hashs'].append(question_hash)
        del user_base_data['task']
        save_user_from_base(chat_id, user_base_data)

        reply_keyboard = REPLY_KEYBOARD_NEW_QUESTION
        reply_markup = ReplyKeyboardMarkup(
            reply_keyboard,
            resize_keyboard=True,
            input_field_placeholder="Ваш выбор ...")

        await update.effective_message.reply_text(
            f'Правильно! 🥳 Поздравляю!\n'
            f'Для следующего вопроса нажми «{ButtonChat.New_question.value}»\n'
            f'/cancel - для отмены',
            reply_markup=reply_markup)

        return State.NEW_QUESTION
    else:
        user_base_data['task']['count_answer'] += 1
        save_user_from_base(chat_id, user_base_data)
        reply = 'Неправильно… 😪 Попробуешь ещё раз?'

        if user_base_data['task']['count_answer'] > 3:
            reply += '\nМожно сдаться.'
        await update.effective_message.reply_text(reply)
    return State.ANSWER_ATTEMPTS


def main():
    env = Env()
    env.read_env()

    token_tel_bot = env.str('TELEGRAM_BOT_TOKEN')

    application = ApplicationBuilder().token(token_tel_bot).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],

        states={
            State.NEW_QUESTION: [
                MessageHandler(
                    filters.Regex(ButtonChat.New_question.value),
                    handle_new_question_request),
                MessageHandler(
                    filters.Regex(ButtonChat.Score.value),
                    handle_score_request),
                CommandHandler('cancel', cancel)],

            State.ANSWER_ATTEMPTS: [
                MessageHandler(
                    filters.Regex(ButtonChat.Surrender.value),
                    handle_surrender_request),
                MessageHandler(
                    filters.Regex(ButtonChat.Score.value),
                    handle_score_request),
                CommandHandler('cancel', cancel),
                MessageHandler(
                    filters.TEXT,
                    handle_solution_attempt)],

        },

        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == '__main__':
    main()
