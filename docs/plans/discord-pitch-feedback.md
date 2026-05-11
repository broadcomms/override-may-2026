# P1.2 — Pitch & Access Communications Log

> Two distinct communications conflated cleanly. Per `.bob/rules.md`, this plan file is deleted in the same PR that closes P1.2 — when both communications are reconciled and any implications for the build are recorded below.

---

## Communication 1 — Access request (email to Makenna Berry)

- **Channel:** Email to BeMyApp Communications Coordinator
- **Sent:** 2026-05-08
- **Purpose:** Resolve the GitHub-invite delay blocking IBM TORCS Learning Lab access (which gates roadmap P1.3).

```text
Dear Makenna,
I am writing to request assistance regarding access to the May Learning Lab. I registered for the May Innovation Challenge but it's been almost 48 hours, and I still can't find the confirmation in my inbox or spam folder.

Could you kindly verify my registration and resend the GitHub invitation?
My details are as follows:
Name: Patrick Ejelle-Ndille (Owner of BroadComms)
Email: patrick@broadcomms.net
University: University of the People
Degree: 2nd year, Computer Science Student.
GitHub username: broadcomms

I am building an explainable AI race-strategy copilot that will help engineers and fans to understand the new 2026 F1 hybrid energy decisions. Does this fit into the May theme? "Race to innovate. Drive AI beyond the finish line." I look forward to experimenting with the baseline model and decision logic discussed during the opening session so I can prepare for my final project submission.

Thank you for your help!
Best,
```

### Reply (verbatim)

- **From:** Makenna Berry — Communications Coordinator, BeMyApp
- **Received:** 2026-05-08, 3:37 PM
- **Text:**
  > Hi Patrick,
  >
  > There has been a slight delay with the GitHub invitations, but you will receive it within the next few days! We can only send a limited number of invites daily, so we are sending them as quickly as possible. We appreciate your patience.
  >
  > Best,
  > Makenna Berry | Communications Coordinator | BeMyApp
- **Tone:** positive, transparent about the queue
- **Action implied:** wait. Follow-up planned for May 11 if invite hasn't arrived — see `docs/plans/quick-follow-up-on-github-invite.md`.

---

## Communication 2 — P1.2 Discord pitch (#may-challenge-and-lab)

- **Channel:** `#may-challenge-and-lab`
- **Posted:** 2026-05-08
- **Purpose:** Rubric fit-check (R10 mitigation per `05-risk-register.md`); implicit organizer endorsement before committing 25 days of build.
- **Verbatim text posted** (canonical version in `docs/00-abstract.md` § "Discord Pitch (#may-challenge-and-lab)"):

```text
Hi Sydney and Lucas! Quick fit-check on my idea:

OVERRIDE — an explainable AI race-strategy copilot that helps engineers AND
fans understand 2026 F1 hybrid energy decisions. Upload a session replay,
get inefficient-zone analysis with reasoning grounded in the FIA's 2026
energy-management regulations (parsed with Docling), optional forecasting
via Granite Time Series, and a two-pass safety check (deterministic
validator + Granite Guardian BYOC). Two UI modes share one backend:
Engineer Mode (full reasoning chains) and Fan Mode (plain language).

Solution areas: AI Strategy & Decision Support + Fan Experience.
IBM tools: watsonx.ai (serving Granite Instruct + Guardian + Embedding),
Granite Time Series TTM-R2, Docling, Langflow.

Does this read as a clean fit for the May challenge rubric? Anything you'd
flag before I commit 25 days to the build?

Thanks 🙏
```

### Replies captured

> Quote each reply **verbatim**. Do not paraphrase. If the reply is long, capture the full text — judging context is in tone as much as content.

_(no replies as of 2026-05-08; capture as they arrive)_

#### Reply template

```
- From:        <handle, role if known>
- Posted at:   <timestamp>
- Text:
  > <verbatim quote>
- Tone:        positive | neutral | cautious | concerned
- Action implied: <if any>
```

---

## Concerns / suggestions raised

- _(bullet list of distinct concerns or suggestions extracted from any replies — none yet)_

## Implications for the build

> Use this section to decide what — if anything — changes in the roadmap, PRD, or risk register based on the feedback.

- **Roadmap:** _(no change pending replies)_
- **PRD:** _(no change pending replies)_
- **Risk register:** _(no change pending replies)_
- **Positioning / framing:** _(no change pending replies)_

## Decision

- [x] Pitch posted; access request acknowledged (queue delay only); **no scope changes required to close P1.2**
- [ ] If a reply arrives later flagging a real issue: re-open this file, document the implication, decide on scope or framing change

## Cleanup

P1.2 considered closed for execution purposes once the pitch is posted and the access request acknowledged — both done. This file is deleted in the same PR that ships the next feature touching `docs/plans/`. If a substantive reply arrives between now and then, re-open and reconcile first.
