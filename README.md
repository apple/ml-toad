# TOAD

This software project accompanies the research paper, [TOAD: Task-Oriented Automatic Dialogs with Diverse Response Styles](https://arxiv.org/abs/2402.10137). **This paper has been accepted by ACL 2024.**

<p align="center">
<img src="resources/toad_icon.jpg" alt="Toad" width="200px" height="200px">
</p>

TOAD is a synthetic TOD dataset that simulates <ins>realistic app context interactions</ins> and provides <ins>multiple system response styles</ins> (verbosity & mirroring user expressions).


## Run Data Synthesis

**Preparation**:
- Install dependencies from `requirements.txt`.
- We use OpenAI Compatible API to make requests to LLMs. Set the environment variable `OPENAI_API_KEY`, `BASE_URL` (optional) and `ENGINE` (e.g. "gpt-3.5-turbo") to config the backend LLM. You can use a dotenv file.

**Synthesis**: The data synthesis pipeline is divided into 3 steps. The generated files will be stored in `data/`.

Step 1: Context generation

1. Run `python -m context_generation.occupation_generator` to synthesize `occupations.json` (you can skip this step and re-use the existing file).
2. Run `python -m context_generation.persona_generator` to synthesize `personas.jsonl` using occupations.
3. Run `python -m context_generation.context_generator` to synthesize `contexts.jsonl` using personas.

Step 2: Dialog generation

4. Run code in `dialog_generation` to synthesize dialogs based on contexts. Example command:

```bash
python -m dialog_generation.main \
    --phenomena='compound' \
    --output_dir='data/dialogs' \
    --number_of_data=1000 \
    --full_options_mode \
    --thread_num=15
```

- `--phenomena` specifies the phenomena to be used in dialog generation. It can be one of `compound`, `compositional`, `none`.   
- `--output_dir` specifies the path to save the generated dialogs.  
- `--number_of_data` specifies the number of dialogs to generate.  
- `--full_options_mode` asks for generating of all 6 response style options.   
- `--thread_num` specifies the number of threads to run in parallel. 

For how to customize dialog generation by modifying the `schema.json`, please refer to [the documentation in that directory](dialog_generation/README.md).

Step 3: Quality control

5. Run `python -m quality_control.main` to filter out inconsistent dialogs using the LLM.


## Citation
```
@inproceedings{liu2024toad,
    title = "{TOAD}: Task-Oriented Automatic Dialogs with Diverse Response Styles", 
    author = "Liu, Yinhong  and
      Fang, Yimai  and
      Vandyke, David  and
      Collier, Nigel",
    booktitle = "Findings of the Association for Computational Linguistics: ACL 2024",
    year = "2024",
    url = "https://arxiv.org/abs/2402.10137"
}
```
