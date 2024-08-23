#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import random
from typing import Dict

from .dataclass import IntentValues
from .schema_utils import Schema


class IncompatibleContext(RuntimeError):
    pass


def sample_intent(context: Dict, service: str = None, intent: str = None, input_slot: str = None, output_slot: str = None) -> IntentValues:
    """ Get an intent with slot keys but empty slot values.
    """
    schema = Schema.get_schema()

    # Randomly sample service & intent, or use the specified given ones
    if service:
        for s in schema:
            if s.service_name == service:
                service_schema = s
                break
        else:
            raise ValueError(f"undefined service: {service}")
    else:
        service_schema = random.sample(schema, k=1)[0]

    if intent:
        for i in service_schema.intent_operations:
            if i.name == intent:
                intent_schema = i
                break
        else:
            raise ValueError(f"undefined intent: {intent}")
    else:
        intent_schema = random.sample(service_schema.intent_operations, k=1)[0]

    # Make sure output_slot is satisfied
    if output_slot and output_slot != 'summary':
        assert not input_slot
        if intent_schema.check_on_input:
            input_slot = output_slot
        else:
            assert output_slot in intent_schema.result_slots

    # Create input & output slots
    output_slot_values = [{slot: None for slot in intent_schema.result_slots}]
    if intent_schema.require_context:
        # When the sampled intent needs interaction with the context.
        num_entities = len(context.get(service_schema.service_name, []))
        if not num_entities:
            raise IncompatibleContext(f"context lacks data for {service_schema.service_name}")
        context_entity_index = random.randrange(num_entities)
        context_entity = context[service_schema.service_name][context_entity_index]
        # We dont check the necessary slots here, cuz we assume
        # if intent needs interacting with context, then it can only operate upto 1 slot.
        # The reason we sample the operation slot here is we would like to fix the output type here.
        # As a result, we can use it to find intent pair for compositional dialog.
        assert not intent_schema.required_slots
        available_slots = set(intent_schema.optional_slots) & context_entity.keys()
        if input_slot: # If input_slot is specified, we only sample that slot.
            if input_slot not in available_slots:
                raise IncompatibleContext(f"context entity doesn't have attribute {input_slot}")
            sampled_input_slots = [input_slot]
        else:
            num_input_slots = random.randint(intent_schema.minimum_input_slot_number, 1)
            sampled_input_slots = random.sample(list(available_slots), k=num_input_slots)
        if intent_schema.check_on_input:
            assert not intent_schema.result_slots
            output_slot_values = [{slot: context_entity[slot] for slot in sampled_input_slots}]
    else:
        context_entity_index = 0
        # <-------------  To be implemented: How to sample slots;
        # How many optional slots should be sampled for different intents  ---------------->
        sampled_input_slots = intent_schema.required_slots[:]
        optional_slots = intent_schema.optional_slots[:]
        if input_slot and input_slot not in sampled_input_slots:
            sampled_input_slots.append(input_slot)
            optional_slots.remove(input_slot)
        max_num_extra_slots = len(intent_schema.required_slots) + len(intent_schema.optional_slots) - len(sampled_input_slots)
        min_num_extra_slots = max(intent_schema.minimum_input_slot_number - len(sampled_input_slots), 0)
        num_extra_slots = random.randint(min_num_extra_slots, max_num_extra_slots)
        sampled_input_slots.extend(random.sample(optional_slots, k=num_extra_slots))
    input_slot_values = {slot: None for slot in sampled_input_slots}

    return IntentValues(
        service=service_schema.service_name,
        intent=intent_schema.name,
        context_entity_index=context_entity_index,
        input_slot_values=input_slot_values,
        output_slot_values=output_slot_values,
    )
