#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import argparse
import json
import os
from textwrap import dedent
from pathlib import Path

from dialog_generation.dataclass import MetaAction, Action
from utilities.async_openai_api import OpenAIRequestManager
from utilities.llm_synthesis_utils import environment


def load_jsonl(file_path):
    data = []
    with open(file_path, 'r') as file:
        for line in file:
            if line!='\n':
                try:
                    data.append(json.loads(line))
                except:
                    print('Error in loading line:')
                    print(line)
    print('Loading raw data length: {} from {}'.format(len(data), file_path))
    return data


def filter_nan_data(data):
    filtered_data = []
    for d in data:
        if len(d) <= 2:
            continue
        filtered_data.append(d)
    print('Filtered {} nan data; {} examples left.'.format(len(data)-len(filtered_data) , len(filtered_data)))
    return filtered_data


######################### Format and slot check #########################
def extract_slot_values_from_action(action):
    values = []
    for val in action.arguments.values():
        if isinstance(val, Action):
            values += extract_slot_values_from_action(val)
        else:
            if isinstance(val, str):
                values.append(val)
    return values


def fuzzy_match_slot_values(val, utterance):
    val = val.lower()
    if val in ['true', 'false', 'yes', 'no']:
        return True
    # if val is a string number
    if val.isdigit():
        return True
    # if val is a string time
    if ':' in val:
        return True
    # if val is a string date
    if '-' in val:
        return True
    # if val is a string operation
    if '_' in val:
        return True

    utterance = utterance.lower()
    words = val.replace('_',' ').split()
    # if the words is a long message
    if len(words)>10 or 'message' in utterance:
        return True
    
    word_matched_count = 0
    for word in words:
        if word in utterance:
            word_matched_count += 1
    if word_matched_count/len(words)>=0.5:
        return True
    else:
        return False


def filter_misformat_data(data):
    filtered_data = []
    for idx, datapoint in enumerate(data):
        good_data = True
        for turn in range(len(datapoint['dialog_action_user'])):
            values = []
            for action in datapoint['dialog_action_user'][turn]:
                a = Action.convert_from_dict(action)
                values += extract_slot_values_from_action(a)
            cur_utterance = datapoint['conversation'][turn*2]
            for val in values:
                if not fuzzy_match_slot_values(val, cur_utterance):
                    good_data = False

        for turn in range(len(datapoint['dialog_action_system'])):
            values = []
            for meta_action in datapoint['dialog_action_system'][turn]:
                a = Action.convert_from_dict(meta_action['default_action'])
                values += extract_slot_values_from_action(a)
            # cur_utterance = datapoint['conversation'][turn*2+1]
            cur_utterance_1 = datapoint['response_options'][turn]['verbosity_high no_mirroring']
            cur_utterance_2 = datapoint['response_options'][turn]['verbosity_high mirroring']
            for val in values:
                if not fuzzy_match_slot_values(val, cur_utterance_1) and not fuzzy_match_slot_values(val, cur_utterance_2):
                    good_data = False
        if good_data:
            filtered_data.append(datapoint)
    
    print('Filtered {} mis-formated data; {} examples left.'.format(len(data)-len(filtered_data) , len(filtered_data)))
    return filtered_data


#######################################################################################
def extract_plot_from_datapoint(datapoint):
    user_actions = []
    system_actions = []
    for line in datapoint['dialog_action_user']:
        actions_line = []
        for action in line:
            act = Action.convert_from_dict(action)
            actions_line.append(act.realize())
        user_actions.append(actions_line)

    for line in datapoint['dialog_action_system']:
        actions_line = []
        for action in line:
            act = MetaAction.convert_from_dict(action)
            actions_line.append(act.realize())
        system_actions.append(actions_line)

    return user_actions, system_actions


def combine_act_utt_pairs(datapoint, user_actions, system_actions):
    user_act_utt_pairs = []
    system_act_utt_pairs = []
    for idx, turn_utt in enumerate(datapoint['conversation']):
        if idx%2==0:
            user_act_utt_pairs.append({'action': user_actions[idx//2], 'utterance': turn_utt})
        else:
            system_act_utt_pairs.append({'action': system_actions[idx//2], 'utterance': turn_utt})
    return user_act_utt_pairs, system_act_utt_pairs


def filter_inconsistent_data_by_llm(data):
    '''
    Will produce a temp_buffer.jsonl file to store the results.
    '''
    prompts = []
    for id in range(len(data)):
        user_actions, system_actions = extract_plot_from_datapoint(data[id])
        user_act_utt_pairs, system_act_utt_pairs = combine_act_utt_pairs(data[id], user_actions, system_actions)
        template_str = dedent("""\
            Please check the consistency between the actions and the corresponding utterances for the following dialog. They might refer to the context below.
            
            Context: {{ context }}
            {% for usr_turn in usr_turn_pairs %}
            User: {{ usr_turn }}
                            
            System: {{ sys_turn_pairs[loop.index0] }}
            {% endfor %}
            Response: """)
            # If you think they are consistent, please type "consistent". If not, please type "inconsistent".

        prompt_template = environment.from_string(template_str)
        prompt = prompt_template.render(
            context=data[id]['context'],
            usr_turn_pairs= user_act_utt_pairs,
            sys_turn_pairs= system_act_utt_pairs,
        )
        prompts.append(prompt)


    def response_extractor(response):
        llm_output = response.choices[0].message.content.strip()
        return {'llm_output': llm_output}


    openai_manager = OpenAIRequestManager(response_extractor)
    openai_manager.multi_threading_openai_api_call(prompts=prompts, max_workers=5)

    check_results = load_jsonl('temp_buffer.jsonl')
    check_results = sorted(check_results, key=lambda x: x['id'])
    
    filtered_data = []
    for idx, result in enumerate(check_results):
        if 'inconsistent' in result['llm_output'].lower():
            continue
        filtered_data.append(data[idx])

    print('Filtered {} inconsistent data; {} examples left.'.format(len(data)-len(filtered_data) , len(filtered_data)))
    return filtered_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', type=str, help='Path to synthesized data.', default=Path('data/dialogs'))
    parser.add_argument('--output_dir', type=str, help='Path to save the filtered synthesized data.', default=Path('data/filtered_dialogs'))
    args = parser.parse_args()

    file_names = ['none.jsonl', 'compositional.jsonl', 'compound.jsonl']
    args.output_dir.mkdir(exist_ok=True)

    for fn in file_names:
        path = args.input_dir / fn
        if not path.is_file():
            continue
        data = load_jsonl(path)
        filtered_data = filter_nan_data(data)
        filtered_data = filter_misformat_data(filtered_data)

        # LLM inconsistency check
        filtered_data = filter_inconsistent_data_by_llm(filtered_data)

        saving_path = os.path.join(args.output_dir, fn)
        with open(saving_path, 'w') as file:
            for d in filtered_data:
                file.write(json.dumps(d, ensure_ascii=False)+'\n')
