#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
import multiprocessing.dummy
import random
from datetime import date, timedelta
from textwrap import dedent
from typing import List

from utilities.llm_synthesis_utils import call_openai_chat_completion
from .persona_generator import PERSONAS_FILE, get_pronoun

CONTEXTS_FILE = "data/contexts.jsonl"

DATE_FORMAT = "%a %Y-%m-%d"


def load_personas():
    personas = []
    with open(PERSONAS_FILE, 'r') as fp:
        for line in fp:
            persona = json.loads(line)
            personas.append(persona)
    return personas


def simulated_app(input_apps: List[str], output_apps: List[str]):
    def decorator(function):
        def wrapper(persona, *args, **kwargs):
            if 'apps' not in persona:
                persona['apps'] = {}
            elif any(app in persona['apps'] for app in output_apps):
                print(f"Data already exists for {', '.join(output_apps)}")
                return
            if any(app not in persona['apps'] for app in input_apps):
                print(f"Cannot generate data for {', '.join(output_apps)}: Required input data doesn't exist")
                return
            try:
                app_data = function(persona, *args, **kwargs)
            except Exception as e:
                print(f"Failed to generate data for {', '.join(output_apps)}: {repr(e)}")
                return
            if isinstance(app_data, tuple):
                assert len(app_data) == len(output_apps)
                for data, app in zip(app_data, output_apps):
                    persona['apps'][app] = data
            else:
                assert len(output_apps) == 1
                persona['apps'][output_apps[0]] = app_data
        return wrapper
    return decorator


def parse_llm_json_list(llm_output):
    items = json.loads(llm_output)
    if isinstance(items, dict):
        assert len(items) == 1, f"Dict should only have 1 item but got {len(items)}: {items}"
        items = list(items.values())[0]
    assert isinstance(items, list), f"List is of unexpected type {type(items)}: {items}"
    return items


@simulated_app([], ['today', 'projects'])
def generate_seed_data(persona, num_projects: int = 3):
    today = date(2023, 7, 1) + timedelta(days=random.randrange(365 * 5))
    persona['apps'] = {'today': today}
    occupation = persona['occupation']
    if occupation == 'Unemployed or retired':
        return today, []
    data = []
    affiliation = ''
    if 'affiliation' in persona:
        data.append("Organization: " + json.dumps(persona['affiliation'], ensure_ascii=False))
        affiliation = ' at this organization'
    elif 'school' in persona:
        data.append("Institution: " + json.dumps(persona['school'], ensure_ascii=False))
        affiliation = ' at this institution'
    if occupation == 'Student':
        prompt = f"Today is {today}. Imagine the work of a current {occupation}{affiliation} in {persona['address']}, and write a JSON list of {num_projects} current projects, courses, or other work items. Each item should contain a \"name\" and a \"description\" (single sentence)."
    else:
        suffix = random.choice(['', ' (can use codenames)'])
        prompt = f"Today is {today}. Imagine the work of a current {occupation}{affiliation} in {persona['address']}, and write a JSON list of {num_projects} current projects{suffix}, products, or other work items. Each item should contain a \"name\" and a \"description\" (single sentence)."
    data.append(prompt)
    messages = [
        {"role": "user", "content": "\n\n".join(data)}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    projects = parse_llm_json_list(llm_output)
    return today, projects


@simulated_app([], ['contacts'])
def generate_contacts(persona, num_contacts: int = 20):
    prompt = dedent(f"""
    Write a JSON list of {num_contacts} possible contacts stored in this person's mobile phone, such as family members, friends, colleagues and businesses. Each contact can contain these attributes: "relationship" (optional) and "full_name".
    """).strip()
    messages = [
        {"role": "user", "content": "\n\n".join([persona['intro'], prompt])}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    contacts = parse_llm_json_list(llm_output)
    return contacts


@simulated_app([], ['alarms'])
def generate_alarms(persona):
    num_alarms = random.randint(2, 5)
    prompt = dedent(f"""
    Write a JSON list of {num_alarms} alarms set on this person's mobile phone. Each alarm should consist of these attributes:
    * "time" (format as "%H:%M")
    * "name" (optional field)
    * "recurring" (boolean, false for one-time alarms)
    """).strip()
    messages = [
        {"role": "user", "content": "\n\n".join([persona['intro'], prompt])}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    contacts = parse_llm_json_list(llm_output)
    return contacts


def format_contacts(contacts) -> str:
    return ", ".join(c['full_name'] + (f" ({c['relationship']})" if c.get('relationship') else "") for c in contacts)


def format_personal_data(persona):
    data = [persona['intro']]
    if 'affiliation' in persona:
        data.append(f"This person works at {persona['affiliation']['name']}. ({persona['affiliation']['description']})")
    elif 'school' in persona:
        data.append(f"This person studies at {persona['school']['name']}. ({persona['school']['description']})")
    if persona['apps'].get('projects'):
        project = random.choice(persona['apps']['projects'])
        data.append(f"This person is currently spending time on {project['name']}. ({project['description']})")
    contacts_info = "This person has these contacts: " + format_contacts(
        random.sample(persona['apps']['contacts'], k=10)) + "."
    data.append(contacts_info)
    return data


@simulated_app(['today', 'contacts'], ['calendar_events'])
def generate_calendar_events(persona, min_num: int = 4, max_num: int = 9):
    today = persona['apps']['today']
    start_date = today.strftime(DATE_FORMAT)
    end_date = (today + timedelta(days=random.choice([3, 6, 13]))).strftime(DATE_FORMAT)
    num_events = random.randint(min_num, max_num)
    prompt = dedent(f"""
    Today is {start_date}. Write a JSON list of {num_events} events on this person's calendar between today and {end_date}. At least one event must be an all-day event. At least one event must be a repeated event. Each event should contain these fields:
    * "calendar_name" (e.g. "personal", "work", etc.)
    * "event_name"
    * "all_day" (boolean)
    * "repeated" (boolean)
    * "start_time" (formatted as "{DATE_FORMAT} %H:%M")
    * "end_time" (formatted as "{DATE_FORMAT} %H:%M")
    * "host" (either "myself" or a contact who created this event)
    * "attendees" (optional list of people who have accepted the invite)
    * "location" (optional field)
    """).strip()
    data = format_personal_data(persona)
    data.append(prompt)
    messages = [
        {"role": "user", "content": "\n\n".join(data)}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    calendar_events = parse_llm_json_list(llm_output)
    return calendar_events


@simulated_app(['today', 'contacts'], ['reminders'])
def generate_reminders(persona, min_num: int = 4, max_num: int = 9):
    today = persona['apps']['today']
    start_date = today.strftime(DATE_FORMAT)
    num_reminders = random.randint(min_num, max_num)
    prompt = dedent(f"""
    Today is {start_date}. Write a JSON list of {num_reminders} upcoming reminders on this person's to-do list. A reminder can have these fields:
    * "todo"
    * "notes" (optional details)
    * "trigger_time" (you will be reminded at this time, formatted as "{DATE_FORMAT} %H:%M")
    * "trigger_location" (you will be reminded when you enter this location; should be a street address)
    All fields are optional except for "todo"; most reminders don't have "notes"; most reminders only have one of "trigger_time" and "trigger_location" but not both.
    """).strip()
    data = format_personal_data(persona)
    data.append(prompt)
    messages = [
        {"role": "user", "content": "\n\n".join(data)}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    reminders = parse_llm_json_list(llm_output)
    return reminders


@simulated_app(['contacts'], ['messages'])
def generate_messages(persona):
    num_long_threads = random.randint(0, 3)
    num_short_threads = random.randint(0, 3) + (3 - num_long_threads)
    sampled_contacts = random.sample(persona['apps']['contacts'], k=num_long_threads + num_short_threads)
    long_contacts, short_contacts = sampled_contacts[:num_long_threads], sampled_contacts[num_long_threads:]
    # generate received single messages
    prompt = dedent(f"""
    Fictionalize one SMS message received by this person from each of the following contacts: {format_contacts(short_contacts)}. Write a JSON list where each element consists of these attributes: "sender" and "message".
    """).strip()
    messages = [
        {"role": "user", "content": "\n\n".join([persona['intro'], prompt])}
    ]
    llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
    sms_list = parse_llm_json_list(llm_output)
    sms_threads = {obj['sender']: [obj] for obj in sms_list}
    # generate long threads
    for contact in long_contacts:
        num_turns = random.randint(2, 6)
        first_turn = random.choice([f"this person {get_pronoun(persona['gender'], 'ref')}", contact['full_name']])
        prompt = dedent(f"""
        Write an SMS conversation between this person and {format_contacts([contact])}, format as a JSON list of {num_turns} turns. Each turn consists of these attributes: "sender" and "message". The sender is either "{contact['full_name']}" or "myself"; the first turn should be from {first_turn}.
        """).strip()
        messages = [
            {"role": "user", "content": "\n\n".join([persona['intro'], prompt])}
        ]
        llm_output, cost = call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)
        sms_list = parse_llm_json_list(llm_output)
        sms_threads[contact['full_name']] = sms_list
    return sms_threads


def generate_app_data(persona):
    print(f">>> Processing persona id = {persona['id']}")
    generate_seed_data(persona)
    generate_contacts(persona)
    generate_calendar_events(persona)
    generate_reminders(persona)
    generate_messages(persona)
    generate_alarms(persona)
    return persona


def main():
    personas = load_personas()
    print(f">>> Loaded {len(personas)} personas")

    with open(CONTEXTS_FILE, 'a') as fp:
        with multiprocessing.dummy.Pool(5) as pool:
            for p in pool.imap(generate_app_data, personas):
                fp.write(json.dumps(p, ensure_ascii=False, default=str))
                fp.write("\n")


if __name__ == '__main__':
    main()
