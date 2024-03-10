import json
import logging
from enum import Enum
from random import choice

import redis
import vk_api as vk
from environs import Env
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkEventType, VkLongPoll
from vk_api.utils import get_random_id

from quiz.quiz import get_random_questions

logger = logging.getLogger(__file__)


class ButtonChat(Enum):
    New_question = 'Новый вопрос ❓'
    Surrender = 'Сдаться 🤷‍♂️'
    Score = 'Мой счет 🥇'


def keyboard_new_question():
    keyboard = VkKeyboard(one_time=True)

    keyboard.add_button(
        ButtonChat.New_question.value, color=VkKeyboardColor.SECONDARY
    )
    keyboard.add_button(
        ButtonChat.Score.value, color=VkKeyboardColor.SECONDARY
    )

    return keyboard.get_keyboard()


def keyboard_answer_attempts():
    keyboard = VkKeyboard(one_time=True)

    keyboard.add_button(
        ButtonChat.Score.value, color=VkKeyboardColor.SECONDARY
    )
    keyboard.add_button(
        ButtonChat.Surrender.value, color=VkKeyboardColor.SECONDARY
    )

    return keyboard.get_keyboard()


def start(redis_db, vk_api, event):
    user_id = event.user_id
    if not redis_db.exists(user_id):
        redis_db.set(user_id, json.dumps({'score': 0}))

    if 'task' in json.loads(redis_db.get(user_id)).keys():
        return

    vk_api.messages.send(
        user_id=user_id,
        message=f'Приветствую.\n'
        f'Нажми {ButtonChat.New_question.value} '
        f'для начала викторины.\n',
        random_id=get_random_id(),
        keyboard=keyboard_new_question(),
    )


def cancel(redis_db, vk_api, event):
    user_id = event.user_id
    user_from_base = json.loads(redis_db.get(user_id))

    if 'task' in user_from_base.keys():
        del user_from_base['task']
        redis_db.set(user_id, json.dumps(user_from_base))

    vk_api.messages.send(
        user_id=event.user_id,
        message='Всего хорошего.\n'
        'Для начала викторины введите команду start',
        random_id=get_random_id(),
    )


def handle_new_question_request(
    redis_db, random_questions, vk_api, event, keyboard
):
    user_id = event.user_id
    user_from_base = json.loads(redis_db.get(user_id))

    if 'task' in json.loads(redis_db.get(user_id)).keys():
        return

    question_and_answer = choice(random_questions)

    vk_api.messages.send(
        user_id=user_id,
        message=f'Вопрос:\n{question_and_answer["question"]}',
        random_id=get_random_id(),
        keyboard=keyboard,
    )

    user_from_base['task'] = question_and_answer
    user_from_base['task']['count_answer'] = 0
    redis_db.set(user_id, json.dumps(user_from_base))
    return


def solution_attempt(redis_db, vk_api, event):
    user_id = event.user_id
    user_from_base = json.loads(redis_db.get(user_id))
    text = event.text
    if text.lower() == user_from_base['task']['answer']:
        user_from_base['score'] += 1
        del user_from_base['task']
        redis_db.set(user_id, json.dumps(user_from_base))

        vk_api.messages.send(
            user_id=user_id,
            message=f'Правильно! 🥳 Поздравляю!\n'
            f'Для следующего вопроса нажми'
            f' «{ButtonChat.New_question.value}»\n'
            f'cancel - для отмены',
            random_id=get_random_id(),
            keyboard=keyboard_new_question(),
        )

    else:
        user_from_base['task']['count_answer'] += 1
        redis_db.set(user_id, json.dumps(user_from_base))
        reply = 'Неправильно… 😪 Попробуешь ещё раз?'

        if user_from_base['task']['count_answer'] > 3:
            reply += '\nМожно сдаться.'

        vk_api.messages.send(
            user_id=user_id,
            message=reply,
            random_id=get_random_id(),
            keyboard=keyboard_answer_attempts(),
        )


def handle_surrender_request(redis_db, random_questions, vk_api, event):
    user_id = event.user_id
    user_from_base = json.loads(redis_db.get(user_id))
    if 'task' not in json.loads(redis_db.get(user_id)).keys():
        return
    vk_api.messages.send(
        user_id=user_id,
        message=f'Правильный ответ 🫣:\n'
        f'{user_from_base["task"]["answer"]}\n\n',
        random_id=get_random_id(),
    )
    del user_from_base['task']
    redis_db.set(user_id, json.dumps(user_from_base))

    handle_new_question_request(
        redis_db, random_questions, vk_api, event, keyboard_answer_attempts()
    )


def handle_score_request(redis_db, vk_api, event):
    user_id = event.user_id
    user_base_data = json.loads(redis_db.get(user_id))
    keyboard = keyboard_new_question()
    if 'task' in json.loads(redis_db.get(user_id)).keys():
        keyboard = keyboard_answer_attempts()
    vk_api.messages.send(
        user_id=user_id,
        message=f'Ваш счет:\n{user_base_data["score"]} баллов.',
        random_id=get_random_id(),
        keyboard=keyboard,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        filename='vk_bot.log',
        filemode='w',
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    env = Env()
    env.read_env()

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

    token_vk_bot = env.str('VK_COMMUNITY_TOKEN')
    vk_session = vk.VkApi(token=token_vk_bot)
    vk_api = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    for event in longpoll.listen():
        if not event.to_me:
            continue
        if event.type != VkEventType.MESSAGE_NEW:
            continue

        if event.text == 'start':
            start(redis_db, vk_api, event)

        elif event.text == 'cancel':
            cancel(redis_db, vk_api, event)

        elif event.text == ButtonChat.New_question.value:
            handle_new_question_request(
                redis_db,
                random_questions,
                vk_api,
                event,
                keyboard_answer_attempts(),
            )

        elif event.text == ButtonChat.Score.value:
            handle_score_request(
                redis_db, vk_api, event)
        elif event.text == ButtonChat.Surrender.value:
            handle_surrender_request(redis_db, random_questions, vk_api, event)

        else:
            if 'task' not in json.loads(redis_db.get(event.user_id)).keys():
                vk_api.messages.send(
                    user_id=event.user_id,
                    message=f'Нажми {ButtonChat.New_question.value}'
                    f' для начала викторины.\n',
                    random_id=get_random_id(),
                    keyboard=keyboard_new_question(),
                )
            else:
                solution_attempt(redis_db, vk_api, event)


if __name__ == '__main__':
    main()
