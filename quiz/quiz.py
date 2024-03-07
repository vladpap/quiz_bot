from os import scandir
from random import choice


def get_random_questions(folder='./questions', file_name='') -> list:

    filenames_from_folder = []
    if not file_name:
        with scandir(folder) as entries:
            for entry in entries:
                if entry.is_file():
                    filenames_from_folder.append(entry.name)
        file_name = f'{folder}/{choice(filenames_from_folder)}'

    with open(file_name, "r", encoding="KOI8-R") as quiz_file:
        file_content_list = quiz_file.read().split('\n\n')

    questions_and_answers = []
    is_find_question, is_find_answer = False, False
    question, answer = '', ''

    for item in file_content_list:
        item = item.strip('\n')
        if item.find('Вопрос') != -1:
            question = item[item.find('\n')+1:]
            is_find_question = True
        elif item.find('Ответ') != -1:
            answer = item[item.find('\n')+1:]
            is_find_answer = True

        if is_find_question and is_find_answer:
            if answer.find('.') != -1:
                answer = answer[:answer.find('.')]
            if answer.find('(') != -1:
                answer = answer[:answer.find('(')]
            correct_answer = answer.lower().strip().replace('"', '')
            questions_and_answers.append(
                {'question': question.replace('\n', ''),
                 'answer': correct_answer})
            is_find_question, is_find_answer = False, False

    return questions_and_answers
