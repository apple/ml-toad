#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import base64
import hashlib
import json
import random
from collections import defaultdict
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from utilities.llm_synthesis_utils import call_openai_chat_completion
from .occupation_generator import INDUSTRIES_FILE, OCCUPATIONS_FILE

NAMES_FILE = "resources/Names_2010Census.csv"
PERSONAS_FILE = "data/personas.jsonl"

INDUSTRIES_APPLICABLE_TO_STUDENTS = {
    'Elementary and Secondary Schools',
    'Junior Colleges',
    'Colleges, Universities, and Professional Schools',
}
RACES = [
    'White',
    'Black or African American',
    'Asian or Pacific Islander',
    'American Indian or Alaska Native',
    'Multiracial',
    'Hispanic or Latino',
]
GENDERS_NORMALIZATION = {
    'Female': 'F',
    'Male': 'M',
    'Trans woman': 'F',
    'Trans man': 'M',
}
PRONOUNS = {
    'F': ("she", "her", "her"),
    'M': ("he", "him", "his"),
    'X': ("they", "them", "their"),
}


def load_hierarchical_occupations(industry_to_occupations: Dict) -> Dict:
    prefix_to_industries = defaultdict(dict)
    with open(INDUSTRIES_FILE, 'r') as fp:
        for line in fp:
            code, industry = line.split("\t")
            if len(code) == 6:
                industry = industry.strip()
                occupations = industry_to_occupations.get(industry)
                if occupations:
                    prefix_to_industries[code[:2]][industry] = occupations
    return prefix_to_industries


def sample_persona_by_occupation(industry_to_occupations: Dict, hierarchical_occupations: Dict) -> Dict:
    status = random.choices(['employed', 'unemployed', 'student'], k=1, weights=[0.7, 0.1, 0.2])[0]
    if status == 'student':
        industries = list(INDUSTRIES_APPLICABLE_TO_STUDENTS & industry_to_occupations.keys())
        occupations = industry_to_occupations[random.choice(industries)]
        occupation = random.choice(occupations)
        persona = {
            'address': occupation['address'],
            'occupation': 'Student',
            'school': {'name': occupation['establishment'], 'description': occupation['description']}
        }
    else:
        subtrees = list(hierarchical_occupations.values())
        occupations = list(random.choice(subtrees).values())
        occupation = random.choice(random.choice(occupations))
        persona = {'address': occupation['address'], 'occupation': 'Unemployed'}
        if status == 'unemployed':
            persona['occupation'] = 'Unemployed or retired'
        else:
            persona['occupation'] = occupation['position']
            persona['job_level'] = occupation['level']
            if random.random() < 0.8:
                persona['affiliation'] = {'name': occupation['establishment'], 'description': occupation['description']}
    return persona


def sample_gender() -> str:
    return random.choices(['Female', 'Male', 'Trans woman', 'Trans man', 'Non-binary', 'Other'],
                          k=1, weights=[0.49, 0.49, 0.005, 0.005, 0.005, 0.005])[0]


def get_pronoun(gender: str, case: str = 'subj') -> str:
    normalized_gender = GENDERS_NORMALIZATION.get(gender, 'X')
    pronouns = PRONOUNS[normalized_gender]
    if case == 'obj':
        return pronouns[1]
    elif case == 'poss':
        return pronouns[2]
    elif case == 'ref':
        return pronouns[1] + "self"
    else:
        return pronouns[0]


def sample_sexual_orientation() -> str:
    return random.choices(['Straight', 'Gay or lesbian', 'Bisexual', 'Pansexual', 'Asexual', 'Queer', 'Other'],
                          k=1, weights=[0.93, 0.03, 0.02, 0.005, 0.005, 0.005, 0.005])[0]


def sample_mbti() -> str:
    return ''.join(random.choice(choices) for choices in ['IE', 'NS', 'TF', 'JP'])


def load_surnames() -> Tuple[pd.DataFrame, Dict[str, float]]:
    df_surnames = pd.read_csv(NAMES_FILE, na_values=["(S)"])[:-1]
    race_to_count = {}
    for pct_col in df_surnames.columns[5:]:
        cnt_col = 'cnt' + pct_col[3:]
        df_surnames[cnt_col] = df_surnames['count'] * df_surnames[pct_col].fillna(0) / 100
        race_to_count[cnt_col] = sum(df_surnames[cnt_col])
    return df_surnames, race_to_count


def sample_surname_and_race(df_surnames: pd.DataFrame, race_to_count: Dict[str, float]) -> Tuple[str, str]:
    cnt_col = random.choices(list(race_to_count.keys()), k=1, weights=[c ** 0.5 for c in race_to_count.values()])[0]
    idx = random.choices(df_surnames.index, k=1, weights=df_surnames[cnt_col])[0]
    row = df_surnames.iloc[idx]
    surname = row['name']
    race_weights = row[5:11]
    num_nans = sum(1 for w in race_weights if np.isnan(w))
    if num_nans:
        weights_sum = sum(w for w in race_weights if not np.isnan(w))
        nan_replacement = max(0, 100 - weights_sum) / num_nans
        race_weights = [nan_replacement if np.isnan(w) else w for w in race_weights]
    race = random.choices(RACES, k=1, weights=[w ** 0.5 for w in race_weights])[0]
    return surname, race


def complete_persona_by_llm(persona):
    gender = persona['gender']
    status = random.choices(
        ['an unfortunate', 'a frustrated', 'a negative', 'a successful', 'an affluent', 'an energetic', 'a fictional'],
        k=1, weights=[0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.4])[0]
    prompt = f"""
    Imagine {status} character with the attributes above, write an introduction for {get_pronoun(gender, 'obj')} in 80 words. The introduction should include {get_pronoun(gender, 'poss')} real first name, age, marital status, any family members, lifestyle, and a few different hobbies.
    """.strip()
    messages = [
        {"role": "user", "content": "\n\n".join([json.dumps(persona, ensure_ascii=False), prompt])}
    ]
    return call_openai_chat_completion(messages, temperature=1.0, max_tokens=1024)


def hash_persona(persona) -> str:
    data = json.dumps(persona, sort_keys=True, ensure_ascii=False).encode('utf8')
    return base64.b85encode(hashlib.md5(data).digest()).decode()


def add_personas(num_personas_to_add: int) -> None:
    df_surnames, race_to_count = load_surnames()
    with open(OCCUPATIONS_FILE, 'r') as fp:
        industry_to_occupations = json.load(fp)
    hierarchical_occupations = load_hierarchical_occupations(industry_to_occupations)

    total_cost = 0
    with open(PERSONAS_FILE, 'a') as fp:
        for _ in range(num_personas_to_add):
            surname, race = sample_surname_and_race(df_surnames, race_to_count)
            persona = {
                'last_name': surname,
                'gender': sample_gender(),
            }
            if GENDERS_NORMALIZATION.get(persona['gender'], 'X') != 'X' and random.random() < 0.5:
                persona['sexual_orientation'] = sample_sexual_orientation()
            if random.random() < 0.5:
                persona['race'] = race
            persona.update(sample_persona_by_occupation(industry_to_occupations, hierarchical_occupations))
            if random.random() < 0.5:
                persona['personality_mbti'] = sample_mbti()
            pid = hash_persona(persona)
            llm_output, cost = complete_persona_by_llm(persona)
            print(f"{persona['last_name']} >>> {llm_output}")
            total_cost += cost
            persona['intro'] = llm_output.strip()
            persona = {'id': pid} | persona  # make `id` the first attribute
            fp.write(json.dumps(persona, ensure_ascii=False))
            fp.write("\n")
    print(f"Synthesis complete. Cost: ${total_cost}")


if __name__ == '__main__':
    add_personas(500)  # set the num of personas you want to append
