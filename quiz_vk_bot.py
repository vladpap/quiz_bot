import json
import logging
from enum import Enum

import redis
import vk_api as vk
from environs import Env
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkEventType, VkLongPoll
from vk_api.utils import get_random_id

from quiz.quiz import random_question

logging.basicConfig(
    level=logging.INFO,
    filename='vk_bot.log', filemode='w',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


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


def get_user_from_base(user_id):
    client = Singleton.get_connection()

    if not client.exists(user_id):
        client.set(user_id, json.dumps({'score': 0, 'question_hashs': []}))

    return json.loads(client.get(user_id))


def save_user_from_base(user_id, user_base_data):
    client = Singleton.get_connection()
    client.set(user_id, json.dumps(user_base_data))


def del_task_user_from_base(user_id):
    user_base_data = get_user_from_base(user_id)
    if 'task' in user_base_data.keys():
        del user_base_data['task']
        save_user_from_base(user_id, user_base_data)


def is_task_in_base(user_id) -> bool:
    return 'task' in get_user_from_base(user_id).keys()


class ButtonChat(Enum):
    New_question = 'Новый вопрос ❓'
    Surrender = 'Сдаться 🤷‍♂️'
    Score = 'Мой счет 🥇'


def keyboard_new_question():
    keyboard = VkKeyboard(one_time=True)

    keyboard.add_button(
        ButtonChat.New_question.value,
        color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(
        ButtonChat.Score.value,
        color=VkKeyboardColor.SECONDARY)

    return keyboard.get_keyboard()


def keyboard_answer_attempts():
    keyboard = VkKeyboard(one_time=True)

    keyboard.add_button(
        ButtonChat.Score.value,
        color=VkKeyboardColor.SECONDARY)
    keyboard.add_button(
        ButtonChat.Surrender.value,
        color=VkKeyboardColor.SECONDARY)

    return keyboard.get_keyboard()


def start(vk_api, event):
    vk_api.messages.send(
        user_id=event.user_id,
        message=f'Приветствую.\n'
                f'Нажми "{ButtonChat.New_question.value}" '
                f'для начала викторины.\n',
        random_id=get_random_id(),
        keyboard=keyboard_new_question(),)


def cancel(vk_api, event):
    user_id = event.user_id

    if is_task_in_base(user_id):
        del_task_user_from_base(user_id)

    vk_api.messages.send(
        user_id=event.user_id,
        message='Всего хорошего.\n'
                'Для начала викторины введите команду start',
        random_id=get_random_id())


def new_question_request(vk_api, event, keyboard):
    user_id = event.user_id
    user_from_base = get_user_from_base(user_id)

    while True:
        question_and_answer = random_question()
        question_hash = hash(question_and_answer['question'])
        if 'question_hashs' not in user_from_base:
            user_from_base['question_hashs'] = []
        if question_hash in user_from_base['question_hashs']:
            continue

        vk_api.messages.send(
            user_id=user_id,
            message=f'Вопрос:\n{question_and_answer["question"]}',
            random_id=get_random_id(),
            keyboard=keyboard)

        user_from_base['task'] = question_and_answer
        user_from_base['task']['count_answer'] = 0
        user_from_base['question_hashs'].append(question_hash)
        save_user_from_base(user_id, user_from_base)
        return


def solution_attempt(vk_api, event):
    user_id = event.user_id
    user_from_base = get_user_from_base(user_id)
    text = event.text
    if text.lower() == user_from_base["task"]["answer"]:
        user_from_base["score"] += 1
        question_hash = hash(user_from_base['task']['question'])
        user_from_base['question_hashs'].append(question_hash)
        del user_from_base['task']
        save_user_from_base(user_id, user_from_base)

        vk_api.messages.send(
            user_id=user_id,
            message=f'Правильно! 🥳 Поздравляю!\n'
                    f'Для следующего вопроса нажми'
                    f' «{ButtonChat.New_question.value}»\n'
                    f'cancel - для отмены',
            random_id=get_random_id(),
            keyboard=keyboard_new_question())

        return True
    else:
        user_from_base['task']['count_answer'] += 1
        save_user_from_base(user_id, user_from_base)
        reply = 'Неправильно… 😪 Попробуешь ещё раз?'

        if user_from_base['task']['count_answer'] > 3:
            reply += '\nМожно сдаться.'

        vk_api.messages.send(
            user_id=user_id,
            message=reply,
            random_id=get_random_id(),
            keyboard=keyboard_answer_attempts())
    return False


def surrender_request(vk_api, event):
    user_id = event.user_id
    user_from_base = get_user_from_base(user_id)

    vk_api.messages.send(
        user_id=user_id,
        message=f'Правильный ответ 🫣:\n'
                f'{user_from_base["task"]["answer"]}\n\n',
        random_id=get_random_id())

    new_question_request(
        vk_api, event, keyboard_answer_attempts())


def score_request(vk_api, event, keyboard):
    user_id = event.user_id
    user_base_data = get_user_from_base(user_id)
    vk_api.messages.send(
            user_id=user_id,
            message=f'Ваш счет:\n{user_base_data["score"]} баллов.',
            random_id=get_random_id(),
            keyboard=keyboard)


def main():
    env = Env()
    env.read_env()

    token_vk_bot = env.str('VK_COMMUNITY_TOKEN')
    vk_session = vk.VkApi(token=token_vk_bot)
    vk_api = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    is_new_question = True

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            if is_new_question:
                match event.text:

                    case 'start':
                        start(vk_api, event)

                    case 'cancel':
                        is_new_question = True
                        cancel(vk_api, event)

                    case ButtonChat.New_question.value:
                        is_new_question = False
                        new_question_request(
                            vk_api, event, keyboard_answer_attempts())

                    case ButtonChat.Score.value:
                        score_request(
                            vk_api, event, keyboard_new_question())

                    case _:
                        vk_api.messages.send(
                            user_id=event.user_id,
                            message=f'Нажми "{ButtonChat.New_question.value}"'
                                    f' для начала викторины.\n',
                            random_id=get_random_id(),
                            keyboard=keyboard_new_question())
            else:
                match event.text:

                    case 'cancel':
                        is_new_question = True
                        cancel(vk_api, event)

                    case ButtonChat.Surrender.value:
                        surrender_request(vk_api, event)

                    case ButtonChat.Score.value:
                        score_request(
                            vk_api, event, keyboard_answer_attempts())

                    case _:
                        is_new_question = solution_attempt(
                            vk_api, event)


if __name__ == "__main__":
    main()
