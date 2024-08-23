#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import logging
import os
import time
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from jinja2 import Environment, select_autoescape
from openai import OpenAI

load_dotenv()
openai_api_key = os.environ.get("OPENAI_API_KEY")
base_url = os.environ.get("BASE_URL")
engine = os.environ.get("ENGINE")

environment = Environment(autoescape=select_autoescape(default_for_string=False))


def call_openai_chat_completion(
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        wait_sec: float = 0.3,
        max_wait_sec: float = 0.3,
        **kwargs
) -> Tuple[str, float]:
    client = OpenAI(api_key=openai_api_key, base_url=base_url)
    while True:
        try:
            response = client.chat.completions.create(
                model=engine,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            break
        except Exception as e:
            msg = f"Retrying in {wait_sec} s due to OpenAI Error: {e}"
            if 'rate limit' in msg.lower():
                logging.debug(msg)
            else:
                logging.warning(msg)
            time.sleep(wait_sec)
            wait_sec = min(wait_sec * 2, max_wait_sec)
    llm_output = response.choices[0].message.content.strip().replace('```json', '').replace('```', '')
    cost = 0.002 * response.usage.total_tokens / 1000
    return llm_output, cost
