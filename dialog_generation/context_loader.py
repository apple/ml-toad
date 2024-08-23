#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
import logging
import random
from datetime import datetime, timedelta

from babel.dates import format_timedelta

DATETIME_FORMAT = '%a %Y-%m-%d %H:%M'
DATE_FORMAT = '%a %Y-%m-%d'
TIME_FORMAT = '%H:%M'

CALENDAR_KEY_MAP = {
    'event_name': 'name',
    'location': 'location',
    'attendees': 'attendees',
}
REMINDER_KEY_MAP = {
    'todo': 'name',
    'notes': 'notes',
}
ALARM_KEY_MAP = {
    'time': 'time',
    'name': 'name',
    'recurring': 'if_repeat',
}
MESSAGE_KEY_MAP = {
    'sender': 'contacts',
    'message': 'text',
}


def load_contexts():
    filename = 'data/contexts.jsonl'
    with open(filename, 'r') as fp:
        contexts = [json.loads(line) for line in fp]
    return contexts


def convert_calendar(input_data: list) -> list:
    output_data = []
    for event in input_data:
        converted = {CALENDAR_KEY_MAP[k]: v for k, v in event.items() if k in CALENDAR_KEY_MAP and v}
        try:
            start_time = datetime.strptime(event['start_time'], DATETIME_FORMAT)
            end_time = datetime.strptime(event['end_time'], DATETIME_FORMAT)
            duration = end_time - start_time
            converted['date'] = start_time.strftime(DATE_FORMAT)
            converted['start_time'] = start_time.strftime(TIME_FORMAT)
            converted['duration'] = format_timedelta(duration, locale='en_US')
        except ValueError:
            try:
                start_time = datetime.strptime(event['start_time'], DATE_FORMAT)
                end_time = datetime.strptime(event['end_time'], DATE_FORMAT)
                duration = max(end_time - start_time, timedelta(days=1))
                converted['date'] = start_time.strftime(DATE_FORMAT)
                converted['duration'] = format_timedelta(duration, locale='en_US')
            except ValueError as e:
                logging.warning(f"Discarded invalid event: {repr(e)}")
        output_data.append(converted)
    return output_data


def convert_reminders(input_data: list) -> list:
    output_data = []
    for reminder in input_data:
        converted = {REMINDER_KEY_MAP[k]: v for k, v in reminder.items() if k in REMINDER_KEY_MAP and v}
        if 'trigger_time' in reminder:
            try:
                trigger_time = datetime.strptime(reminder['trigger_time'], DATETIME_FORMAT)
                converted['date'] = trigger_time.strftime(DATE_FORMAT)
                converted['time'] = trigger_time.strftime(TIME_FORMAT)
            except ValueError:
                try:
                    trigger_time = datetime.strptime(reminder['trigger_time'], DATE_FORMAT)
                    converted['date'] = trigger_time.strftime(DATE_FORMAT)
                except ValueError as e:
                    logging.warning(f"Discarded invalid reminder: {repr(e)}")
        output_data.append(converted)
    return output_data


def convert_alarms(input_data: list) -> list:
    output_data = []
    for alarm in input_data:
        converted = {ALARM_KEY_MAP[k]: v for k, v in alarm.items() if k in ALARM_KEY_MAP and v}
        output_data.append(converted)
    return output_data


def convert_messages(input_data: dict) -> dict:
    output_data = {'messages': [], 'messages_sent': []}
    threads = list(input_data.items())
    random.shuffle(threads)
    for contact, thread in threads:
        for message in thread:
            converted = {MESSAGE_KEY_MAP[k]: v for k, v in message.items() if k in MESSAGE_KEY_MAP and v}
            if message['sender'] == 'myself':
                app_name = 'messages_sent'
                converted['contacts'] = contact  # overwrite the contact (which would have been 'myself')
            else:
                app_name = 'messages'
            if isinstance(converted.get('contacts'), str):  # convert contacts to list
                converted['contacts'] = [converted['contacts']]
            output_data[app_name].append(converted)
    return output_data


CONVERTERS = {
    'calendar_events': convert_calendar,
    'reminders': convert_reminders,
    'alarms': convert_alarms,
    'messages': convert_messages,
    'contacts': lambda x: x.copy(),
    'today': lambda x: datetime.strptime(x, '%Y-%m-%d').strftime(DATE_FORMAT),
}


def sample_time(granularity: int = 1, hours: tuple = (0, 24)) -> str:
    hour = random.randrange(*hours)
    minute = random.randrange(60 // granularity) * granularity
    return f"{hour:0>2}:{minute:0>2}"


def convert_context(context: dict) -> dict:
    """ Make a copy of the context, formatted according to the schema.
    """
    result = {}
    for app, app_data in context['apps'].items():
        converter = CONVERTERS.get(app)
        if converter:
            converted_data = converter(app_data)
            if isinstance(converted_data, dict):
                result.update(converted_data)
            else:
                result[app] = converted_data
    result['current_time'] = sample_time()
    result['intro'] = context['intro']
    return result


if __name__ == '__main__':
    for c in load_contexts():
        convert_context(c)
