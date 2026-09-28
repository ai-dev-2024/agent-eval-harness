# Coding task comparison

24 attempts. Pass rates are task-macro-averaged. Missing usage is unknown.

| Model | Pass@1 | Pass@k | Mean (s) | Median (s) | Input / output tokens | Cost (USD) |
| --- | ---: | --- | ---: | ---: | --- | --- |
| mock-reference | 100.0% | 1: 100.0%, 2: 100.0% | 0.274 | 0.271 | unknown / unknown | unknown |
| mock-wrong | 0.0% | 1: 0.0%, 2: 0.0% | 0.309 | 0.308 | unknown / unknown | unknown |

## Per-task passes / attempts

| Task | mock-reference | mock-wrong |
| --- | ---: | ---: |
| arithmetic | 2/2 | 0/2 |
| intervals | 2/2 | 0/2 |
| json_path | 2/2 | 0/2 |
| lru_ttl | 2/2 | 0/2 |
| rate_limiter | 2/2 | 0/2 |
| roman | 2/2 | 0/2 |

Reported totals may be partial. Usage coverage (attempts with input/output/cost):

- mock-reference: 0/0/0 of 12.
- mock-wrong: 0/0/0 of 12.
