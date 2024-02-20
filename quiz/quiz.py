from os import scandir
from random import choice


def get_questions_and_answer_from_file(file_name: str = '') -> list:
    filenames_from_folder = []
    if not file_name:
        with scandir('./questions') as entries:
            for entry in entries:
                if entry.is_file():
                    filenames_from_folder.append(entry.name)
        file_name = f'./questions/{choice(filenames_from_folder)}'

    with open(file_name, "r", encoding="KOI8-R") as my_file:
        file_content_list = my_file.read().split('\n\n')

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


def random_question() -> dict:
    return choice(get_questions_and_answer_from_file())


if __name__ == '__main__':
    pass
