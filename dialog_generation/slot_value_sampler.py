#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
import logging
import random
import time
from datetime import datetime, timedelta
from textwrap import dedent
from typing import Dict

from utilities.llm_synthesis_utils import call_openai_chat_completion, environment
from .context_loader import DATE_FORMAT, sample_time
from .dataclass import Operation, IntentValues, ServiceSchema, IntentSchema
from .schema_utils import Schema


def _request_openai_response(prompt: str):
    messages = [
        {'role': 'system',
         'content': "You are a helpful assistant. Please follow the user's instructions and examples' format."},
        {'role': 'user', 'content': prompt},
    ]
    while True:
        llm_output, _ = call_openai_chat_completion(
            messages,
            max_tokens=512,
            temperature=0.7,
            top_p=0.8,
            frequency_penalty=0,
            # 1 encourages diverse response, 0 allows repeating frequently.
            presence_penalty=0
            # 1 encourages using more provided keywords, 0 allows less constrained by the given context.
        )
        try:
            return json.loads(llm_output.replace('```json', '').replace('```', ''))
        except json.decoder.JSONDecodeError:
            logging.warning(f"LLM generated malformed JSON: {llm_output}")
            time.sleep(1)


def _prepare_prompt_params(service_schema: ServiceSchema, intent_schema: IntentSchema, input_slot_values: Dict = None) -> Dict:
    example_slot_values = {slot["name"]: slot["potential_values"] for slot in service_schema["slots"] if
                           len(slot["potential_values"]) > 0}
    service_intent = {"service": service_schema["service_name"], "operation": intent_schema["name"]}
    example_slot_values = json.dumps(example_slot_values) if len(example_slot_values) > 0 else None
    input_slot_values = input_slot_values or {}
    filtered_slot_values = {k: v for k, v in input_slot_values.items() if v}
    result = {
        'premise': json.dumps({**service_intent, **filtered_slot_values}),
        'example_slot_values': example_slot_values,
    }
    return result


def _sample_input_slot_values(intent_schema: IntentSchema, intent: IntentValues, context: Dict) -> None:
    # Steal slot values from a 'donor entity' in the same app's context (as input values for e.g. creating new events)
    donor_entities = context.get(intent.service if intent.service != 'messages' else 'messages_sent', [])
    if len(donor_entities) > 1:
        if intent_schema.require_context:
            donor_entities = donor_entities[:intent.context_entity_index] + donor_entities[intent.context_entity_index + 1:]
        donor_entity = random.choice(donor_entities)
    else:
        donor_entity = None

    # Fill in slot values
    for k, v in intent.input_slot_values.items():
        if v is not None:
            continue
        if donor_entity and k in donor_entity:
            intent.input_slot_values[k] = donor_entity[k]
        elif k in ['contacts', 'attendees']:
            if k == 'contacts':
                num = 1
            else:
                num = random.randint(1, 3)
            contacts = random.sample(context['contacts'], k=num)
            intent.input_slot_values[k] = [x['full_name'] for x in contacts]
        elif k in ['date', 'start_date']:
            today = datetime.strptime(context['today'], DATE_FORMAT)
            date = today + timedelta(days=random.randint(1, 14))
            intent.input_slot_values[k] = date.strftime(DATE_FORMAT)
        elif k in ['time', 'start_time']:
            granularity = random.choice([1, 5, 10, 15, 30])
            if intent.service == 'restaurant_booking':
                hours = random.choice([(10, 23), (11, 14), (17, 21)])
            else:
                hours = random.choice([(0, 24), (8, 23), (9, 21), (9, 18)])
            intent.input_slot_values[k] = sample_time(granularity, hours)


def generate_input_slot_values(service_schema: ServiceSchema, intent_schema: IntentSchema, intent: IntentValues, context: Dict) -> None:
    """ Populate values for input slots that are currently `None`.
    """
    # _sample_input_slot_values(intent_schema, intent, context)
    unfilled_slots = [k for k, v in intent.input_slot_values.items() if v is None]
    if not unfilled_slots:
        return

    # For slot values that cannot be sampled, use LLM to generate them.
    input_value_sample_template = dedent("""\
        Please generate examples with random slot values for the given slots.

        Example:                                
        Premise: {"service": "restaurant_event", "operation": "find_restaurant"}
        Slots: ["location", "cuisine_type"]
        Response: [{"location": "San Francisco", "cuisine_type": "Japanese"}]
        
        Please generate a list of 5 examples for the following slots. Please return in the format of JSON list.
        {{ "Here are some suggested slot values {}.".format(example_slot_values) if example_slot_values }}
        Premise: {{ premise }}
        Slots: {{ input_slots }}
        Response list:\
    """)
    input_value_sample_template = environment.from_string(input_value_sample_template)

    prompt_params = _prepare_prompt_params(service_schema, intent_schema, intent.input_slot_values)
    prompt_params['input_slots'] = json.dumps(unfilled_slots)
    input_value_sample_prompt = input_value_sample_template.render(prompt_params)
    response_object = _request_openai_response(input_value_sample_prompt)
    input_slot_values = random.choice(response_object)
    try:
        intent.input_slot_values.update(input_slot_values)
    except ValueError as e:
        logging.warning(f"Failed to update input slot values: {e}")
        print(input_slot_values)
        assert False

def generate_output_slot_values(service_schema: ServiceSchema, intent_schema: IntentSchema, intent: IntentValues) -> None:
    """ Overwrite the entire output slot values.
    """
    output_value_sample_template = dedent("""\
        Please generate examples with random real-world slot values for the given slots list. The slot values should follow the specifications in the premise.

        Example:           
        Premise: {"location": "San Francisco", "cuisine_type": "Japanese"}
        Slots: ["restaurant_name", "contact_number", "restaurant_address", "menu_price_range"]
        Response: [{"restaurant_name": "Akiko's Restaurant", "contact_number": "(415) 123-4567", "restaurant_address": "431 Bush St, San Francisco, CA 94108", "menu_price_range": "$$ - $$$"}]

        Now please generate a list of 5 realistic examples for the following slots. Please return in list of JSON format.
        {{ "Here are some suggested slot values {}.".format(example_slot_values) if example_slot_values }}
        Premise: {{ premise }}
        Slots: {{ output_slots }}
        Response list:
    """)
    output_value_sample_template = environment.from_string(output_value_sample_template)
    # Separate the result slots that are covered by the input slots -> We would like them fiexed for all examples in the returned list.
    # 22/08/2023 This might not be needed anymore, as the latest result_slots schema exclude all input_slots.
    non_overlapping_output_slots = list(set(intent_schema['result_slots']) - intent.input_slot_values.keys())
    overlapping_output_slots = list(set(intent_schema['result_slots']).intersection(intent.input_slot_values.keys()))

    prompt_params = _prepare_prompt_params(service_schema, intent_schema, intent.input_slot_values)
    prompt_params['output_slots'] = json.dumps(non_overlapping_output_slots)
    output_value_sample_prompt = output_value_sample_template.render(prompt_params)
    output_slot_values = _request_openai_response(output_value_sample_prompt)
    for output_slot_values_option in output_slot_values:
        output_slot_values_option.update({slot: intent.input_slot_values[slot] for slot in overlapping_output_slots})
    intent.output_slot_values = output_slot_values


def get_output_summary(data, emphasis_slots):
    summarisation_template = dedent("""\
        You are a helpful virtual assistant. Please return in JSON format with "summary" as key.
        Please summarise the below data with brief coherent sentences, emphasising the slots {{  emphasis_slots  }}.
        data: {{  data  }}
        summary:\
    """)
    summarisation_prompt = environment.from_string(summarisation_template)
    prompt_params = {'data': data, 'emphasis_slots': emphasis_slots}
    summarisation_prompt = summarisation_prompt.render(prompt_params)
    while True:
        summary_values = _request_openai_response(summarisation_prompt)
        if 'summary' in summary_values:
            break
    return summary_values


def populate_intent_slot_values(intent: IntentValues, context: Dict) -> None:
    service_schema = Schema.get_service_schema(intent.service)
    intent_schema = Schema.get_intent_schema(intent.service, intent.intent)
    if intent_schema.require_input_values:
        generate_input_slot_values(service_schema, intent_schema, intent, context)
        if intent_schema.result_slots:
            assert not intent_schema.check_on_input # 'check' intent shouldn't require input values. It shouldn't be here.
            generate_output_slot_values(service_schema, intent_schema, intent)
        if intent_schema.return_list:   # For intents that performs research and returns a list of search results
            selection_idx = random.randint(0, len(intent.output_slot_values)-1)
            intent.summary_further_slot_values = {'selection_idx': selection_idx,
                                                  'slot_values': intent.output_slot_values[selection_idx]}
            intent.output_slot_values = [get_output_summary(intent.output_slot_values, intent_schema['summary_emphasis_slots'])]
        else:
            intent.output_slot_values = [random.choice(intent.output_slot_values)]


def populate_operation_slot_values(operation: Operation, context: Dict) -> None:
    populate_intent_slot_values(operation.intent_values[-1], context)

    if operation.phenomena == 'compositional':
        outer_intent, inner_intent = operation.intent_values
        # Overwrite the matching slot values
        if inner_intent.matching_slot != 'summary':
            outer_intent_schema = Schema.get_intent_schema(outer_intent.service, outer_intent.intent)
            sampled_intent_inner_output_slots = inner_intent.output_slot_values[0]
            if outer_intent_schema.require_context:
                # require_context can only take 1 input slot; overwrite the existing slot
                assert len(outer_intent.input_slot_values) == 1 and outer_intent.matching_slot in outer_intent.input_slot_values
            outer_intent.input_slot_values[outer_intent.matching_slot] = sampled_intent_inner_output_slots[inner_intent.matching_slot]
        # todo: for the summary case, generate the actual summary text here?
        else: 
            pass

    for iv in operation.intent_values[:-1]:
        populate_intent_slot_values(iv, context)
