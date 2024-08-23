#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
import random
from textwrap import dedent

from utilities.llm_synthesis_utils import call_openai_chat_completion

INDUSTRIES_FILE = "resources/NAICS_2022.tsv"
OCCUPATIONS_FILE = "data/occupations.json"


def load_industries(skip_keys=None):
    industries = set()
    with open(INDUSTRIES_FILE) as fp:
        for line in fp:
            code, industry = line.split("\t")
            if len(code) == 6:
                industry = industry.strip()
                if skip_keys and industry in skip_keys:
                    continue
                industries.add(industry)
    print(f"Loaded {len(industries)} industries")
    return sorted(industries)


def generate_occupations_for_industry(industry: str, n: int):
    prompt = dedent(f"""
    Create {n} random but realistic establishments of different sizes in the \"{industry}\" industry. Submit a JSON list of objects, by formatting each of them as an object with following attributes.
    * "establishment": Name of the establishment.
    * "address": The city it is located in (must be within the US).
    * "description": A short description of what it does.
    * "position": A plausible position in that establishment.
    * "level": What job level that position belongs to ("entry-level", "intermediate", or "senior").
    """).strip()
    messages = [
        {"role": "user", "content": prompt}
    ]
    return call_openai_chat_completion(messages, temperature=0.7, max_tokens=1024)


def load_occupations():
    try:
        with open(OCCUPATIONS_FILE) as fp:
            return json.load(fp)
    except FileNotFoundError:
        return {}


def add_occupations(num_industries_to_add: int, num_establishments_per_industry: int = 5):
    occupations = load_occupations()
    all_remaining_industries = load_industries(occupations.keys())
    industries = random.sample(all_remaining_industries, k=min(num_industries_to_add, len(all_remaining_industries)))
    total_cost = 0
    for industry in industries:
        print(f"Generating occupations in industry: {industry}")
        llm_output, cost = generate_occupations_for_industry(industry, num_establishments_per_industry)
        total_cost += cost
        try:
            generated_occupations = json.loads(llm_output)
        except json.JSONDecodeError:
            print(f"Malformed LLM Output: {llm_output}")
            continue
        occupations[industry] = generated_occupations
    print(f"Synthesis complete. Cost: ${total_cost}")
    with open(OCCUPATIONS_FILE, "wt") as fp:
        json.dump(occupations, fp, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    add_occupations(200)  # set the num of occupations you want to append
