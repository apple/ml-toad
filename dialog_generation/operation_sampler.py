#
# For licensing see accompanying LICENSE file.
# Copyright (C) 2024 Apple Inc. All Rights Reserved.
#
import logging

from .dataclass import Operation
from .intent_sampler import sample_intent, IncompatibleContext
from .schema_utils import Schema


def get_operation(context: dict, phenomenon: str, service: str = None, intent: str = None) -> Operation:
    """ Get an Operation (which consists of one or more IntentValues).
    (`service` only works when phenomenon is 'none'.)
    """
    while True:
        try:
            if phenomenon == 'compound':  # For phenomenon that requires two intents
                sampled_intent_1 = sample_intent(context)
                sampled_intent_2 = sample_intent(context)
                operation = Operation(
                    phenomena=phenomenon,
                    intent_values=[sampled_intent_1, sampled_intent_2]
                )
            elif phenomenon == 'compositional':
                compositional_intent = Schema.sample_compositional_intent()
                inner_intent = sample_intent(
                    context,
                    service=compositional_intent.inner[0].service_name,
                    intent=compositional_intent.inner[1].name,
                    output_slot=compositional_intent.inner_slot,
                )
                outer_intent = sample_intent(
                    context,
                    service=compositional_intent.outer[0].service_name,
                    intent=compositional_intent.outer[1].name,
                    input_slot=compositional_intent.outer_slot,
                )
                outer_intent.matching_slot = compositional_intent.outer_slot
                outer_intent.initial_slot = [compositional_intent.outer_slot]
                inner_intent.matching_slot = compositional_intent.inner_slot
                operation = Operation(
                    phenomena=phenomenon,
                    intent_values=[outer_intent, inner_intent]
                )
            else:  # For single intent case
                sampled_intent = sample_intent(context, service, intent)
                operation = Operation(
                    phenomena=phenomenon,
                    intent_values=[sampled_intent],
                )
            return operation
        except IncompatibleContext as e:
            logging.warning(f"Retrying due to: {e}")
            pass
