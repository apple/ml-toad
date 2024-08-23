#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import copy
import json
from dataclasses import dataclass
from typing import List, Optional, Union

from dataclasses_json import dataclass_json

SYS_ACTION_PRIORITY = {
    'ask_user_for': 6,
    'inform_result': 4,
    'inform_summary': 4,
    'ask_confirm': 2,
    'notify_done': 4,
}
SYS_ACTION_EXPECT_USR = {
    'ask_user_for': True,
    'inform_result': False,
    'inform_summary': False,
    'ask_confirm': True,
    'notify_done': False,
}


def convert_kv_to_string(d):
    if not d:
        return ''
    else:
        return ', '.join([f"{key}={json.dumps(val)}" if val else key for key, val in d.items()])


class DictInterface:

    def __getitem__(self, key):
        return getattr(self, key, None)


@dataclass_json
@dataclass(frozen=True)
class IntentSchema(DictInterface):
    name: str
    description: str
    require_input_values: bool
    require_context: bool
    require_confirmation: bool
    return_list: bool
    report_result: bool
    check_on_input: bool
    can_refer_to_input_slot: bool
    minimum_input_slot_number: int
    minimum_initial_slots: List[str]
    summary_emphasis_slots: List[str]
    required_slots: List[str]
    optional_slots: List[str]
    result_slots: List[str]


@dataclass_json
@dataclass(frozen=True)
class SlotSchema(DictInterface):
    name: str
    description: str
    potential_values: List[str]
    alias: List[str]


GLOBAL_SLOT_SCHEMA = {
    'summary': SlotSchema('summary', 'Summary of the results.', [], ['text'])
}


@dataclass_json
@dataclass(frozen=True)
class ServiceSchema(DictInterface):
    service_name: str
    intent_operations: List[IntentSchema]
    slots: List[SlotSchema]

    def get_intent(self, intent: str) -> IntentSchema:
        for intent_schema in self.intent_operations:
            if intent_schema.name == intent:
                return intent_schema
        else:
            raise ValueError("Couldn't find intent schema")

    def get_slot(self, slot: str) -> SlotSchema:
        for slot_schema in self.slots:
            if slot_schema.name == slot:
                return slot_schema
        else:
            slot_schema = GLOBAL_SLOT_SCHEMA.get(slot)
            if slot_schema:
                return slot_schema
            raise ValueError("Couldn't find slot schema")


@dataclass_json
@dataclass
class Action(DictInterface):
    action_name: str
    service_prefix: Optional[str] = None
    attribute: Union[str, 'Action', None] = None
    referral_action: Optional['Action'] = None
    referral_event_index: Optional[int] = None
    item_index: Optional[int] = None
    arguments: Optional[dict] = None
    max_num_arguments: Optional[int] = None   # Not used
    no_bracket: bool = False
    
    def realize(self):
        if self.arguments:
            kv_list = []
            for key, val in self.arguments.items():
                if isinstance(val, Action):
                    if key == '':
                        kv_list.append("{}".format(val.realize()))
                    else:
                        kv_list.append("{}={}".format(key, val.realize()))
                elif val or val==0:
                    kv_list.append("{}={}".format(key, json.dumps(val, ensure_ascii=False)))
                else:   # Should be None
                    kv_list.append("{}".format(key))
            arguments_expression = ', '.join(kv_list)
        else:
            arguments_expression = ''
        
        if self.no_bracket:
            action_string = '{intent}'.format(intent=self.action_name)
        else:
            action_string = '{intent}({args})'.format(intent = self.action_name, 
                                                    args=arguments_expression)
        if self.service_prefix:
            action_string = '{prefix}_'.format(prefix=self.service_prefix) + action_string
        if self.item_index or self.item_index==0:
            action_string += '[{}]'.format(self.item_index)
        if self.attribute:
            if isinstance(self.attribute, Action):
                action_string += '.{}'.format(self.attribute.realize())
            else:
                action_string += '.{}'.format(self.attribute)
        if self.referral_action:
            action_string = self.referral_action.realize() + '.' + action_string
        return action_string
    
    def realize_generic_action(self, context=None):
        if self.arguments:
            kv_list = []
            for key, val in self.arguments.items():
                if isinstance(val, Action):
                    if key == '':
                        kv_list.append("{}".format(val.realize_generic_action(context)))
                    else:
                        kv_list.append("{}={}".format(key, val.realize_generic_action(context)))
                elif val or val==0:
                    kv_list.append("{}={}".format(key, json.dumps(val, ensure_ascii=False)))
                else:   # Should be None
                    kv_list.append("{}".format(key))
            arguments_expression = ', '.join(kv_list)
        else:
            arguments_expression = ''
        
        if self.no_bracket:
            action_string = '{intent}'.format(intent=self.action_name)
        else:
            action_string = '{intent}({args})'.format(intent = self.action_name, 
                                                    args=arguments_expression)
        if self.service_prefix:
            action_string = '{prefix}_'.format(prefix=self.service_prefix) + action_string
        if self.item_index or self.item_index==0:
            action_string += '[{}]'.format(self.item_index)
        if self.attribute:
            if isinstance(self.attribute, Action):
                action_string += '.{}'.format(self.attribute.realize_generic_action(context))
            else:
                action_string += '.{}'.format(self.attribute)
        if self.referral_action:
            # if self.service_prefix in context: # For compositional action, it's difficult to tell which part of the action belows to which service.
            #     context = copy.copy(context[self.service_prefix])
            for key, value in context.items():
                if key in self.referral_action.action_name:
                    referred_context = value
            self.referral_action.arguments = {'context': referred_context, 'index': self.referral_action.referral_event_index}
            action_string = self.referral_action.realize_generic_action(context) + '.' + action_string
        return action_string
    
    @staticmethod
    def convert_from_dict(data: dict) -> 'Action': 
        ''' Should use this convertor rather than the from_dict() which won't parse accuratly'''
        if isinstance(data, dict):
            # Convert nested 'arguments' dictionary recursively
            arguments = data.get('arguments', {}) if data.get('arguments', {}) else {}
            arguments = {k: Action.convert_from_dict(v) for k, v in arguments.items()}
            attribute = data.get('attribute') 
            if isinstance(attribute, dict):
                attribute = Action.convert_from_dict(attribute)
            return Action(
                action_name=data.get('action_name'),
                service_prefix=data.get('service_prefix'),
                attribute=attribute,
                referral_action=Action.convert_from_dict(data.get('referral_action')),
                referral_event_index=data.get('referral_event_index'),
                item_index=data.get('item_index'),
                arguments=arguments,
                max_num_arguments=data.get('max_num_arguments'),
                no_bracket=data.get('no_bracket', False)
            )
        else:
            return data


@dataclass_json
@dataclass
class MetaAction(DictInterface):
    default_action: Action
    special_mirroring_action: Optional[Action] = None
    generic_action: Optional[Action] = None
    special_low_verbosity: bool = False

    @property
    def expect_usr(self) -> bool:
        return SYS_ACTION_EXPECT_USR[self.default_action.action_name]
    
    @property
    def priority(self) -> int:
        return SYS_ACTION_PRIORITY[self.default_action.action_name]

    def realize(self, style=(), context=None):
        if 'mirroring' in style and self.special_mirroring_action:
            action_to_realize = copy.deepcopy(self.special_mirroring_action)
        else:
            action_to_realize = copy.deepcopy(self.default_action)
        if 'verbosity_low' in style and self.special_low_verbosity:
            action_to_realize.arguments = None
        if context:
            return action_to_realize.realize_generic_action(context)
        else:
            return action_to_realize.realize()

    @staticmethod
    def convert_from_dict(data: dict) -> 'MetaAction':
        ''' Should use this convertor rather than the from_dict() which won't parse accuratly'''
        default_action = Action.convert_from_dict(data['default_action'])
        special_mirroring_action = (
            Action.convert_from_dict(data['special_mirroring_action'])
            if 'special_mirroring_action' in data
            else None
        )
        special_low_verbosity = data.get('special_low_verbosity', False)
        return MetaAction(
            default_action=default_action,
            special_mirroring_action=special_mirroring_action,
            special_low_verbosity=special_low_verbosity
        )


@dataclass
class IntentPlot(DictInterface):
    user_actions: List[List[Action]]
    system_actions: List[List[Action]]
    system_response_style: list
    local_phenomena: Optional[list]


@dataclass
class IntentValues(DictInterface):
    service: str
    intent: str
    context_entity_index: int
    input_slot_values: dict
    output_slot_values: Union[List[dict], dict]
    matching_slot: Optional[str] = None
    initial_slot: Optional[list] = None
    summary_further_slot_values: Optional[dict] = None

    def __str__(self):
        return f"{self.service}.{self.intent}({convert_kv_to_string(self.input_slot_values)})"
    

@dataclass
class Operation(DictInterface):
    phenomena: str
    intent_values: List[IntentValues]

    def __str__(self):
        return f"{self.phenomena}, {', '.join(str(i) for i in self.intent_values)}"


system_response_style_prompts: dict = {
    'verbosity_low': 'The message must only have a couple of words or verbs, such as "when", "how long", "changed" or "done".',
    'verbosity_mid': 'The message must replace the nouns or noun phrases mentioned by user with pronouns, such as "it", "that" and "its".',
    'verbosity_high': 'The message should use full expressions with name if available rather than pronouns.',
    'mirroring': "The message should use the user's noun phrases or verb expressions.",  # It should refer to the event or verbs by the same user's expression.",
    'no_mirroring': "Ignore the previous conversation.",  # Do not use the expression used by the user.
    'summarisation': 'Please respond with a single sentence coherent summary.',
    'complex': 'Please respond with a single sentence with complex sentence structure.',
    'compound': 'Please response with a sentence with compound sentence structure if possible.',
    'kid_friendly': "The message should use simple words with less syllables and safe language as if talking to a children."
}


@dataclass_json
@dataclass
class SystemResponseStyle(DictInterface):
    verbosity: Optional[str] = None
    mirroring: Optional[str] = None
    additional: Optional[list] = None
    
    def get_style_tuple(self):
        return tuple([self.verbosity, self.mirroring] + self.additional)
    
    def realize(self):
        if self.additional == None:
            self.additional = []
        styles = []
        if self.mirroring:
            styles.append(self.mirroring)
        if self.verbosity:
            styles.append(self.verbosity)
        return ' '.join([system_response_style_prompts[style] for style in styles + self.additional])
    
    def realize_to_key(self):
        key = ''
        key += self.verbosity
        if self.mirroring:
            key += ' ' + 'mirroring'
        else:
            key += ' ' + 'no_mirroring'
        return key


if __name__ == '__main__':

    a = Action(action_name='help', 
               arguments={'time':'2pm', 
                          'content':Action(action_name='search', 
                                           arguments={'name':'Titan', 'location':None},
                                           attribute='summary')
                         }
                )
    print(a.realize())