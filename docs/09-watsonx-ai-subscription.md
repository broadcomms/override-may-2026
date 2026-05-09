The right answer for OVERRIDE is **Essentials (pay-as-you-go, $0/month base)** — total expected dev cost over the next 23 days is well under $5. 

Here's the full math.

## Verified watsonx.ai pricing (as of May 2026)

### Tier structure

| Tier | Platform fee | Foundation model usage | Best for |
|---|---|---|---|
| **Free (Lite)** | $0 | 300,000 tokens/month total + 20 CUH/month + 100 docs/month text extraction | Playground, prototyping |
| **Essentials** | **$0/month base** + pay-per-token | Same per-token rates as Standard | **Active development on a budget** |
| **Standard** | **$1,050/month base** + pay-per-token | Same per-token rates as Essentials, plus enterprise extras (LoRA fine-tuning, custom model hosting, GPU on-demand) | Enterprise production |

### Per-token rates (apply to BOTH Essentials and Standard — same)

| Model | Input | Output | OVERRIDE uses |
|---|---|---|---|
| **`granite-4-h-small`** (Instruct) | **$0.06 / 1M tokens** | **$0.25 / 1M tokens** | reasoning + Fan Mode |
| **`granite-guardian-3-8b`** | **$0.20 / 1M tokens** (combined) | same | Pass-2 |
| **`granite-embedding-278m-multilingual`** | **$0.10 / 1M tokens** (combined) | same | regulation chunk retrieval |
| `granite-timeseries-ttm-r2` | $0.38 / 1M tokens | same | only if P2.2 ships |

Pricing source: [IBM watsonx.ai pricing page](https://www.ibm.com/products/watsonx-ai/pricing). Per the footnote, 1 Resource Unit (RU) = 1,000 tokens; "input" and "output" tokens are charged separately for Instruct, combined for Guardian and Embedding.

## OVERRIDE's actual per-session token burn

Based on observed pipeline behavior (5.1s end-to-end, 4 zones detected on the FastF1 fixture):

### Per-zone breakdown

| Stage | Direction | Tokens | Notes |
|---|---|---|---|
| Reasoning input | input | ~2,600 | lap_window (30 × ~40 tok) + zone + chunk + prompt |
| Reasoning output | output | ~400 | ReasoningOutput JSON |
| Embedding (query) | combined | ~100 | zone-type query string |
| Guardian × 2 criteria | combined | ~4,010 | criterion + lap context + reasoning + chunk |
| **Per zone (no retries)** | | **~7,110** | |
| **Per zone (1 retry on Pass-2)** | | **~14,220** | doubled call |
| **Per zone (worst case: 2 retries on each pass)** | | **~21,330** | |

### Per-session totals (typical 4 zones)

| Scenario | Total tokens | Cost on Essentials |
|---|---|---|
| Clean run, no retries | **~28,500** | $0.005 |
| Typical (some retries on 1-2 zones) | **~40,000** | $0.008 |
| Worst case (max retries everywhere) | **~85,000** | $0.018 |
| Plus Fan Mode for all 4 zones | **+6,000** | +$0.002 |

### One-time startup costs

| Item | Tokens | Frequency |
|---|---|---|
| Pre-embed 48 chunks (one-time per build) | ~28,800 | only when chunk corpus changes (G-4-style events) |
| Schema/regs.py module import | 0 | no cost |

## Daily budget table

### Free tier (300K tokens/month — current state)

| Daily allowance | Sessions/day at typical usage |
|---|---|
| 10,000 tokens/day (300K ÷ 30) | **~1 session per day** |
| Front-loaded (week 1 burn) | ~7 sessions, then drought |
| With pre-embedding refresh | Half a session less per refresh |

**Reality check:** You have ~23 days to submission and ~30-50 sessions of dev/test/recording work ahead. Free tier covers maybe 7-8 sessions total. **You'll hit the wall the way R18 just predicted.**

### Essentials ($0/month base + pay-per-token)

At typical OVERRIDE burn (~40K tokens per session, ~$0.008/session):

| Sessions per day | Daily cost | Monthly cost |
|---|---|---|
| 5 | $0.04 | $1.20 |
| 10 | $0.08 | $2.40 |
| 25 | $0.20 | $6.00 |
| 50 (heavy demo recording day) | $0.40 | $12.00 |

**For OVERRIDE's remaining 23 days at, say, 30 total sessions:**
- Total tokens: ~1.2M
- Reasoning (input+output): ~$0.20
- Guardian: ~$0.10
- Embedding: ~$0.005
- **Total dev spend: ~$0.30 — three quarters of a US dollar**

**Even worst-case heavy testing of 100 sessions over 23 days: ~$1-2 total.**

### Standard ($1,050/month base + same per-token rates)

Standard charges the **same per-token rates** as Essentials. The $1,050/month buys you:
- LoRA / QLoRA fine-tuning capability
- Custom foundation model hosting
- On-demand GPU model deployment ($4.43-$128/hour for various GPU configs)
- Synthetic data generator
- Advanced platform features

**OVERRIDE doesn't use any of those.** You're not fine-tuning Granite; you're not hosting a custom model; you're not deploying GPUs on-demand. Standard is for enterprises building proprietary models on top of watsonx — that's not OVERRIDE.

## Strategic recommendation: upgrade to Essentials, not Standard

**Cost ratio:** Essentials gets you everything OVERRIDE needs for **<$5 over the entire submission window**. Standard would cost **$1,050+ for the same outcome**. That's a 200×+ premium for features OVERRIDE doesn't use.

**Action:**
1. Go to [watsonx.ai pricing](https://www.ibm.com/products/watsonx-ai/pricing), upgrade to Essentials (pay-as-you-go, $0 base, requires credit card on file).
2. The same `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` keep working — no code changes.
3. Set a budget alert in IBM Cloud at $5/month so a runaway test loop can't surprise you.
4. Keep the existing rate-limit + caching architecture — it's already optimal regardless of tier. The user's architectural-discipline framing is correct: deterministic-first + AI-second is the right pattern, free tier or not.

## Even on Essentials, keep the R18 mitigations

Quota hits don't disappear on Essentials — they just become rate limits at very high volumes (which OVERRIDE will never approach). But the **demo-recording resilience strategy** stays valid because of two other risks:

1. **Network outage during the 2:42-2:55 recording window** — same R18 mitigation applies. The `layered_defense_demo.json` fixture is insurance.
2. **Granite output non-determinism between recording attempts** — even with `temperature=0.3`, two runs of the same session may produce slightly different `cause`/`consequence` wording. If the recording requires retake, you want byte-identical fixture-replay so the screen content matches the voiceover.

Continue capturing fixtures (the 3-5 sample outputs I suggested last round) regardless of tier upgrade. Even at $0.40/session, replaying from disk is faster than re-running through watsonx and removes any non-determinism risk.

## What stays smart about the existing architecture

Your "deterministic-first + AI-second" framing is exactly right and pays off two ways:

1. **It's the architectural discipline the rubric rewards** ("build trust through explainability") — judges read coherent systems, not GPU burn.
2. **It scales the free-tier story** — even if you stay on free tier, the architecture means a single 300K-token monthly allotment covers ~30 typical sessions, which is enough for the demo + recording + a handful of screenshots. The user's framing of "maximum perceived sophistication with minimum compute burn" is accurate.

But for **active development under a deadline**, the math says: Essentials. $0.30 over 23 days vs. losing half a day debugging quota throttling is an obvious trade.

## Decision matrix

| Path | Total cost (23 days) | Daily session capacity | When right |
|---|---|---|---|
| **Stay on Free tier** | $0 | ~1/day with conservation | If $5 is genuinely meaningful right now AND you can batch all dev into the first week before quota resets |
| **Upgrade to Essentials** ✅ | **~$0.30-$5** | **25-50/day at sub-dollar/day cost** | **Default recommendation for the remaining 23 days** |
| Upgrade to Standard | $1,050+ | Same as Essentials | Only if you suddenly need fine-tuning or custom model hosting (you don't) |

**My recommendation: upgrade to Essentials today, set a $5/month budget alert, keep developing without quota anxiety.** The R18 risk register stays as written — the mitigations are still load-bearing for demo-recording resilience — but the day-to-day dev experience is no longer constrained.

Sources:
- [IBM watsonx.ai pricing](https://www.ibm.com/products/watsonx-ai/pricing)
- [Ibm-granite token cost calculator (Price Per Token)](https://pricepertoken.com/pricing-calculator/provider/ibm-granite)
- [Billing details for generative AI assets — IBM watsonx docs](https://dataplatform.cloud.ibm.com/docs/content/wsj/getting-started/wxai-runtime-plans-genai.html?context=wx)