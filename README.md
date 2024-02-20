![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
[![Vkontakte](https://img.shields.io/badge/-Vkontakte-284CEB?style=for-the-badge&logo=Vk)](https://vk.com/web.step)


# Quiz bots 🤔

Боты проведения викторин исторического музея в мессенджере Telegram и социальной сети ВКонтакте.

## Установка.
- Python3 (версия Python 3.10) должен быть уже установлен.
- Рекомендуется использовать среду окружения [venv](https://docs.python.org/3/library/venv.html) 
для изоляции проекта.
 - Используйте `pip` (или `pip3`, если есть конфликт с Python2) для установки зависимостей
```console
$ pip install -r requirements.txt
```


### Переменные окружения

Часть настроек проекта берётся из переменных окружения. Чтобы их определить, создайте файл `.env` и запишите туда данные в таком формате: `ПЕРЕМЕННАЯ=значение`.

- `TELEGRAM_BOT_TOKEN` - Токен ключ телеграм бота
- `VK_COMMUNITY_TOKEN` - токен группы в контакте

опционально:
- `REDIS_HOST` - хост базы redis, по умолчанию `0.0.0.0`
- `REDIS_PORT` - порт базы redis, по умолчанию `6379`
- `REDIS_TIMEOUT` - максимальное время в миллисекундах, в течение которого разрешено выполнение поискового запроса, по умолчанию `2`
- `REDIS_RETRY` - стратегией Backoff c максимальным количеством повторов, по умолчанию `3`


## Запуск

```console
$ python3 quiz_tel_bot.py
```
```console
$ python3 quiz_vk_bot.py
```


## Работающие боты
[VK](https://vk.com/public223195342) и [Telegram](https://t.me/historical_museum_quiz_bot)

## Пример работы бота
![](video_example_work.gif)

## Цели проекта

Код написан в учебных целях — это **Урок 4. Проводим викторину** на курсе по Python [Devman](https://dvmn.org).


<img src="https://dvmn.org/assets/img/logo.8d8f24edbb5f.svg" alt= “” width="102" height="25">
