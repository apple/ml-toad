#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import json
from textwrap import dedent

from utilities.llm_synthesis_utils import call_openai_chat_completion, environment
from .dataclass import SystemResponseStyle


def conversation_to_text(conversation):
    # input is a list of string, output should be one string with line breaking.
    conversation_with_role = []
    for idx, conv in enumerate(conversation):
        if idx % 2 == 0:
            conversation_with_role.append('user: ' + conv)
        else:
            conversation_with_role.append('assistant: ' + conv)

    return "\n".join(conversation_with_role)


def get_system_response(prompt=None, messages=None) -> str:
    if not messages:
        messages = [
            {'role': 'system',
             'content': "You are a helpful assistant. Please follow the user's instructions and examples' format."},
            {'role': 'user', 'content': prompt},
        ]
    max_retries, retry_count = 3, 0
    while retry_count < max_retries:
        try:
            llm_output, _ = call_openai_chat_completion(
                messages,
                max_tokens=750,
                temperature=0.2,
                top_p=0.9,
                frequency_penalty=0.3,
                # 1 encourages diverse response, 0 allows repeating frequently.
                presence_penalty=0.2
                # 1 encourages using more provided keywords, 0 allows less constrained by the given context.
            )
            json.loads(llm_output)
            break
        except:
            retry_count += 1
    if retry_count == max_retries:
        print(llm_output)
        raise AssertionError("LLM cannot produce output in JSON format.")
    return llm_output


def get_user_response(prompt=None, messages=None):
    if not messages:
        messages = [
            {'role': 'system',
             'content': "You are a helpful assistant. Please follow the user's instructions and examples' format."},
            {'role': 'user', 'content': prompt},
        ]
    max_retries, retry_count = 3, 0
    while retry_count<max_retries:
        try:
            llm_output, _ = call_openai_chat_completion(
                messages,
                max_tokens=512,
                temperature=0.3,
                top_p=0.9,
                frequency_penalty=0.3,
                # 1 encourages diverse response, 0 allows repeating frequently.
                presence_penalty=0.5
                # 1 encourages using more provided keywords, 0 allows less constrained by the given context.
            )
            json.loads(llm_output)
            break
        except:
            retry_count += 1
    if retry_count == max_retries:
        print(llm_output)
        raise AssertionError("LLM cannot produce output in JSON format.")
    
    return llm_output


def generate_single_dialog(buffer):
    user_prompt_template = dedent("""\
        You are a smartphone user and you are testing your virtual assistant on your phone by engaging in a multi-turn conversations with it. 
        Here is your personal introduction: {{ user_intro }}

        Instructions:
        1. You need to communicate with the assistant following the guidance of "actions".
        2. Based on the introduction, think about what speech habit you should have and communicate with this pattern.
        3. The "utterance" should be brief.
        4. You must return in JSON format, following the provided examples.

        The context information is: {{ context }}.
        
        You are using these apps: {{ situation }}.

        Example 1:
        user: {"actions": ["get_reminders(time="09:00").reminders_modify(name=get_calendar_events(ordered_by="date", index=2).calendar_events_check(name).name)"], "utterance": "Please update the name of my 9am reminder to match the title of the 2nd earlist event on my calendar."}
        Example 2:
        user: {"actions": ["reminders_create(date=get_reminders(time="09:00").reminders_check(date).date)"], "utterance": "I'd like to create a new reminder same date with my 9 am reminder."}
        
        Begin conversation (you are identified as "user").
        user: {"actions": ["hello()"], "utterance": "Hi."}
        assistant: {"actions": ["offer_help()"], "utterance": "Hello, how can I help?"}
        {% if conversation | length>0 %}{{ conversation | conversation_to_text }}{% endif %}

        The "actions" you need to follow is {{ dialog_action_user_realized[cur_turn_counter] | tojson }}. Please phrase the action into a realistic utterance. {{ user_style_instruction }}
        user:\
    """)
    system_prompt_template = dedent("""\
        You are a virtual assistant. Your goal is to assist the user based on their requests and provide helpful responses. 
                                    
        Instructions:
        1. Maintain a friendly and professional personality throughout the conversation.
        2. Your responses should be simple, natural, and concise, using minimum words necessary.
        3. Follow the provided context information and adhere to the specified "actions."
        4. You must return in JSON format, following the provided examples.

        The user is interacting with these apps: {{ situation }}.

        Here is some relevant context: {{ context }}.

        Conversation Example:
        Begin conversation (you are identified as "assistant").
        user: {"actions": ["hello()"], "utterance": "Hi."}
        assistant: {"actions": ["offer_help()"], "utterance": "Hello, how can I help?"}
        {% if conversation | length>0 %}{{ conversation | conversation_to_text }}{% endif %}

        Next Action:
        Your next actions are {{ system_action_temp | tojson }}. Generate an appropriate response message. {{ system_style_instruction }}

        assistant:\
    """)

    environment.filters['conversation_to_text'] = conversation_to_text
    user_prompt_template = environment.from_string(user_prompt_template)
    system_prompt_template = environment.from_string(system_prompt_template)

    system_response_style_prompts = {
        'verbosity_low': 'The message must only have a couple of words, such as "when", "how long" or "done".',
        'verbosity_mid': 'The message must replace the nouns or noun phrases mentioned by user with pronouns, such as "it", "that" and "its".',
        'verbosity_high': 'The message should use full expression with name if available rather than pronouns.',
        'mirroring': "Use the user's noun phrase or verb expressions when possible.",  # It should refer to the event or verbs by the same user's expression.",
        'no_mirroring': "Ignore all previous dialog.",  # Do not use the expression used by the user.
        'summarisation': 'Please respond with a coherent summary.',
        'complex': 'Please respond with a sentence using complex sentence structure.',
        'kid_friendly': "The message should use simple words with less syllables and safe language as if talking to a children."
    }
    system_grounding_options = ['verbosity_low', 'verbosity_mid', 'verbosity_high']
    system_mirroring_option = ['mirroring', 'no_mirroring']

    buffer['dialog_action_user_realized'] = [[act.realize() for act in actions] for actions in buffer['dialog_action_user']]
    buffer['response_options'] = []
    total_turn = len(buffer['dialog_action_user']) + len(buffer['dialog_action_system'])
    cur_turn = 0
    for i in range(10):
        user_prompt = user_prompt_template.render(buffer)
        response = get_user_response(user_prompt)
        buffer['conversation'].append(response)

        cur_turn += 1
        if cur_turn >= total_turn:
            break

        if buffer['if_full_response_options']:      # Generate all combinations of verbosity and mirroring
            system_response_options = {}
            optimal_style: SystemResponseStyle = buffer['system_optimal_style'][buffer['cur_turn_counter']]
            additional_styles = optimal_style.additional
            for grounding_option in system_grounding_options:
                # buffer['system_style_instruction'] = grounding_option
                for mirroring_option in system_mirroring_option:
                    temp_style = SystemResponseStyle(verbosity=grounding_option, mirroring=mirroring_option, additional=additional_styles)
                    buffer['system_style_instruction'] = temp_style.realize()  #' '.join([system_response_style_prompts[style] for style in system_response_style])

                    current_sys_actions = buffer['dialog_action_system'][buffer['cur_turn_counter']]
                    buffer['system_action_temp'] = [meta_action.realize((grounding_option, mirroring_option)) for meta_action in current_sys_actions]
                    system_prompt = system_prompt_template.render(buffer)
                    response = get_system_response(system_prompt)
                    system_response_options[(grounding_option, mirroring_option)] = response
            buffer['response_options'].append(system_response_options)
            cur_optimal_style = (optimal_style.verbosity, "no_mirroring")  # (Optimal) verbosity and mirroring style to carry on the dialog.
            buffer['conversation'].append(system_response_options[cur_optimal_style])
            cur_turn += 1

        else:
            buffer['system_style_instruction'] =  buffer['system_optimal_style'][buffer['cur_turn_counter']].realize()
            current_sys_actions = buffer['dialog_action_system'][buffer['cur_turn_counter']]
            current_sys_style = buffer['system_optimal_style'][buffer['cur_turn_counter']].get_style_tuple()
            buffer['system_action_temp'] = [meta_action.realize(current_sys_style) for meta_action in current_sys_actions]
            system_prompt = system_prompt_template.render(buffer)
            response = get_system_response(system_prompt)
            buffer['conversation'].append(response)
            cur_turn += 1

        if cur_turn >= total_turn:
            break
        buffer['cur_turn_counter'] += 1

    return buffer


def generate_dialog_one_off(buffer):
    user_prompt_template = dedent("""\
        Instructions:
        1. You are a smartphone user and you need to communicate with your virtual assistant by engaging in a multi-turn conversations.
        2. Based on your personal introduction, think about what speech habit you should have and speak with this pattern.
        3. Your response should strictly follow the given actions. Take the nesting action as a clause and the slot value as an antecedent to generate a coherent and complex user query.

        Personal introduction: {{ user_intro }}
        
        You are using these apps: {{ situation }}.

        Conversation Example (you are identified as "user" and talking to "assistant").
        user actions: ["operation_on_device(operation=\\"turn_off\\", device=\\"heating\\")"]
        user: Can you please turn up the heating?
        assistant actions: ["request_information(home_space)"]
        assistant: Which room would that be?
        user action: ["inform_information(home_space=\\"study room\\")"]
        user: {"message": " In the study room"}

        New conversation:
        {% if conversation | length>0 %}{{ conversation | conversation_to_text }}{% endif %}
                                  
        You must return in JSON format and response base on the following action:
        user action: {{ dialog_action_user_realized[cur_turn_counter] | tojson }}.
        user: \
    """)
                                

    system_prompt_template_speedup = dedent("""\
        Instructions:
        1. You are a virtual assistant. Your goal is to assist the user to accomplish their goal.
        2. Your responses should strictly follow the given actions and be helpful, natural, professional and concise.
        3. Your response should strictly follow the corresponding "actions".

        The user is interacting with these apps: {{ situation }}.
                                            
        Style instruction:
        'verbosity_low': Your response must only have a couple of words, such as "when", "how long" or "done".
        'verbosity_mid': Your response should be a concise but complete sentence and must replace the nouns or noun phrases mentioned by user with pronouns, such as "it", "that" and "its".
        'verbosity_high': Your response should use full expressions with all the details.
        'mirroring': Your response should use the user's noun phrase or verb expressions when possible.
        'no_mirroring': Ignore all previous dialog. Do not affect by user expression.
        'summary': Your response should be a brief report of the given summary.

        Response Example:
        assistant actions: {"verbosity_low mirroring": ["notify_done()"], "verbosity_low no_mirroring": ["notify_done()"], "verbosity_mid mirroring": ["notify_done(operation_on_device(operation=\\"turn_off\\", device=\\"heating\\", home_space=\\"bedroom\\"))"], "verbosity_mid no_mirroring": ["notify_done(operation_on_device(operation=\\"turn_off\\", device=\\"heating\\", home_space=\\"bedroom\\"))"], "verbosity_high mirroring": ["notify_done(operation_on_device(operation=\\"turn_off\\", device=\\"heating\\", home_space=\\"bedroom\\"))"], "verbosity_high no_mirroring": ["notify_done(operation_on_device(operation=\\"turn_off\\", device=\\"heating\\", home_space=\\"bedroom\\"))"]}
        assistant: {"verbosity_low mirroring": "Turned off.", "verbosity_low no_mirroring": "Done.", "verbosity_mid mirroring": "I have turned off the heating in that room.", "verbosity_mid no_mirroring": "I have turned it off in that room.", "verbosity_high mirroring": "I have turned off the bedroom heating.", "verbosity_high no_mirroring": "Sure, I have turned off the heating in the bedroom."}

        Conversation history:
        {% if conversation | length>0 %}{{ conversation | conversation_to_text }}{% endif %}
        
        New turn:
        You should return in JSON format with 6 keys: ["verbosity_low mirroring", "verbosity_low no_mirroring", "verbosity_mid mirroring", "verbosity_mid no_mirroring", "verbosity_high mirroring", "verbosity_high no_mirroring"].
        assistant actions: {{ style_action_cur | tojson }}.
        assistant: \
    """)
    environment.filters['conversation_to_text'] = conversation_to_text
    user_prompt_template = environment.from_string(user_prompt_template)
    system_prompt_template = environment.from_string(system_prompt_template_speedup)

    system_grounding_options = ['verbosity_low', 'verbosity_mid', 'verbosity_high']
    system_mirroring_options = ['mirroring', 'no_mirroring']

    buffer['dialog_action_user_realized'] = [[act.realize() for act in actions] for actions in buffer['dialog_action_user']]
    buffer['response_options'] = []
    total_turn = len(buffer['dialog_action_user']) + len(buffer['dialog_action_system'])
    cur_turn = 0
    for i in range(10):
        user_prompt = user_prompt_template.render(buffer)
        response = get_user_response(user_prompt)
        # print(user_prompt)
        user_msg = json.loads(response)['message']
        buffer['conversation'].append(user_msg)
        # print('---------------------------------------------------')
        cur_turn += 1
        if cur_turn >= total_turn:
            break

        current_optimal_style = buffer['system_optimal_style'][buffer['cur_turn_counter']].realize_to_key()
        current_sys_actions = buffer['dialog_action_system'][buffer['cur_turn_counter']]
        style_actions = {}
        for v in system_grounding_options:
            for m in system_mirroring_options:
                key = v + ' ' + m
                style_actions[key] = [meta_action.realize(key) for meta_action in current_sys_actions]
        buffer['style_action_cur'] = style_actions

        system_prompt = system_prompt_template.render(buffer)
        # print(system_prompt)
        response = get_system_response(system_prompt)
        parsed_response = json.loads(response)
        buffer['conversation'].append(parsed_response[current_optimal_style])
        buffer['response_options'].append(parsed_response)
        cur_turn += 1

        if cur_turn >= total_turn:
            break
        buffer['cur_turn_counter'] += 1
    

def buffer_filter(buffer):
    contents = ['phenomena', 'local_phenomena', 'context', 'situation', 'services', 'intents', 'dialog_action_user',\
                'dialog_action_system', 'system_optimal_style', 'conversation', 'response_options', 'user_intro']
    buffer = {key:buffer[key] for key in contents}
    return buffer
    
