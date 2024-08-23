#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import random
from typing import List, Union

from .dataclass import Operation, IntentPlot, SystemResponseStyle, Action, MetaAction, IntentValues
from .plot_generator_utils import generic_intent_plot_generator
from .schema_utils import Schema


def add_service_prefix_to_actions(service_prefix: str, action_list: List[Union[Action,MetaAction]]) -> None:
    for act in action_list:
        if isinstance(act, Action):
            act.service_prefix = service_prefix
        elif isinstance(act, MetaAction):
            act.default_action.service_prefix = service_prefix
            if act.special_mirroring_action:
                act.special_mirroring_action.service_prefix = service_prefix


def filter_relevant_context(full_context, operation):
    relevant_service = [intent_value['service'] for intent_value in operation['intent_values']]

    filtered_context = {} 
    default_context_key = ['today']
    for contexet in default_context_key:
        if isinstance(full_context[contexet], list) and len(full_context[contexet]) >5:
            filtered_context[contexet] = random.sample(full_context[contexet], k=5)
        else:
            filtered_context[contexet] = full_context[contexet]

    for service, context in full_context.items():
        if service in relevant_service:
            filtered_context[service] = context

    user_intro = full_context['intro']
    return filtered_context, user_intro


def time_date_sort_key(data_str):
    """ The time and date in the context has canonical format. For example: '09:00' and 'Thu 2024-10-17'.
    We only need to remove the day to perform sorting.
    """
    return data_str.split(' ')[-1]


def compose_compound_dialog(operation, context) -> IntentPlot:
    service_1 = operation['intent_values'][0]['service']
    service_2 = operation['intent_values'][1]['service']
    plot_msg_1 = generic_intent_plot_generator(
        operation.intent_values[0],
        context,
        phenomena=operation['phenomena'])  # fot now, only consider this operation
    plot_msg_2 = generic_intent_plot_generator(
        operation.intent_values[1],
        context,
        phenomena=operation['phenomena'])  # fot now, only consider this operation
    # The first turn of two intents should be the main commands.
    user_actions = []
    system_actions = []
    system_response_style = []

    # Composing initial query
    add_service_prefix_to_actions(service_1, plot_msg_1.user_actions[0])
    add_service_prefix_to_actions(service_2, plot_msg_2.user_actions[0])
    user_actions.append(plot_msg_1.user_actions[0] + plot_msg_2.user_actions[0])

    l, r = 0, 0
    while l < len(plot_msg_1.system_actions) and r < len(plot_msg_2.system_actions):
        if plot_msg_1.system_actions[l][0].expect_usr and plot_msg_2.system_actions[r][0].expect_usr:
            # when both system expect usr to return information, split into multi-turn.
            add_service_prefix_to_actions(service_1, plot_msg_1.system_actions[l])
            system_actions.append(plot_msg_1.system_actions[l])
            system_response_style.append(SystemResponseStyle(verbosity='verbosity_mid', additional=[]))
            if l + 1 < len(plot_msg_1.user_actions):
                add_service_prefix_to_actions(service_1, plot_msg_1.user_actions[l + 1])
                user_actions.append(plot_msg_1.user_actions[l + 1])
            l += 1
        else:
            # Organizing the order of compound responses
            add_service_prefix_to_actions(service_1, plot_msg_1.system_actions[l])
            add_service_prefix_to_actions(service_2, plot_msg_2.system_actions[r])
            if plot_msg_1.system_actions[l][0].priority <= plot_msg_2.system_actions[r][0].priority:
                system_actions.append(plot_msg_1.system_actions[l] + plot_msg_2.system_actions[r])
            else:
                system_actions.append(plot_msg_2.system_actions[r] + plot_msg_1.system_actions[l])
            system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=['compound']))

            if l + 1 < len(plot_msg_1.user_actions) and r + 1 < len(plot_msg_2.user_actions):
                add_service_prefix_to_actions(service_1, plot_msg_1.user_actions[l + 1])
                add_service_prefix_to_actions(service_2, plot_msg_2.user_actions[r + 1])
                user_actions.append(plot_msg_1.user_actions[l + 1] + plot_msg_2.user_actions[r + 1])
            elif l + 1 < len(plot_msg_1.user_actions):
                add_service_prefix_to_actions(service_1, plot_msg_1.user_actions[l + 1])
                user_actions.append(plot_msg_1.user_actions[l + 1])
            elif r + 1 < len(plot_msg_2.user_actions):
                add_service_prefix_to_actions(service_2, plot_msg_2.user_actions[r + 1])
                user_actions.append(plot_msg_2.user_actions[r + 1])
            else:
                pass
            l += 1
            r += 1

    # Append the unfinished dialog
    if l != len(plot_msg_1.system_actions):
        for actions in plot_msg_1.system_actions[l:]:
            add_service_prefix_to_actions(service_1, actions)
        system_actions += plot_msg_1.system_actions[l:]
        system_response_style += plot_msg_1['system_response_style'][l:]
        if l + 1 < len(plot_msg_1.user_actions):
            for actions in plot_msg_1.user_actions[l + 1:]:
                add_service_prefix_to_actions(service_1, actions)
            user_actions += plot_msg_1.user_actions[l + 1:]

    if r != len(plot_msg_2.system_actions):
        for actions in plot_msg_2.system_actions[r:]:
            add_service_prefix_to_actions(service_2, actions)
        system_actions += plot_msg_2.system_actions[r:]
        system_response_style += plot_msg_2['system_response_style'][r:]
        if r + 1 < len(plot_msg_2.user_actions):
            for actions in plot_msg_2.user_actions[r + 1:]:
                add_service_prefix_to_actions(service_2, actions)
            user_actions += plot_msg_2.user_actions[r + 1:]

    plot_msg = IntentPlot(
        user_actions=user_actions,
        system_actions=system_actions,
        system_response_style=system_response_style,
        local_phenomena=plot_msg_1.local_phenomena + plot_msg_2.local_phenomena
    )
    return plot_msg


def compose_compositional_dialog(operation, context) -> IntentPlot:
    inner_intent_values: IntentValues = operation['intent_values'][1]
    outer_intent_values: IntentValues = operation['intent_values'][0]
    if_summary = inner_intent_values['matching_slot'] == 'summary'

    # The slot value for outer intent maching slot has been modified by populate_operation_slot_values
    plot_outer: IntentPlot = generic_intent_plot_generator(outer_intent_values, context, phenomena=operation['phenomena'])
    plot_inner: IntentPlot = generic_intent_plot_generator(inner_intent_values, context, phenomena=operation['phenomena'])
    
    user_actions, system_actions, system_response_style = [], [], []
    l, r = 0, 0
    # Compose the Initial user query.
    secondary_action: Action = plot_inner.user_actions[0][0]  
    secondary_action.service_prefix = inner_intent_values.service 
    if if_summary:  # For search type intent
        secondary_action.attribute = "summary"
    else:  # For the rest of intent
        # This was for non summary non referral case, where attribute was not set. But it can also work for referral case. e.g. check(date) -> .date
        secondary_action.attribute = inner_intent_values['matching_slot']  
    primary_matching_slot = outer_intent_values['matching_slot']

    add_service_prefix_to_actions(outer_intent_values.service, plot_outer.user_actions[0])
    primary_action: Action = plot_outer.user_actions[0][0]
    primary_action.arguments[primary_matching_slot] = secondary_action  
    user_actions.append([primary_action])

    # First filling the slots for secondary intent
    while r < len(plot_inner.system_actions):
        if plot_inner.system_actions[r][0].expect_usr:
            add_service_prefix_to_actions(inner_intent_values.service, plot_inner.system_actions[r])
            system_actions.append(plot_inner.system_actions[r])
            system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=[]))
            r += 1
            add_service_prefix_to_actions(inner_intent_values.service, plot_inner.user_actions[r])
            user_actions.append(plot_inner.user_actions[r])
        else:
            break

    # Then filling the slots for primary intent
    while l < len(plot_outer.system_actions):
        if plot_outer.system_actions[l][0].expect_usr == 1:
            add_service_prefix_to_actions(outer_intent_values.service, plot_outer.system_actions[l])
            system_actions.append(plot_outer.system_actions[l])
            system_response_style.append(plot_outer['system_response_style'][l])
            l += 1
            add_service_prefix_to_actions(outer_intent_values.service, plot_outer.user_actions[l])
            user_actions.append(plot_outer.user_actions[l])
        else:
            break

    # Only reporting the primary intent result
    if l != len(plot_outer.system_actions):
        # <--!--> Insert the second action here, the notidy_done() is guarentee to have no argument.
        add_service_prefix_to_actions(outer_intent_values.service, plot_outer.system_actions[l])
        add_service_prefix_to_actions(inner_intent_values.service, plot_inner.system_actions[r])
        final_response_expression: MetaAction = plot_outer.system_actions[l][0]
        final_response_style = SystemResponseStyle(verbosity='verbosity_high', additional=['complex'])

        if if_summary:
            ## When the inner intent is summary variation of check, we need to report all slot values for that context event.
            secondary_intent_schema = Schema.get_intent_schema(service=inner_intent_values.service, intent=inner_intent_values.intent)
            if secondary_intent_schema['check_on_input']:
                full_slot_values = context[inner_intent_values.service][inner_intent_values.context_entity_index]
                plot_inner.system_actions[r][0].default_action.arguments = full_slot_values
            summerise_inner_action = plot_inner.system_actions[r][0].default_action

            if '' in final_response_expression.default_action.arguments:
                final_response_expression.default_action.arguments[''].arguments[primary_matching_slot] = summerise_inner_action
                if final_response_expression.special_mirroring_action:
                    final_response_expression.special_mirroring_action.arguments[''].arguments[primary_matching_slot] = summerise_inner_action
            else:
                final_response_expression.default_action.arguments[primary_matching_slot] = summerise_inner_action
            final_response_style.additional = ['summarisation', 'complex']

        system_response_style.append(final_response_style)
        system_actions.append([final_response_expression])

    plot_msg = IntentPlot(
        user_actions=user_actions,
        system_actions=system_actions,
        system_response_style=system_response_style,
        local_phenomena=plot_outer.local_phenomena + plot_inner.local_phenomena,
    )
    return plot_msg



def get_dialog_plot(operation: Operation, context: dict) -> IntentPlot:
    """ Get the entire dialog plot, which may be a merger of two plots for individual intents.
    """
    if operation['phenomena'] == 'compound':
        plot_msg = compose_compound_dialog(operation, context)
    elif operation['phenomena'] == 'compositional':
        plot_msg = compose_compositional_dialog(operation, context)
    elif operation['phenomena'] == 'none':  
        plot_msg = generic_intent_plot_generator(operation['intent_values'][0], context, phenomena=operation['phenomena'])
    else: 
        raise ValueError(f"unknown phenomenon: {operation['phenomena']}")
    return plot_msg


def get_initial_buffer(setup, context, operation: Operation):
    """
    The input are sampled context and setup parameters, service, api and phenomena to simulate.
    The service should be one of ['alarm', 'calendar'].
    The api should be the corresponding operations supported by the service. Some examples are ['create', 'modify', 'check', 'delete']
    The phenomena should be one of ['None', ]
    This function returns the initial buffer for the given plot of dialog.
    """
    relevant_context, usr_intro = filter_relevant_context(context, operation)

    user_style_instruction_list = {
        'slow': 'Please take the nesting action as a clause and the slot value as an antecedent. Generate a coherent and complex user query.',
        # 'The message should not be more than 30 words.',
        'normal': ''}
    system_style_instruction_list = {'low_grounding': 'The message should be natural and use pronoun when possible.',
                                     'normal_grounding': '',
                                     'high_grounding': 'The message should not be more than 20 words.', }
    # system_style_instruction_grounding = {'low': 'The message must only have a couple of words, such as "when", "how long" or "done".',
    #                                       'mid': 'The message must replace the nouns or noun phrases mentioned by user with pronouns, such as "it", "that" and "its".', 
    #                                       'high': 'The message should use full expression with name if available rather than pronouns.'}

    # Resolve setup to determine grounding level
    if setup['event_execute_count'] > 3 or setup['user_speaking_speed'] == 'slow':
        user_style_instruction = user_style_instruction_list['slow']
        system_style_instruction = system_style_instruction_list['high_grounding']

    else:
        user_style_instruction = user_style_instruction_list['normal']
        system_style_instruction = system_style_instruction_list['high_grounding']

    plot_msg = get_dialog_plot(operation, relevant_context)

    services = ', '.join(intent['service'] for intent in operation.intent_values)

    # # Action realization
    # user_actions = [[act.realize() for act in actions] for actions in plot_msg.user_actions]
    # system_actions = [[act.realize() for act in actions] for actions in plot_msg.system_actions]

    buffer = {
        'phenomena': operation.phenomena,
        'local_phenomena': plot_msg.local_phenomena,
        'context': relevant_context,
        'situation': services,
        'services': [intent['service'] for intent in operation.intent_values],
        'intents': [intent['intent'] for intent in operation.intent_values],
        # 'intent': ,
        'dialog_action_user': plot_msg.user_actions,
        'dialog_action_system': plot_msg.system_actions,
        'user_style_instruction': user_style_instruction,
        'system_optimal_style': plot_msg['system_response_style'],
        # 'system_mirror_switch': setup['system_mirror_switch'],
        # 'system_kid_switch': setup['system_kid_switch'],
        'system_style_instruction': '',
        'cur_turn_counter': 0,
        'conversation': [],
        'response_options': [],
        'user_intro': usr_intro,
    }
    return buffer
