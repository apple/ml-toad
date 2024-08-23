#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import argparse
import json
import logging
import math
import multiprocessing.dummy
import traceback
import uuid
from pathlib import Path

from .context_loader import load_contexts, convert_context
from .dialog_generator import generate_single_dialog
from .operation_sampler import get_operation
from .plot_generator import get_initial_buffer
from .slot_value_sampler import populate_operation_slot_values


def generate_single_datapoint(setup, context, phenomena, if_full_response_options, service=None, intent=None):
    data_id = uuid.uuid4()
    buffer = {'id': str(data_id)}
    try:
        operation = get_operation(context, phenomena, service=service, intent=intent)
        populate_operation_slot_values(operation, context)
        logging.warning(f'{data_id} - Intent and parameters ready: {operation}')
        # Construct buffer
        buffer = get_initial_buffer(setup, context, operation=operation)
        buffer['if_full_response_options'] = if_full_response_options
        logging.warning(f'{data_id} - Intent plots ready.')
    except Exception as e:
        logging.error(f"{data_id} - Plot generation failed: {repr(e)}")
        # Get the traceback object
        tb = traceback.format_exc()
        # Print the traceback information
        logging.error("Traceback: "+tb)
        return buffer

    # Simulation
    try:
        generate_single_dialog(buffer)
        logging.warning(f'{data_id} - Dialog generation finished: {len(buffer["dialog_action_user"])+len(buffer["dialog_action_system"])} turns')
    except Exception as e:
        logging.error(f"{data_id} - Dialog generation failed: {repr(e)}")
        return buffer

    # Convert data into JSON-able format
    if buffer.get('dialog_action_user'):
        buffer['dialog_action_user'] = [[action.to_dict() for action in turn] for turn in buffer['dialog_action_user']]
    if buffer.get('dialog_action_system'):
        buffer['dialog_action_system'] = [[action.to_dict() for action in turn] for turn in buffer['dialog_action_system']]
    if buffer.get('system_optimal_style'):
        buffer['system_optimal_style'] = [style.to_dict() for style in buffer['system_optimal_style']]
    if buffer.get('response_options'):
        buffer['response_options'] = [{' '.join(k): v for k, v in turn.items()} for turn in buffer['response_options']]

    return buffer


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phenomena', type=str, help='The phenomena to simulate.', default='none')
    parser.add_argument('--output_dir', type=Path, help='The path to save the synthetic dataset.', default=Path('data/dialogs'))
    parser.add_argument('--number_of_data', type=int, help="How many number of datapoint to generate.", default=100)
    parser.add_argument('--erase_previous_data', action="store_true", help="Enable erasing previously saved data.")
    parser.add_argument('--full_options_mode', action='store_true', help="Enable generation all system response options.")
    parser.add_argument('--thread_num', type=int, help="Number of threads to use.", default=5)
    args = parser.parse_args()
    logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.WARNING)

    phenomena = args.phenomena
    contexts = load_contexts()
    expanded_contexts = (contexts * math.ceil(args.number_of_data / len(contexts)))[:args.number_of_data]
    seeded_setup = {
        'event_execute_count': 5,
        'user_speaking_speed': 'slow',
        'system_mirror_switch': False,
        'system_kid_switch': False,
    }

    def _generate_data_point(context):
        context = convert_context(context)
        buffer = generate_single_datapoint(seeded_setup, context, phenomena,
                                           if_full_response_options=args.full_options_mode)
        return buffer

    args.output_dir.mkdir(exist_ok=True)
    output_path = args.output_dir / f'{phenomena}.jsonl'
    mode = 'w' if args.erase_previous_data else 'a'

    num_completed = 0
    with open(output_path, mode) as fp:
        with multiprocessing.dummy.Pool(args.thread_num) as pool:
            for d in pool.imap(_generate_data_point, expanded_contexts):
                try:
                    fp.write(json.dumps(d, ensure_ascii=False))
                    fp.write("\n")
                except Exception as e:
                    logging.error(e)
                    logging.error(f"Failed to save data: {d}")
                fp.flush()
                num_completed += 1
