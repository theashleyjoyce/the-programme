# Agent design — source material for Report section 4 and the slide diagram

Rubric, section 4 (10 pts): what each agent does, what tools it can use, how
they are organised and who hands work to whom, with a diagram; which models and
why; and one real run traced step by step with screenshots.

Keep this out of the public About page. It is too technical for someone
choosing a bar, and it is exactly what the report is graded on.

---

## The shape of it

Five agents in two tiers. The point of the split is cost and speed: the
expensive work runs once and is shared by everyone, instead of being repeated
for every visitor.

```
        OFFLINE — runs on a refresh, not per visitor
        ──────────────────────────────────────────────────────────
          SCOUT ──────────> RESEARCHER ──────────> WRITER
          reads the city's   finds each venue's     writes the entry
          editorial listings  rooms, capacities,     that appears on
          by neighborhood     settings, policies     the card
            │                   │                      │
            └───────────────────┴──────────────────────┘
                                ▼
                        data/*.json   (committed to the repo)
                                │
        ──────────────────────────────────────────────────────────
        AT REQUEST TIME — runs per visitor
                                │
   you type ──> CONCIERGE ──> Brief ──> PLANNER ──> Night ──> page
   a vibe       (free text     (typed    (no model,   (typed
                to structure)  request)  pure Python)  object)
                                              │
                                   cannot cover it?
                                              ▼
                                           EDITOR
                                  (plans the night itself,
                                   with web search)
```

## Each agent

| Agent | When | Tools | Output |
|---|---|---|---|
| **Scout** | offline | `web_search` | Candidate venues per neighborhood, with category, price band, group policy, website, coordinates, and which publications recommended it |
| **Researcher** | offline | `web_search` | Rooms and capacities per venue, each with a citation. Reports conflicting published figures rather than picking one |
| **Writer** | offline | none | The one or two sentence entry on each card, plus `order_this` |
| **Concierge** | per request | none | A typed `Brief` from free text. Skipped entirely when the form already supplies everything |
| **Editor** | per request, fallback | `web_search` | A whole `Night` when local data cannot cover the request |

**PLANNER is not an agent**, and that is the design decision worth defending in
the report. Choosing venues is filtering, sequencing is arithmetic, and the
prose about a venue does not change between visitors. None of that needs a
model, so none of it uses one.

## Models, and why

`gpt-5.6-luna` throughout, via a direct OpenAI client. The assignment names
`gpt-6-luna` on the course Portkey key; that key is rejected by the gateway on
every authentication method tried, and the instructor has already approved the
substitution for coursework. The app still supports both and falls back
automatically, so a grader with a working course key is covered.

Structured outputs everywhere: every agent returns a schema-validated object,
never free text to be parsed.

## What this bought — measure before and after

| | Before | After |
|---|---|---|
| Plan, cached data | ~25 s | **~1 ms** |
| Plan, needs the fallback | ~25 s | ~22 s |
| Model calls per plan | 2 | 0 to 1 |
| Tokens per plan | ~30,000 | 0 to ~1,350 |
| Cost per plan | ~$0.056 | **$0.00 to $0.002** |

The honest tradeoff, which the Tokenomics row asks about directly: cached copy
is written per venue, not per request, so a stop's description does not know
that this particular visitor said "birthday, eight of us". The connective line
is still written per request, and a real city guide works the same way. The
Infatuation writes one review per restaurant, not one per reader.

## The traced run to screenshot

Use a request that stays on the fast path, and one that falls back, so the
report can show both:

1. **Fast:** filters only, Dinner + Drinks, Manhattan. Zero model calls.
2. **Fallback:** "jazz night with good food". Concierge runs, local data cannot
   cover it, Editor plans it with web search.

For each: the search page, the working page, the finished night, and the
colophon showing measured tokens. `output/spend_ledger.json` has the real
numbers for every call.

## Defences worth naming here as well as in section 6

The Editor's output lands in a lenient draft, then a repair step fills what it
can from our own data and **drops any stop it cannot attribute**. So the
sourcing rule is enforced after generation rather than trusted during it, and a
missing field costs one stop instead of the whole plan.
