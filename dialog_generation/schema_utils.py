#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
import random
from collections import defaultdict
from typing import List, NamedTuple, Tuple

from .dataclass import ServiceSchema, IntentSchema


class CompositionalIntent(NamedTuple):
    inner: Tuple[ServiceSchema, IntentSchema]
    outer: Tuple[ServiceSchema, IntentSchema]
    inner_slot: str
    outer_slot: str

    def __repr__(self):
        return f"{self.outer[0].service_name}.{self.outer[1].name}({self.outer_slot}={self.inner[0].service_name}.{self.inner[1].name}().{self.inner_slot})"


class Schema:
    _data: List[ServiceSchema] = []
    _compositional: List[CompositionalIntent] = []

    @classmethod
    def get_schema(cls):
        if not cls._data:
            file_path = "data/schema.json"
            with open(file_path, 'r') as file:
                data = json.load(file)
                cls._data = [ServiceSchema.from_dict(serv) for serv in data]
        return cls._data

    @classmethod
    def get_service_schema(cls, service: str) -> ServiceSchema:
        data = cls.get_schema()
        for service_schema in data:
            if service_schema.service_name == service:
                return service_schema
        else:
            raise ValueError("Couldn't find service schema")

    @classmethod
    def get_intent_schema(cls, service: str, intent: str) -> IntentSchema:
        service_schema = cls.get_service_schema(service)
        return service_schema.get_intent(intent)

    @classmethod
    def iter_intents(cls):
        data = cls.get_schema()
        for service_schema in data:
            for intent_schema in service_schema.intent_operations:
                yield service_schema, intent_schema

    @classmethod
    def sample_compositional_intent(cls) -> CompositionalIntent:
        if not cls._compositional:
            for inner_serv, inner_intent in cls.iter_intents():
                if inner_intent.check_on_input:
                    inner_output_slots = inner_intent.required_slots + inner_intent.optional_slots
                else:
                    inner_output_slots = inner_intent.result_slots
                if not inner_output_slots:
                    continue  # inner intent must return something
                if inner_intent.return_list:
                    inner_output_slots = ['summary']
                else:
                    inner_output_slots = inner_output_slots + ['summary']
                alias_to_slot = defaultdict(set)
                for s in inner_output_slots:
                    for alias in inner_serv.get_slot(s).alias + [s]:
                        alias_to_slot[alias].add(s)
                for outer_serv, outer_intent in cls.iter_intents():
                    if outer_serv.service_name == inner_serv.service_name and outer_intent.name == inner_intent.name:
                        continue  # must be different intents
                    if not outer_intent.require_input_values:
                        continue  # outer intent must require an input slot value
                    outer_input_slots = outer_intent.required_slots + outer_intent.optional_slots
                    matching_slots = set(outer_input_slots) & alias_to_slot.keys()
                    for outer_slot in matching_slots:
                        for inner_slot in alias_to_slot[outer_slot]:
                            cls._compositional.append(CompositionalIntent(
                                inner=(inner_serv, inner_intent),
                                outer=(outer_serv, outer_intent),
                                inner_slot=inner_slot,
                                outer_slot=outer_slot,
                            ))
        return random.choice(cls._compositional)
