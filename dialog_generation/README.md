# TOAD Dialog Generation Documentation

## Schema

You may edit `schema.json` to support new domains and new intents.
For intents that interact with the context, you may also need to update `context_loader.py`, which maps the output of the context generator to the contexts used by the dialog generator.

Properties in the schema:
- `require_context`: True for intents that need interaction with the context. The `context_event_index` in this case marks the event index the intent is interacting with.
- `return_list`: True for searching intents that return multiple search results. The `context_event_index` in this case labels which item is selected for the following-up dialog.
- `check_on_input`: This indicator is mainly for the 'check' intent, where only slot keys but not values are input, and the assistant should inform the slot values. The 'check' intent doesn't have a fixed `result_slots`, but it dynamically returns the value for the input slot.
