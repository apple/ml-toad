#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import copy
import random

from .dataclass import IntentPlot, SystemResponseStyle, Action, IntentValues, MetaAction
from .schema_utils import Schema
from .slot_value_sampler import populate_intent_slot_values

# There might be a better way to record them, e.g. saved in the schema file
FULL_RANKABLE_SLOTS = ["date", "start_time", "time", "song_year"]
PROPER_REFERRING_SLOTS = ["name", "start_time", "time", "contacts"]


def time_date_sort_key(data_str):
    """ The time and date in the context has canonical format. For example: '09:00' and 'Thu 2024-10-17'.
    We only need to remove the day to perform sorting.
    """
    return data_str.split(' ')[-1]


def slot_ranking_criteria(item, necessary_slots):
    return 0 if item in necessary_slots else 1


def prepare_slots_for_dialog(intent_input_values, intent_schema, context_entity=None, initial_slot=None, phenomena=None):
    '''This function return 3 slot-value dictionaries.'''
    if context_entity:  # For context interaction, only sample a referring slot. Don't touch the input slot.
        context_entity_slots = list(context_entity.keys())
        if intent_schema['can_refer_to_input_slot']:
            referring_slot = random.choice(context_entity_slots)
        else:
            for slot in list(intent_input_values.keys()):  # Should be either 0 or 1 slot in input
                context_entity_slots.remove(slot)
            referring_slot = random.choice(context_entity_slots)
        referring_slot_value = {referring_slot: context_entity[referring_slot]}
        return intent_input_values, None, referring_slot_value

    else:  # For non-context situation, arrange initial and remaining slots.
        # Minimum initial slots
        initial_input_slots = copy.copy(intent_schema['minimum_initial_slots'])
        # Add compositional matching slot, as we would like it to be in the first utterance.
        # <--?--> Do we really want this? Or shall we turn it into sequential compositional case?
        if initial_slot:
            initial_input_slots += initial_slot

        # Sample from the rest of the available slots, based on the minimum_input_slot_number
        available_slots = list(set(intent_input_values.keys()) - set(initial_input_slots))
        minimum_optional_slot_number = max(intent_schema['minimum_input_slot_number'] - len(initial_input_slots), 0)
        sample_initial_slot_size = random.randint(minimum_optional_slot_number, len(available_slots))
        if phenomena != 'compositional':
            initial_input_slots += random.sample(available_slots, sample_initial_slot_size)
        initial_input_slot_values = {key: intent_input_values[key] for key in initial_input_slots}
        # The rest of slots (The intent sampler has made sure it fully contain all necessary slots)
        remaining_necessary_slots = list(set(intent_input_values.keys()) - set(initial_input_slots))
        # Re-order the remaining slots such that the assistant always ask the more important slots first
        necessary_slots = intent_schema['required_slots']
        remaining_necessary_slots.sort(key=lambda item: slot_ranking_criteria(item, necessary_slots))
        remaining_necessary_slot_values = {slot: intent_input_values[slot] for slot in
                                           remaining_necessary_slots}  # Since Python 3.7, dict also maintain order

        return initial_input_slot_values, remaining_necessary_slot_values, None


def check_service_rankable(service):
    service_schema = Schema.get_service_schema(service)
    rankable_slots = [slot['name'] for slot in service_schema['slots'] if slot['name'] in FULL_RANKABLE_SLOTS]
    return len(rankable_slots)!=0


def get_complex_referral_action(intent, context) -> Action:
    service = intent.service
    context_entity_index = intent.context_entity_index
    service_schema = Schema.get_service_schema(service)
    rankable_slots = [slot['name'] for slot in service_schema['slots'] if slot['name'] in FULL_RANKABLE_SLOTS]
    full_slots = [slot['name'] for slot in service_schema['slots']]
    ranking_slot = random.choice(rankable_slots)
    checking_slot = list(intent.input_slot_values.keys())[0] if intent.input_slot_values else None

    full_slots.remove(ranking_slot)
    if checking_slot and checking_slot in full_slots:
        full_slots.remove(checking_slot)
    # condition_slot = random.choice(full_slots)
    # condition_slot_value = {condition_slot: context[service][context_entity_index][condition_slot]}
    filtered_context_entities = [e for e in context[service] if ranking_slot in e]
                                #  if condition_slot in e and e[condition_slot] == condition_slot_value[condition_slot]]
            
    sorted_filtered_context_entities = sorted(filtered_context_entities,
                                              key=lambda x: time_date_sort_key(x[ranking_slot]))
    ranking_index = sorted_filtered_context_entities.index(context[service][context_entity_index])

    return Action(action_name="get_{}".format(service), 
                  arguments={"ordered_by":ranking_slot, "index":ranking_index},
                  referral_event_index=intent.context_entity_index,) # **condition_slot_value}, 
                #   item_index=str(ranking_index))
    

def sample_revised_intent(original_intent: IntentValues, context):
    revised_input_slot = random.choice(list(original_intent.input_slot_values.keys()))
    original_input_value = original_intent.input_slot_values[revised_input_slot]
    revised_intent = copy.deepcopy(original_intent)
    cnt = 0
    while revised_intent.input_slot_values[revised_input_slot] == original_input_value:
        revised_intent.input_slot_values[revised_input_slot] = None
        populate_intent_slot_values(revised_intent, context=context)
        cnt += 1
        if cnt >1:    # When it cannot find new value from context, try to find one in schema potential_values 
            service_schema = Schema.get_service_schema(original_intent.service)
            potential_values = copy.copy(service_schema.get_slot(revised_input_slot).potential_values)
            if original_input_value in potential_values and len(potential_values)>=2:
                potential_values.remove(original_input_value)
                revised_intent.input_slot_values[revised_input_slot] = random.choice(potential_values)
                populate_intent_slot_values(revised_intent, context=context)
        if cnt == 3:    # If still same slot value, then just give up, as user can make mistake as well.
            break

    return revised_input_slot, revised_intent


def check_if_target_slot_included(target_slot, slots):
    if isinstance(slots, dict) or isinstance(slots, list):
        return target_slot in slots
    else:
        return target_slot == slots


def get_referring_action(plot, intent, context, referring_slot_value):
    '''Ideally should be called only once'''
    # <--Local Phenomena-->: Complex referral
    if check_service_rankable(intent.service) and random.random() > 0.7:   
            plot.local_phenomena.append('complex_referral')   
            referral_action = get_complex_referral_action(intent, context)
    # Normal referral
    else:   
        referral_action = Action(
            action_name="get_{}".format(intent.service),
            arguments=referring_slot_value,
            referral_event_index=intent.context_entity_index,
            max_num_arguments=1,
        )
    return referral_action


def get_proper_referral_action(intent, context):
    '''Proper referring expression used by system'''
    context_entity = context[intent.service][intent.context_entity_index] 
    context_entity_slots = list(context_entity.keys())
    for slot in PROPER_REFERRING_SLOTS:
        if slot in context_entity_slots:
            proper_referring_slot_value = {slot: context_entity[slot]}
            return Action(action_name="get_{}".format(intent.service), 
                          arguments=copy.deepcopy(proper_referring_slot_value), 
                          referral_event_index=intent.context_entity_index)
    raise ValueError('No proper referral slot for {}-{}'.format(intent.service, intent.intent))


def get_self_correction_action(intent, revised_intent, revised_input_slot):
    revised_input_slot_values = {revised_input_slot: revised_intent.input_slot_values[revised_input_slot]}
    correction_action = Action(action_name='self_correction', arguments=copy.deepcopy(revised_input_slot_values))
    intent.output_slot_values = revised_intent.output_slot_values
    intent.input_slot_values = revised_intent.input_slot_values
    eligible_for_revision = False
    return correction_action, eligible_for_revision


def insert_summarise_dialog_turn(plot, intent):
    output_slot_values = intent['output_slot_values'][0]    # Should be a list of 1 result. No return_list = True case.
    plot.system_actions.append([MetaAction(default_action=Action(
                                                action_name="inform_summary", 
                                                arguments=copy.deepcopy(output_slot_values)))])
    plot.system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=['summarisation']))


def insert_summarise_further_dialog_turn(plot, intent, intent_schema):
    # select_index = random.randint(0, len(intent.output_slot_values) - 1)
    # request should refer with a emphasis slot
    emphasis_slots = copy.copy(intent_schema['summary_emphasis_slots'])
    random.shuffle(emphasis_slots)

    dict_items = list(intent.summary_further_slot_values['slot_values'].items())
    random_key, random_value = random.choice(dict_items)
    refer_slot_value = {random_key: random_value}
    for slot in emphasis_slots:
        if slot in intent.summary_further_slot_values['slot_values']:
            refer_slot_value = {slot: intent.summary_further_slot_values['slot_values'][slot]}
            break
    plot.user_actions.append([Action(action_name="request_details_for_datapoint",
                arguments={'datapoint': Action(action_name="refer_by", arguments=refer_slot_value )})])
    plot.system_actions.append([MetaAction(default_action=Action(
                                        action_name="inform_result", 
                                        arguments=copy.deepcopy(intent.summary_further_slot_values['slot_values'])))])
    plot.system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=[]))


def insert_ask_confirmation_dialog_turn(plot, intent, context, referral_action=None):
    # But if context related intent, such as delete, and check, the input_slot_values should be key:None
    core_user_action = Action(action_name=intent.intent, arguments=copy.deepcopy(intent.input_slot_values)) 
    if referral_action:
        reporting_user_action_mirroring = core_user_action
        reporting_user_action_proper = copy.deepcopy(core_user_action)
        reporting_user_action_mirroring.referral_action = referral_action
        reporting_user_action_proper.referral_action = get_proper_referral_action(intent, context)
        plot.system_actions.append([MetaAction(default_action=Action(action_name="ask_confirm", arguments={'':reporting_user_action_proper}),
                                            special_mirroring_action=Action(action_name="ask_confirm", arguments={'':reporting_user_action_mirroring}))])
    else:
        plot.system_actions.append([MetaAction(default_action=Action(action_name="ask_confirm", arguments={'':core_user_action}))])
    plot.system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=[]))


def insert_inform_results_dialog_turn(plot, intent):
    output_slot_values = intent['output_slot_values'][0]    # Should be a list of 1 result. No return_list = True case.
    plot.system_actions.append([MetaAction(default_action=Action(
                                                action_name="inform_result", 
                                                arguments=copy.deepcopy(output_slot_values)))])
    plot.system_response_style.append(SystemResponseStyle(verbosity='verbosity_high', additional=[]))


def insert_notify_dialog_turn(plot, intent, context, referral_action=None):
    intent_schema = Schema.get_intent_schema(intent.service, intent.intent)
    core_user_action = Action(action_name=intent.intent, arguments=copy.deepcopy(intent.input_slot_values)) 
    if referral_action:
        reporting_user_action_mirroring = core_user_action
        reporting_user_action_proper = copy.deepcopy(core_user_action)
        reporting_user_action_mirroring.referral_action = referral_action
        reporting_user_action_proper.referral_action = get_proper_referral_action(intent, context)
        plot.system_actions.append([MetaAction(
                                    default_action=Action(action_name="notify_done", arguments={'':reporting_user_action_proper}), 
                                    special_mirroring_action=Action(action_name="notify_done", arguments={'':reporting_user_action_mirroring}),
                                    special_low_verbosity=True)]) 
    else:
        plot.system_actions.append([MetaAction(
                                    default_action=Action(action_name="notify_done", arguments={'':core_user_action}), 
                                    special_low_verbosity=True)]) 
    plot.system_response_style.append(
        SystemResponseStyle(verbosity='verbosity_low' if intent_schema['require_confirmation'] else 'verbosity_high', additional=[]))


def generic_intent_plot_generator(intent: IntentValues, context: dict, phenomena=None) -> IntentPlot:
    """ Generate a dialog plot resolving a single plot. This plot may be later combined with other plots.
    """
    plot = IntentPlot(
        user_actions=[],
        system_actions=[],
        system_response_style=[],
        local_phenomena=[],
    )

    intent_schema = Schema.get_intent_schema(intent.service, intent.intent)
    # <--Local Phenomena-->: Self-revision
    eligible_for_revision, revised_input_slot = False, None
    if intent_schema.require_input_values and random.random()>0.9:
        plot.local_phenomena.append('self-revision')
        revised_input_slot, revised_intent = sample_revised_intent(intent, context)

    # Check if the intent needs context interaction 
    if intent_schema['require_context']:  
        sampled_context_entity = context[intent.service][intent.context_entity_index] 
    else: sampled_context_entity = None

    # Arrange the Dialog flow by assigning slots
    initial_input_slot_values, remaining_necessary_slot_values, referring_slot_value = prepare_slots_for_dialog(
        intent_input_values=copy.deepcopy(intent.input_slot_values),
        intent_schema=intent_schema,
        context_entity=sampled_context_entity,
        initial_slot=intent.initial_slot,
        phenomena=phenomena
    )
    eligible_for_revision = check_if_target_slot_included(revised_input_slot, initial_input_slot_values)

    # Dialog Part 1: Start with the main intent action 
    initial_user_action = Action(action_name=intent.intent, arguments=copy.deepcopy(initial_input_slot_values)) 
    # Self-correction check
    if eligible_for_revision and random.random()>0.8:  
        correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
        initial_user_action.attribute = correction_action

    if referring_slot_value:
        referral_action = get_referring_action(plot, intent, context, referring_slot_value)
        initial_user_action.referral_action = referral_action
    else: referral_action = None
    plot.user_actions.append([initial_user_action])

    # Dialog Part 2 (optional): Slot filling loop
    if remaining_necessary_slot_values:
        for slot, value in remaining_necessary_slot_values.items():
            # eligible_for_revision = check_if_target_slot_included(revised_input_slot, initial_input_slot_values)   # reset correction eligibility
            plot.system_actions.append([MetaAction(default_action=Action(action_name="ask_user_for", arguments=copy.copy({slot: None})))])
            plot.system_response_style.append(SystemResponseStyle(verbosity='verbosity_mid', additional=[]))
            user_act = Action(action_name="inform_value", arguments=copy.copy({slot: value}))
            # Self-correction check
            if eligible_for_revision and random.random() >0.8: 
                correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
                user_act.attribute = correction_action             
            plot.user_actions.append([user_act])

    # Dialog Part 3 (optional): Branch for searching intents: Report multiple search results -> selection dialog
    if intent_schema['return_list']:  
        insert_summarise_dialog_turn(plot, intent)
        # Optional turn: requesting more information on a specific result
        if random.random() > 0.5:
            insert_summarise_further_dialog_turn(plot, intent, intent_schema)
        if eligible_for_revision:
            correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
            plot.user_actions.append([correction_action])
            insert_summarise_dialog_turn(plot, intent)
        return plot

    # Dialog part 4 (confirmation): Ask for confirmation, usually for irreversiable intent operation
    if intent_schema['require_confirmation']:
        insert_ask_confirmation_dialog_turn(plot, intent, context, referral_action)
        if eligible_for_revision: 
            correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
            plot.user_actions.append([correction_action])
            insert_ask_confirmation_dialog_turn(plot, intent, context, referral_action)
        plot.user_actions.append([Action(action_name="confirm")])

    # Dialog part 5: A notification of done. Brief summary of what have been done by the system
    if intent.output_slot_values[0] != {} or intent_schema['check_on_input']:
        insert_inform_results_dialog_turn(plot, intent)
        if eligible_for_revision: 
            correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
            plot.user_actions.append([correction_action])
            insert_inform_results_dialog_turn(plot, intent)  
    else:
        insert_notify_dialog_turn(plot, intent, context, referral_action)
        if eligible_for_revision: 
            correction_action, eligible_for_revision = get_self_correction_action(intent, revised_intent, revised_input_slot)
            plot.user_actions.append([correction_action])
            insert_notify_dialog_turn(plot, intent, context, referral_action)

    return plot
