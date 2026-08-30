# ORA — Architecture

## V3.3 — Work admission

    Knowledge acquisition must not create work by itself.

`home/work_admission.py` holds the invariant. Eight reasons may bring something
into somebody's day — `decision`, `confirmation_required`, `deadline`, `risk`,
`goal_blocker`, `user_request`, `opportunity`, `consent` — and every one of them
is a statement about the person's situation. "A document was processed" is not
among them, and confidence in the reading cannot add it.

`admit()` runs once, in `build_home`, immediately after `gather_all`. It applies
to `KNOWLEDGE_SOURCES` (`document`, `document_action`, `event_candidate`,
`life_experience`) — what exists only because ORA read something. A calendar
event or a goal step is the person's own commitment and keeps the standing it
always had.

    declared reason + date   admitted while the date is inside the horizon
    declared reason, no date admitted
    no reason                dropped

`ATTENTION_HORIZON_HOURS = 168` is the week ranking already treats as the edge
of "later". Nothing is lost past it: the fact stays in the profile and in
Documenti, and the same date walks back through the gate as it approaches, with
no new ingestion.

Four producers were turning ingestion into work, and each was corrected where it
sat:

    documents.py            a `needs_review` card for any of four pipeline
                            states, titled with the document's own name.
                            `awaiting_confirmation` — which only means ORA
                            proposed something to itself — was one of them.
    documents.py (admin)    an item for every incomplete `admin_analysis`,
                            whatever its date.
    event_candidates.py     a card for every proposed candidate.
    document_actions.py     cards for `create_reminder` / `needs_review`
                            generic actions, which the analyzer writes for
                            itself off the back of a taxonomy.

`home/adapters/document_uncertainty.py` decides the one remaining case. A
question exists only when the analyzer said it could not resolve something —
`requires_review`, the `needs_review` terminal state, or a failed read — and
then it names the field: an ambiguous date, a missing one, a document that would
not open. The item's title is that question. No path produces a card titled
after a document.

## V3.5 — Evidence becoming a decision

    RESEARCH FINDS EVIDENCE.
    COMPARISON TURNS EVIDENCE INTO A DECISION.
    RECOMMENDATION DOES NOT AUTOMATICALLY CREATE WORK.
    RECOMMENDATION DOES NOT EXECUTE ACTIONS.
    CODE ORCHESTRATES. AI REASONS.

`response_mode="compare"` with a `comparison_need` — the third sibling of
`context_need` and `research_need`. One is about what ORA holds about this
person, one about the world, this one about choosing between things. Nothing
infers it: two results are not a comparison, and governance refuses the mode
without at least two alternatives.

The order of operations is the argument:

    the model frames it     what matters here for this person, which of those
                            things are absolute and which are preferences,
                            what would have to be worked out, what is missing
                            and whether only they can supply it
    the code answers        the arithmetic (`comparison/arithmetic.py`, six
                            generic operations), and whether each stated
                            condition holds for each option
                            (`comparison/constraints.py`)
    the model reads back    strengths, weaknesses, trade-offs, and what it
                            would say — or that it cannot say it yet

There is no score anywhere in `comparison/`. No weight, no ordering function,
no sort: a guard asserts the words cannot appear as identifiers. An option is
better because a sentence says why, and the only thing the code contributes to
that sentence is the numbers in it. `Importance` is a word, not a coefficient,
because the moment code multiplies it, code is deciding what matters.

Two asymmetries the code enforces against the model:

  * a constraint that could not be checked is **not** a breach. An option whose
    figure is missing has not failed anything, and ruling it out would invent a
    fact about it;
  * an exclusion the checks do not support does not stand, and an option that
    was ruled out cannot then be recommended. The model may read the results;
    it may not overrule them.

Evidence is V3.4's, referenced by `research_run_ids` and never copied. When
framing finds the world has not been asked, the research service is called with
the same session, plan and situation, and framing runs again once — inside the
same decision, with no second plan appearing anywhere.

A run is persisted in `comparison_runs` with `supersedes_run_id`, `revision`
and `changed_because`, so "I said A, now I would say B, because" is expressible
later. Nothing in this phase goes looking for the opportunity to say it.

And a comparison produces a decision, not a task: nothing in `comparison/`
writes a card, an item, a reminder or a plan, and nothing in it executes — no
buying, booking or sending. What was concluded goes back to the reasoning that
asked, which decides through the paths that already exist.

Commercial neutrality is structural: there is no sponsorship, affiliate or
partner concept anywhere, and no ordering function through which one could act.

## V3.4 — The four statements it rests on

    CODE ORCHESTRATES. AI REASONS.
    RESEARCH CREATES EVIDENCE, NOT WORK.
    KNOWLEDGE ACQUISITION != WORK.
    A TEMPORAL WINDOW MUST NOT BECOME AN EXACT DATE WITHOUT EVIDENCE.

Everything below is one of those four, made structural.

The code owns identity, ownership, persistence, timeouts, retries, caps,
dedupe, secret handling and the shape of what the model returns. It owns no
judgement: there is no threshold that declares evidence sufficient, no score
over sources, no map from a subject to a query, no phrase that decides how
precise a date is.

The model owns whether to look outside at all, what would answer the question,
how to word the searches, what kind of source settles which claim
(`ResearchQuestion.source_fitness`, per question — what a rule requires is
settled by whoever sets it, what something costs by whoever sells it), how
recent evidence has to be and how long its own answer keeps
(`freshness_requirement`, `valid_for_hours`), what of a person may appear in a
public query and what must not (`disclosable_context` / `withheld_context`,
minimum necessary disclosure, with the sanitizer as a backstop beneath it),
whether what came back settles the question (`sufficient` / `insufficient` /
`conflicted`), whether two sources disagree, whether to look again, when to
stop, and — for a conclusion about a person rather than about a market
(`EvidenceClaim.scope`) — whether it knows enough about them to make it.

`ResearchRun` holds the whole of it: `ResearchNeed`, `ResearchPlan`,
`EvidenceSource`, `EvidenceClaim`, `ResearchAssessment`, `ResearchSynthesis`.
Persisted in `research_runs`, never in Life Memory: what the world said this
morning is not a fact about a person.

`TemporalTarget` holds when something is meant to happen at the grade it was
said: **exact / window / horizon / none**. Only `exact` fills `target_date`,
which everything downstream reads as a deadline.

None of these contracts belong to a provider. The same `CognitiveDecision`,
`ResearchPlan`, `ResearchAssessment`, `ResearchSynthesis` and `TemporalTarget`
come back whether Gemini, Groq or Mistral answered — verified by running the
whole research pipeline on Mistral while Gemini was out of quota. Provider
names exist in the adapter layer and the manager, and nowhere that reasons.

## V3.4 — Which model answers is infrastructure

    gemini → groq → mistral → openai → ollama → emergent

Tried in that order, stepped down only for a technical reason: a quota, a rate
limit, a timeout, an unreachable host, a model the account does not serve.
Never because an answer was not liked — a reply the schema rejects is the
reasoning's problem, and failing over on it would make what ORA concludes
depend on who happened to be up.

`ProviderManager` already had the shape: an ordered tuple, typed failures
(`LLMQuotaError`, `LLMRateLimitError`, …, each with a `kind`), per-provider
cooldowns and an attempt log. V3.4 adds two adapters to it — `GroqProvider`
(`qwen/qwen3.8-27b`) and `MistralProvider` (`mistral-small-latest`), both
OpenAI-compatible, both verified against the live accounts for JSON mode and
tool calling — and fixes two things the chain got wrong:

  * the adapters raised bare `RuntimeError` for a network blip or an unmapped
    status, which reached the manager as an application bug and stopped the
    chain dead. They raise typed failures now;
  * a rate limit benched a provider for thirty seconds. One turn of reasoning
    is many calls, so a single 429 removed it for the rest of the turn and a
    whole conversation failed over something that had cleared in a second. Four
    seconds, with `Retry-After` still able to extend it.

A wrong key is a configuration problem, not a busy server: five minutes of
cooldown, so it is not retried on every request forever.

Nothing above the adapter layer knows any of these names. `research/`,
`guidance/`, `life_os/`, `home/` and `life_profile/` are checked for it, and
everything that thinks goes through `get_manager()` without asking who is
behind it.

## V3.4 — Going and finding out

    The code orchestrates. The AI reasons.

Some things cannot be known from inside ORA. They are not about the person, so
they are in no store; they change without telling anyone. V3.4 gives ORA a way
to go and look, and gives the looking a shape.

**The decision is declared, never inferred.** `CognitiveDecision` gains
`research_need`, a sibling of `context_need`: one is about what ORA already
holds about this person, the other about the world. `response_mode="research"`
is the reasoning saying it has reached the edge of what it knows. Nothing
derives it from a plan type, a document type, an area of life or a word in the
message, and governance rejects the mode when no need is attached.

**One way out.** `web_search` is no longer offered to cognition
(`availability="hidden"`; it stays registered and executable). It is the tool
layer underneath research, called directly by the service. Two cognition-facing
paths to the same place meant the model kept taking the blinder one: a single
query, five links, an answer.

**The loop.** `research/service.py` runs plan -> search -> assess -> (search
again) -> synthesize. Every one of those steps except the searching is a model
call with a validated structured answer:

    plan_research      what would answer this, which searches to run, how
                       recent evidence has to be, how long the answer keeps,
                       what may be disclosed and what must not
    assess_evidence    sufficient / insufficient / conflicted, what is still
                       missing, what to search next
    synthesize         the answer, as claims each naming the sources it rests on

The code contributes caps (3 rounds, 8 queries, 24 sources), query dedupe by
normalised text, one technical retry, ownership, timestamps and persistence. It
contributes no judgement: there is no threshold that declares evidence
sufficient, no score over sources, no map from a subject to a query.

**Evidence, not memory.** A `ResearchRun` is persisted in `research_runs`,
never in Life Memory. What a rate is today is something the world said this
morning, not something true about a person.

**Reuse.** The code drops runs whose own stated shelf life has passed —
arithmetic. Whether what is left answers a new question is meaning, so the
model is asked.

**Citations.** Only sources a claim actually rests on are citable; anything
retrieved and ignored is not shown. The existing PX1.4 "FONTI" block renders
them unchanged.

**An exchange is not a task because it happened.** The same rule again, in the
place it was still being broken: `conversation_adapter` turned every open
session into "DA FARE ADESSO — Continua la collaborazione con ORA", so asking
what a car inspection costs put a job on somebody's plate. A conversation is
admitted now only when the reasoning left something open — a plan it drew up,
a guided flow it started, a V3.1 question it is blocked on — each an artefact
of a decision the model made. `active_goal` is deliberately not consulted: the
model fills it every turn as a running description of the topic, so reading it
as a goal is exactly how a question became a task.

**A verdict on a person needs to know the person.** `EvidenceClaim.scope` says
who a statement is about — `external_fact`, `general_inference`,
`person_specific` — and a person-specific conclusion must name the facts about
them it rests on, or it is dropped. What any given conclusion needs is the
model's judgement; the code only checks that it named something.

**What settles a question depends on the question.** `ResearchQuestion.
source_fitness` is per question, not per plan: what a rule requires is settled
by whoever sets the rule, what something costs by whoever sells it. Both
sentences are the model's, and the code privileges neither.

**A window must not become a day.** The plan could hold two things — a date or
nothing — so "quest'anno" had nowhere to go and arrived as 24 June 2027, six
months past the year it named, with Home counting down to it. `TemporalTarget`
carries the grade instead: `exact` for a day somebody gave, `window` for a
period with a far edge, `horizon` for a distance, `none` for silence, plus
their own words in `as_said`. `LifeOsPlan.target_date` — which ranking,
urgency, countdowns and the calendar all read as a deadline — is filled from
`target.exact_day` and from nothing else, so no path exists by which a period
becomes a date. Which grade was said is the model's to report; the guarantee
that it is not quietly improved is the code's.

**Research is evidence acquisition. Research does not create work.** The V3.3
rule, extended. Nothing in `research/` writes a task, a card, an attention item
or a notification. What was found returns to the reasoning that asked, in the
same session and the same plan, and that reasoning decides through the paths
that already exist.

## V3.3 — What a fact learned in the setup may become

Three rules, all enforced in deterministic code, none of which knows a domain.

**A capability claim needs its grounding.** `BenefitDescriptor.grounded_by`
lists the keys that would make the claim true; `active_benefits()` drops a
benefit whose grounding is absent, however many activation keys are present.
Knowing that a policy *exists* is a boolean; "posso monitorare la scadenza"
needs the expiry or the document. The keys live in the catalogue, so the rule
reads a declared field and never a subject.

    grounded_by=[]              the claim rests on the activation keys alone
    grounded_by=[k, ...]        claimed only once one of these is known

**Knowledge availability is never the hero.** The life-setup adapter marks its
benefit items `priority="later"` and `meta.knowledge_only`; `_focus_eligible()`
in `home/service.py` rejects them, *and so does the fallback that exists so a
stale-but-real item can still open the day* — a rule that holds only while
something else is present is not a rule. An empty focus slot is a legitimate
outcome: Home says there is nothing rather than inventing something.

**A card keeps the destination it declared.** `rank_items()` used to overwrite
every item's actions with `actions_for(item)`, whose default route is
`GENERIC_ENTRY = "/action/open"` — the clarifier for ambiguous *typed* input.
A card ORA generated therefore arrived at the intent classifier carrying only
its title. Ranking now keeps a declared non-generic route as the primary
action and appends only the generic verbs (snooze, ignore, correct, complete);
an item that declares nothing still gets the guided entry.

**And it keeps its meaning at the destination.** Keeping the route was only
half of it: a card that declares nothing still opens the guided flow, and there
the Action Engine classified the *title* — `item_type=None`, deliberately,
because a card's type used to be an unreliable guess. For one kind of card it
is not a guess: `needs_review` exists because a document was read and is
waiting to be confirmed. `_intent_declared_by_card_type` reads
`HOME_TYPE_BY_INTENT` backwards for exactly those types, so the flow is chosen
from what ORA knows rather than from the words in the title; everything whose
type was itself a classification (`study`, `event`, `travel`, …) still goes to
the classifier, which is what keeps "devo studiare l'esame di psicologia" on a
card typed `event` routed to study.

**A branch records what it establishes.** An option that resolves a question
one way must write the fact for every way, negatives included: "casa in
affitto" writes `casa.owned: False`. Otherwise the objective stays `unknown`,
nothing ever asks it again, and the area is capped below 100% by an answer the
person already gave. `_is_negative` makes a stated no a resolved state; the
strategist's `known_keys` excludes false values, so a recorded negative never
activates anything.

## V3.3 — Guided Life Setup

The first thing a person meets is no longer a conversation. It is a guided
path: structured choices, one part of a life at a time, with free text only
behind "Altro". The open conversation is ORA's, afterwards — a chat box on the
first morning asks somebody to work out what to say before they know what ORA
is for.

    guided.py     the catalogue: what is asked, how it is answered, what an
                  answer means, and what has to be true for it to be asked
    setup.py      which question is on screen, and what happens to an answer
    router.py     GET /life-profile/setup · POST answer / skip-area /
                  go-to-area / finish

`guided.py` is declarative and it is the whole business logic. An entry carries
its question, its control (`single` · `multi` · `yes_no` · `currency` ·
`number` · `date` · `location` · `document` · `text`), its options, and for
each option what it *establishes* (`sets`) and what it *retires*
(`not_applicable`). The interface receives one objective and draws it; a branch
implemented in a component is a branch nobody can test.

Three invariants:

- **One area at a time.** The visible current area is the area the current
  question came from, and moving on is an explicit step the person takes —
  "Casa — conosciuta, ORA ne conosce il 72%. Passa a Lavoro."
- **Cross-area learning, never cross-area jumping.** Choosing "con il partner"
  in Casa records `famiglia.partner`, so Famiglia moves; the next question
  stays in Casa.
- **No question index.** What comes next is derived from what is known, what
  was declined, what was ruled out and which dependencies are settled. Closing
  the app halfway and returning resumes from the real state.

**An answer can mean "there is none".** "Non lavoro" writes
`lavoro.active = False` and retires every objective behind it, so Lavoro reads
100% for somebody with nothing to tell it — distinct from skipping, which
leaves the hole, and from declining, which is counted as missing and never
raised again.

**The name is asked once, before the areas, and only when the account has
nothing usable.** It belongs to no part of a life, which is why it cannot live
inside one — asked in the middle of Casa it reads as a form changing subject.
It writes to `db.users.name`, the identity every surface greets with: the
previous version kept its own copy in the setup session while Home went on
saying "Test".

## V3.3 — Progressive Life Setup and the Life Profile

The figure on the screen is the whole design problem. "42%" is the one thing a
person reads literally, so it had to mean something literal: the share of what
ORA could usefully know about a part of a life that it currently does know,
weighted by how much each piece helps.

    completeness = Σ weight(known or inferred) / Σ weight(applicable)

`backend/life_profile/` is a projection and writes nothing. The knowledge it
counts was declared long before this sprint: `ai_life_strategist`'s
`DOMAIN_GAPS` already carries weights (`information_gain`) and dependencies
(`when`), and `minimum_life_context` already knows which keys evidence the
early nuclei. Areas group those domains for a person to recognise; a second
catalogue would be a second truth.

    areas.py         eight areas over the existing gap domains
    objectives.py    five states, and which objectives are live right now
    completeness.py  the arithmetic, and what "enough to help" reads as
    service.py       the read model over LifeProfile + setup session
    router.py        GET /life-profile · POST /life-profile/not-applicable

The denominator excludes exactly two things, and the distinction between them
and a third is the whole honesty of the number:

    skipped         not now              still counted as missing
    declined        I would rather not   still counted, never asked again
    not applicable  there is none        gone from the reckoning

Only `not_applicable` leaves. "Non ho la macchina" resolves the question it
answers *and* retires everything gated on it, so Mobilità reads 100% with no
invented answers — a life without a car is not an incomplete life. A refusal
does not leave: ORA still does not know, and a percentage that rose because
somebody declined would be the one reading of this number that is a lie. It is
simply never raised again.

- **what is still latent.** ORA does not know whether there is a mortgage to
  ask about until it knows the place is owned, so the objective appears only
  when its gate is answered. This is why an area can *widen* — answering
  "di proprietà" opens the deed, the mortgage and the insurance, and the share
  known legitimately falls. Inventing monotonicity there would mean inventing
  a number.

What is deliberately **not** excluded is anything merely skipped. "Più tardi"
leaves the objective unknown and counted as missing, or the figure would be a
measure of how many questions somebody dismissed.

**One life model.** There is no `onboarding_answers` collection. Setup answers,
documents and ordinary conversation all write into the stores that already own
them — `LifeProfile` for structured facts, governed memory for the rest — and
the profile is read from those. It follows that learning outside the setup
moves the figure by itself: a policy uploaded a week later, or a payment
mentioned in passing, updates the same projection with nobody reopening a form.

**A setup question is not a blocker.** V3.1's `OpenQuestion` means work has
stopped and is waiting for this person. Nothing in a life is stopped because
somebody has not said which energy supplier they use, so the setup never
creates one — a guard fails the build if either module reaches for that API.
Ten skipped offers leave "Domande per te" exactly as it was.

**The first run is over when the person says so.** `isFirstRunOver` accepts
completed, skipped, cancelled and interrupted. Completion is about knowledge; a
gate has no business holding somebody at the door until they have told ORA
enough about themselves.

**The surface.** `LifeSetupSurface` puts structure around the conversation
rather than inside it: who is asking, the promise, the profile figure, the part
of life this is (with what ORA already knows and what would still help, as
things rather than fields), what else exists, and that you can leave. Nothing
on it can be typed into except the composer — the questions are still written
one at a time, in the thread, by the part of ORA that knows what was just said.

**Patrimonio.** What somebody owns beyond the roof over their head — another
flat, a loan still running, savings — had no representation at all: `finanze`
carried a single objective about monthly outgoings. It is now its own area over
its own domain, marked sensitive, because standing possessions change what
advice is realistic in a different way from monthly spending, and because
somebody willing to discuss their bills is not necessarily willing to discuss
their savings.

Live QA fixed four things underneath this, all in code that predates the
sprint: "senza mutuo" was recorded as *having* a mortgage (a mention is not a
possession); "la casa è di mia proprietà" matched no phrase at all; Home
claimed "adesso posso usare i documenti della tua casa" to somebody who had
never uploaded one, because the benefit fired on owning a home rather than on
having a document; and the two nuclei that belong to no subject in particular —
the person's name, what is most pressing — could interrupt somebody mid-thought
("come preferisci che ti chiami?" straight after they described their house).

## V3.2 — Life guidance: reconstruct, then ask only what blocks

V3.1 made a blocker survive. V3.2 decides whether there should be one.

The unit is not a domain flow. It is a `GoalState`: an objective, a stage, and
milestones each carrying a `state` (done / active / upcoming / conditional /
not_applicable / unknown) and a `basis` (fact / inference / unknown). The
residual path is simply the milestones that are not behind us — nothing is
"generated"; what is already done is dropped, and what remains is what ORA
guides. `plan_item_id` binds a milestone to the plan item it already has, so
reconstruction is a read-model over existing work rather than a second plan.

Four steps, in order, in `backend/guidance/`:

    models.py       GoalState · Milestone · Variable · NextStep · Sufficiency
    resolution.py   know before asking
    questioning.py  bundle what is left
    service.py      reconstruct → assess → evaluate
    bridge.py       the reasoning's vocabulary ↔ guidance's, and V3.1's payload

**Reconstruction.** The model emits `goal_state` on its decision; the service
merges it into what was already known. A correction beats an inference, a
stated fact is never downgraded by a later guess, milestone identity and
`plan_item_id` survive a revision, and a malformed reconstruction leaves the
previous state standing rather than replacing a plan with rubble.

**Resolution — the step that decides whether ORA is a guide or an intake form.**
Every variable the next step needs is looked for, in order, in: the sentence
the person just said, answers already given (a refusal is an answer), and
ORA's own sources through the existing Context Broker. There is deliberately
no second retrieval path: the broker already knows every source with authority
and provenance attached. A resolved sensitive variable is recorded as "già
noto" — never quoted back into a prompt or a log.

Two rules keep "I already know this" honest, both written after live QA broke
them:

- **Everything the variable is called has to be present.** Partial token
  overlap let "fissa l'appuntamento dal notaio" resolve "data e ora
  dell'appuntamento dal notaio": naming a thing became stating its value. The
  ref is a machine name and only stands in when there is no label; Italian
  elision is unglued first, so "l'importo" is recognised as "importo".
- **ORA's own records of the work are not evidence.** Situations, goals and
  plan items restate what the person asked for — a situation reading "…in
  attesa di specificare data e ora" made ORA decide it knew the date it was, in
  the same sentence, waiting for. Resolution reads profile, memory, documents
  and the life graph; it does not read the plan.

**Sufficiency.** Only `required` may become a question, and only while it is
still unknown (`Variable.blocks`). `useful` and `optional` never reach a
person, however interesting they are.

**Questioning.** What is left is asked once: a bundle of at most 7, least
personal first, in one sentence with one question mark — not a form, and not
six turns. When guidance did not change the set the model asked for, the
model's own wording stands: the system decides *what* may be asked, the model
writes it. Composition is the fallback, and it no longer grafts the reasoning's
prose into a template — the purpose travels as `why_needed`, where V3.1 already
shows it.

**Guidance either advances the work or asks what blocks it.** It may not
describe what advancement would look like — that was the last failure and the
quietest: ORA reconstructed the path, said what the next step would be, and
stopped, leaving the person to work out what it needed and volunteer it. Five
shapes of that dead end are recognised deterministically in
`guidance/wording.py` and the loop, and each buys the model one more pass with
the residual path in front of it (at most two per turn, so it always
converges): the plan narrated with nothing done and nothing asked; a conclusion
drawn about the person before what it rests on is known; a question for
something the model itself marked `useful`; being stopped from re-asking and
offering to stop instead; and an action refused for missing information with no
question written to go with it.

**One turn, one question, one meaning.** A question is decided, stored, shown
in the thread and projected onto two other surfaces, and each of those was a
chance for it to become a slightly different question. Three bindings close
that: the sentence the person reads in the thread *is* the sentence stored on
the `OpenQuestion`; the work it is filed under comes from the guidance step it
was decided in (`step_title`, `milestone_ref`, `plan_item_id` travel on the
ask) rather than from whichever plan item the session happened to be focused
on; and Home and Attività project that one row by identity. Live, a question
about scheduling a meeting had been filed under "definire la data esatta di
fine rapporto" — two different steps in one row, with no way for the person to
tell which they were answering.

**Every turn on live work is named.** `guidance_outcome` records what a turn
amounted to for the person — `ask`, `act`, `complete`, `continue`, or `limbo`.
Limbo is the plan described with nothing asked and nothing done: the state this
whole section exists to remove, written down rather than assumed gone, because
a guarantee nobody measures is a hope.

**ORA chooses the step; the person chooses their life.** A turn that ends
"su cosa vuoi concentrarti?" has handed the plan back — the person is being
asked to manage the process, which is the work guidance exists to take off
them. `guidance/wording.py` recognises that shape and the loop gives the model
one more pass with the residual path in front of it. It never fires without a
reconstruction behind it: offering a direction is honest when ORA does not yet
know the shape of the goal. The same pass catches the other escape route — a
question written into an answer's prose, which `response_mode=ask` never sees:
when the reasoning itself marked a need `useful` and then asked for it anyway,
it is held to its own declaration.

The same module refuses wording that arrives in English, because the product
speaks Italian and a question written for another reader cannot be shown. Where
either check fires, the question is composed from the variables instead — and
the composed question replaces the model's sentence *in the conversation too*,
not only on the stored `OpenQuestion`. The same substitution happens when
guidance narrowed the set: leaving the original sentence on screen asks for
something ORA had already decided it knows, and the person cannot tell that the
system decided otherwise.

**"Domande per te" means one thing.** A real `OpenQuestion` and a suggestion the
attention layer phrased as a question look identical and behave nothing alike —
only one of them has stopped work. When a real one exists it is the only kind
shown, on both surfaces, and the displaced suggestions move to the updates feed
rather than disappearing. Every count on the page — the section badge, the
rail's "Domande in attesa" — derives from that one list.

A blocked action is an ask, not an apology. `governance.validate_decision`
refuses a side effect whose uncertainty is blocking; it used to replace the
message with "Mi manca un'informazione necessaria per procedere in modo
affidabile" and throw away the question the reasoning had already written. It
now switches the turn to `ask` and keeps that question, which is also what
routes it through the guidance gate and into a durable `OpenQuestion`.

The gate lives in `conversation_engine/ai_core/loop.py`, immediately before the
ask is appended:

    decision says "ask", uncertainty blocking
        └─ bridge.variables_from_missing        (explicit necessity wins;
                                                 a legacy blocking ask ⇒ required)
        └─ GuidanceService.evaluate             resolve → assess → bundle
             ├─ nothing required is unknown
             │    └─ bridge.resolution_observation → INFORMATION_ALREADY_KNOWN
             │       fed back to the model, which now answers
             └─ something is genuinely missing
                  └─ bridge.blocking_ask_payload → V3.1 OpenQuestion
                     carrying `requested_variables` and `avoided`

Two properties are structural, not stylistic:

- **The gate never costs a turn.** If guidance raises, the question the model
  wrote is still a legitimate question and is asked. Guidance improves an ask;
  it is never a dependency of one.
- **`goal_state` crosses governance explicitly.** `governance.validate_decision`
  rebuilds a `CognitiveDecision` field by field from an allowlist, so a new
  field that is not named there is silently dropped. It is validated as a
  `GoalState` at that boundary and passed through; invalid input is recorded as
  `goal_state_invalid` and the previous reconstruction stands.

`resolved_refs` on the AI-Core state records what one turn resolved. It is
deliberately not `clarification_history`, which is the loop's own attempt
counter and is rewritten on every ask.

Domain neutrality is enforced by test, not by convention: an AST walk over the
guidance package fails on any class, function or constant naming a domain
(mortgage, house, car, wedding, travel, job…), and the same engine is proven on
an unrelated goal. There is no `if domain == …` anywhere, and V3.2 introduces
no search engine, crawler, comparator or commercial provider.

## V3.1 — WAITING_USER: persistent blockers and exact resume

A conversation that stops for a question has always been able to say so. What
it could not do was survive: close the app, restart the process, come back on
Tuesday, and the only record was a sentence in a transcript. `waiting_user` on
the session is not that record — it is set after every turn and means "idle".

The addition is one entity and one rule.

**The entity.** `waiting/models.py::OpenQuestion` holds the question, why it is
needed, human words for the work it belongs to, the work's own identifiers
(`WorkRefs`: session / plan / plan item / object / situation), a
`ResumePointer`, and — separately from the question's own lifecycle — a
`ContinuationState`.

**The rule.** The client never names the continuation target. It sends the
answer and the question's handle; the pointer comes from the server.

Flow:

    reasoning marks its uncertainty blocking
        └─ CognitiveTurnResult.blocking_ask
             └─ AICoreOrchestrator._persist_blocking_ask
                  reads the session's own ai_core focus:
                    active_plan_id · current_plan_item_ref ·
                    active_object_ref · active_situation_ref ·
                    reasoning_epoch · active_goal
                  └─ WaitingService.record_blocking_question  (idempotent)

    POST /questions/{id}/answer
        └─ repository.answer            conditional on status == "open"
        └─ repository.claim_continuation conditional on pending|failed
        └─ _restore_focus               LifeOsService.bind_session_object_focus
        └─ _run_turn                    AICoreOrchestrator.message(
                                          client_message_id=f"ans_{question_id}")
        └─ finish_continuation          done | failed (retryable)

Three properties are storage guarantees rather than application logic, because
application logic is where races live:

- a partial unique index on `(user_id, dedupe_key)` where `status == "open"`
  makes a retried cycle collide with the question it already asked;
- `answer` is one conditional update, so two simultaneous answers produce one
  transition and one continuation;
- `claim_continuation` is another, so a retry overlapping a running attempt
  does nothing rather than running the work twice.

The reasoning still reasons. What changed is that it reasons over a state it
was handed — the same plan, the same item, the same object — instead of one it
reconstructed from its own previous sentences.

## V2.8.2 — Context Broker V3

Il production brain mantiene due stadi: Stage A è una slice piccola di account,
Situation correnti e active goal; Stage B parte soltanto da un `ContextNeed`
AI-owned, validato da governance. Un `ContextSourceRegistry` espone adapter
uniformi per Profile, Memory, Situations, Life OS, Goals, file metadata e
calendar metadata. Presence resta esclusa dal retrieval automatico e richiede la
capability consent-aware dedicata.

Il ranking è bounded e general-purpose: overlap semantico leggero, authority,
Situation anchor e source diversity. Non esiste un secondo LLM orchestrator né
un domain router. Il report distingue `no_relevant_evidence`,
`source_unavailable` e `access_denied`, misura candidate/final count, payload e
latenza per source senza registrare contenuto personale. I path category/keyword
V2.1 restano soltanto come compatibilità esplicita per chiamanti legacy.

## Prompt V2.7.1 — Foreground location + PresenceContext (2026-08-15; STALE refresh + Home handoff 2026-08-16)

```
Home Ask / startOraConversation
  → POST /ai-core/start (ONE cognitive turn; persist user message + message_id)
  → navigate /ora/{sessionId} only (no text/coords in URL)
  → OraConversationScreen GET history + pending_turn
  → if awaiting_client: fulfill client_actions once → client-resume
  → if completed: render history (user + ora)
```

```
AI get_current_location / get_current_presence
  → preference off → needs_client + request_location_permission (ORA consent)
  → STALE / no signal + while_using → needs_client + request_foreground_location
      (refresh: true on STALE; maximumAge 0 on FE)
  → CognitiveTurnResult.client_actions + pending_turn (persisted; survives navigation)
  → FE: sheet only for ORA consent; if while_using + Chrome granted → getCurrentPosition directly
  → POST /api/location/signal  (auth, user-scoped; reverse place label)
  → PresenceContext upsert (CURRENT)
  → POST /api/conversation/ai-core/{id}/client-resume
  → AI answers from CURRENT/RECENT — STALE never claimed as now
  → timeout/denied/unavailable recorded distinctly; transient errors clear on next user turn
  → pending_client_capability enables generic “try again” without hardcoding phrases
```

| Concept | Storage | Notes |
|---------|---------|--------|
| LocationSignal | `location_signals` | TTL **2h** via `expires_at`; not Memory |
| PresenceContext | `user_presence` | Latest per user; AI consumes `for_ai()` / broker slice |
| Preference | `users.settings.location_mode` | `off` \| `while_using` (≠ browser permission) |
| Freshness | CURRENT ≤5m, RECENT ≤30m, else STALE | UNKNOWN if none |

Native / background: **unsupported / unavailable**. No geofence→action. Residence remains Profile/Memory.

**Canonical:** Location is sensor evidence. Presence is contextual state. Meaning remains governed/AI-interpreted. Memory remains governed.

## Prompt V2.6.2 — Context change & turn-scoped idempotency (2026-08-15)

Invariant: **New evidence may invalidate persisted state. Idempotency is execution safety, not a ban on future adaptation.**

```
each user turn → new reasoning_epoch
same-turn identical tool_signature → reuse observation (no second write)
cross-turn same target + new fact → update_plan / update_object allowed
user_fact_summary → USER_PROVIDED_CONTENT (source_type=user_conversation)
user_conversation must not supersede user_file evidence
```

## Prompt V2.6.1 — Source-grounded reconciliation (2026-08-14)

```
new evidence → AI chooses reconciliation_mode
  preserve | patch | replace_scope | rebuild_from_evidence
update_plan:
  replace_items | remove_item_ids | add_items | item_updates
  → same plan_id; optional progress map by title; item.origin provenance
evidence:
  status active|superseded|historical
  public_sources[] for Workspace (human display_name only)
GenerativeObjectRenderer: useTheme() colors (not static dark tokens.color)
```

## V2.8.1 — Situation Model V1

`backend/situations/` provides user-scoped, cross-session contextual state for
the production AI Core. `CognitiveDecision.situation_update` is optional and
domain-neutral. The AI selects semantic operation and content; runtime assigns
ids and guarantees ownership, optimistic revision checks, valid terminal
transitions, provenance history and reasoning-epoch idempotency.

Mongo collection `situations` uses non-destructive indexes on `(user_id,id)`,
`(user_id,status,updated_at)`, `(user_id,session_id,updated_at)` and
`(user_id,linked_plan_id)`. Context Broker Stage A adds only a small session/
recent slice; Stage B can include bounded details. Situation writes do not
write Life Memory and do not implicitly mutate linked plans or objects.

Canonical contract: [COGNITIVE_ARCHITECTURE.md](COGNITIVE_ARCHITECTURE.md).

## Prompt V2.6 — ContextFile / AI Core file evidence (2026-08-14)

```
OraComposer paperclip
  → POST /api/conversation/ai-core/files/upload  (auth, Documents V2 storage)
  → ContextFile (life_os_context_files) + session_files in AI state
  → message attachments: [{file_id, display_name, mime_type}]
  → AI Core tools: list_session_files / get_file_context / get_file_content / link_file_context
  → existing Life OS: update_plan / update_object + evidence_refs (USER_PROVIDED_CONTENT)
```

- Blobs stay in Documents V2 (local/dev storage abstraction already there); messages hold refs only.
- Staged retrieval: lightweight `session_files` in Context Broker payload; full text via chunked `get_file_content`.
- No domain document routers. File text is UNTRUSTED DATA (prompt + observation notices).
- `runtime_capabilities` exposed to the model for capability honesty (`image_vision_multimodal: unavailable` today).
- Indexes: `life_os_context_files` on startup via `ContextFileService.ensure_indexes`.

## Prompt V2.5 — Production ORA surface (2026-08-13)

```
Home OraInput / Ambient ORA tab / Workspace “Continua con ORA”
       → buildOraConversationHref / startOraConversation
       → /ora/{sessionId}  (production)
       → POST /api/conversation/ai-core/*  (same AI Core runtime)
       → Life OS plans + GenerativeObjects → Goal Workspace
/ora-ai/* = DEV harness only (shared OraConversationScreen)
```

| Piece | Role |
|-------|------|
| Production ORA | `/ora`, `/ora/{sessionId}` — Quiet Premium conversation |
| Entry points | `home` \| `ora` \| `goal_workspace` \| `continue` \| `focus` \| `object` |
| Nav helpers | `frontend/src/ora/oraNav.ts`, `startOraConversation.ts` |
| Composer | `OraComposer` — shared; Home compact `OraInput` feeds same runtime |
| Session policy | Coherent thread; goal-bound work reuses `plan.conversation_session_id`; general ORA creates a new thread when starting fresh |
| Legacy boundary | CE→AE remains for genuine legacy items; new Life OS work never opens Study/Action wizards |

## Prompt V2.4 — Generative Workspaces (2026-08-13)

```
AI Core → create_plan / create_actions / create_object
       → life_os_plans + life_os_objects (declarative UI blocks)
       → Goal Workspace + Home / Contesti (same identities)
       → Observation → AI answer
```

| Piece | Role |
|-------|------|
| `GenerativeObject` | AI-authored durable object; `object_kind` is a label only |
| UI primitives | text, card_deck, timeline, task_group, relation_graph, … |
| Revealable card contract | Canonical `{front, back, revealable}`; `card_deck` requires both; API/FE normalize small legacy aliases (`title`/`question`/`answer`/…) |
| Governance | size/nesting/primitive/executable validation |
| Goal Workspace | `/goal-workspace/{planId}` + `GenerativeObjectRenderer` |
| Decisions from Life OS | route to Goal Workspace — never legacy `/action` |
| Budgets | MAX_STEPS=8, tools=5, writes=4, objects=2, external=2 |

Closed V2.3 artifact types (`generate_artifact` flashcards/quiz/…) removed from AI Core. Legacy StudyPlan/Travel/Action Engine unchanged as compatibility infrastructure.

## Prompt 7 V2.2 — Tools & grounded external knowledge (2026-08-13)

```
USER → AI
     → personal context (Context Broker) and/or READ_ONLY tool
     → Governance (capability, side-effect, query sanitize, budgets)
     → Observation (ExternalObservation / personal facts)
     → AI re-entry
     → answer | ask | finish | act
```

| Layer | Role |
|-------|------|
| Cognition | Chooses capability ids (`web_search`), never provider brands |
| Tool Registry V2 | Metadata: classification, side_effect (READ_ONLY / REVERSIBLE_WRITE / CONSEQUENTIAL_WRITE), freshness, availability |
| Provider layer | Tavily → Brave → Gemini Search failover for `web_search` only when prior fails / empty |
| Observations | Evidence snippets + authority hints; provider “answers” not authoritative |
| Epistemics | Tool-before-claim for current/operational external facts; no silent model substitution on tool failure |
| Temporal | `current_facts.*` for temporary/goal facts; durable Profile unchanged |

`web_search` ≠ live traffic / Maps routing / booking / weather APIs.

## Prompt 7 V2.1 — Personal context retrieval (2026-08-12)

```
USER → AI (Stage A: account name + goal)
     → if needs more: response_mode=context + semantic context_query
     → Context Broker Stage B (Profile/Memory, filtered, provenance)
     → AI re-entry (original question preserved) → answer
```

| Layer | Role |
|-------|------|
| Stage A | Tiny high-authority baseline (`users.name` as `structured_account`, active goal) — enables 1-call identity answers |
| Stage B | Semantic categories (identity/residence/employment/study/general) over Profile + Memory; no full dump |
| Authority | Reuses Life Memory `authority_band` / `memory_status_from_authority` — conflicts exposed, not flattened |
| Governance | Blocks over-broad queries (“entire database”, “full profile”) |

Unavoidable schema maps live only inside the Context Broker (Profile slot families via `normalize_slot`). They do **not** script dialogue.

## Prompt 7 V2 — AI-Native Cognitive Core (2026-08-12)

**AI owns cognition. Deterministic systems own capabilities and governance.**

```text
USER → AI ORCHESTRATOR → (optional Context Broker / Tool)
     → GOVERNANCE → OBSERVATION → AI again (bounded)
     → FINAL RESPONSE (answer | ask | finish | act)
```

Package: `backend/conversation_engine/ai_core/`

| Piece | Role |
|-------|------|
| `CognitiveDecision` | Structured AI decision (no domain slots) |
| Context Broker | Small relevant Profile/Memory pack (stage A/B) |
| Tool Registry | Semantic capabilities (`search_life_memory`, …) |
| Governance | Schema/tool/permission/state allowlist; memory = proposals only |
| Bounded loop | `MAX_STEPS=4`; duplicate tool signatures blocked |
| Provider | Generic `llm.manager` — not vendor-hardwired cognition |

HTTP (parallel to legacy AE Conversation path): `/api/conversation/ai-core/*`  
Production ORA: `/ora` (scroll + composer). DEV harness: `/ora-ai` (same components).

**Prompt 7.x — abandoned experiment** (stash only). Do not restore its readiness/requirements/discriminator orchestration.

## Conversation architecture reset (2026-08-12)

Prompt 7.x experimental cognitive orchestration (deterministic GoalRequirements / readiness / research discriminators owning dialogue) was **abandoned** after live QA failure. Uncommitted work is in git stash only; working tree restored to Life Memory baseline `258cd85`.

**Rebuild direction (not implemented yet):** AI-first orchestrator owns cognition (understand → ask|research|tool|act → re-enter). Deterministic layer owns auth, schemas, provenance, privacy, tool execution, safety, persistence. New domains add tools/capabilities — not question wizards.

## AI-Native cognition principle (Prompt 5.1, 2026-08-09)

```
REAL USER DATA
  → STRUCTURED ORA STATE          (= source of truth)
  → GEMINI SEMANTIC REASONING     (= cognition, optional)
  → STRUCTURED INTERPRETATION     (= validated JSON)
  → ORA VALIDATION / GOVERNANCE   (= engines)
  → HUMAN PRESENTATION            (= UI)
  → USER
```

| Layer | Role |
|-------|------|
| **Gemini** | Comprendere, classificare, collegare, sintetizzare, ambiguità — **non** database, non fatti inventati, non UI |
| **Structured data** | Source of truth (Life Profile, Study/Travel, Life Objects, …) |
| **Engines** | Governance / action / validation |
| **UI** | Presentation only |

**AI-NATIVE ≠ AI-INVENTED.**  
**AI failure must not erase deterministic user reality.**

Shared LLM path: `backend/llm/` (Provider Manager + `chat_json`). No second Gemini client.

### Life Map (`backend/life_map/`) — Contesti cognition foundation

- **Life Map = DERIVED SEMANTIC PROJECTION** — not memory, not source of truth, not taxonomy.
- **DATABASE RECORD ≠ LIFE SITUATION.** Contesti shows canonical life situations, not raw study/travel rows.
- **SAME ≠ RELATED.** Only `same` collapses Contesti rows; `related` stays separate (e.g. same subject, different exam dates).
- Pipeline:

```
evidence → identity resolution → canonical situations
        → optional Gemini interpretation → presentation → Contesti
```

- Identity (`identity.py`): Level 1 structured (`source_id`, shared `source_priority_id` lineage, future Life Object id) → Level 2 correlation (entity keys ∩ + same temporal anchor) → Level 3 Gemini consultant (capped pairs) → Level 4 do-not-merge.
- Entity keys are open-semantic (normalize + optional post-`:` segment) — **not** subject-specific hacks.
- Stable canonical IDs from sorted `source_refs` / evidence — never `hash(label)`.
- Gemini must not override structured temporal conflicts.
- **OPEN SEMANTICS:** novel situations need no frontend category enums.
- **DETERMINISTIC REALITY > AI INTERPRETATION** (`governance.py` + identity).
- `GET /api/life-map` — presentation-ready canonical rows; Contesti does not invent semantics or dedupe.
- Cache: Mongo `life_map_snapshots` = **DERIVED / REBUILDABLE**; Never SoT.
- Life Objects (future): `life_object_ids` on candidates already reserved as Level-1 identity signal — no LO refactor now.
- Contesti FE prefers `/life-map`, falls back to `buildContextsMap` only if the API fails/invalid (never overwrites a valid canonical payload). Pull-to-refresh uses `force=true`.
- `life_map_snapshots` caches optional Gemini interpretation only — identity/assemble always recomputed. Stale uvicorn without this router causes Contesti FE fallback duplicates.
- Local AI: `LIFE_MAP_GEMINI=1` + `GEMINI_API_KEY`; default `0`.

### Life Memory (`backend/life_memory/`) — Memoria cognition foundation (Prompt 6)

```
DATABASE RECORD ≠ MEMORY
MEMORY ≠ CURRENT CONTEXT (Life Map / Contesti)
AI INTERPRETATION ≠ EVIDENCE
```

Pipeline:

```
raw sources → normalize candidates → memory identity
           → contradiction governance → canonical memories
           → optional Gemini wording → Memoria UI
```

- **Sources V1:** Life Profile facts (primary), durable study *subject* (not exam countdown), user notes (`db.memories`). Travel projects / Home priorities / chat turns **out**.
- **Identity:** same slot family (e.g. `casa.city`) + same value → one memory; study entity keys merge polluted titles.
- **Contradiction:** stronger/fresher authoritative source supersedes; unresolved weak conflict → `ambiguous` (not false fact).
- **Gemini (`MEMORY_GEMINI`, default 0):** wording polish only via Provider Manager; hallucinated memory ids rejected; failure keeps deterministic statements.
- **`GET /api/life-memory`** — presentation-ready; Memoria FE must not invent memory from raw profile compose. On API failure → honest empty/error (`__DEV__` warn).
- **Cache:** `life_memory_snapshots` = Gemini wording only (fingerprint + TTL); assemble/identity always recompute.
- **Legacy:** `GET/POST /api/memory`, `POST /api/memory/ask` unchanged (notes + Q&A).
- **Life Objects:** hybrid path — LO = entity evidence authority later; V1 reads Profile first (no LO refactor).
- **Conversation→Memory:** CE slots stay session-local today; promotion to durable Profile missing (documented gap).
- **Controls:** `clarify=true` for ambiguous items; Correct/Forget form editors still off.
- **Clarification loop (Prompt 6.1):**

```
Memoria “Da chiarire”
  → POST /life-memory/clarify/start (or CE origin=memoria)
  → Gemini question (minimized pack) / deterministic fallback
  → Focus `/memory-clarify/{id}` free-text answer
  → Gemini structured resolution → validate targets/ids
  → LifeProfileService.correct_fact / apply_facts(suggest)
  → invalidate cache → recompute Life Memory
```

- Gemini never writes truth; hallucinated memory ids / unauthorized keys rejected.
- Additional facts from answers → `source=inferred` suggested only.
- CE session linked (`ui_mode=memory_clarify`) for continuity — **not** Action Engine.
- **Epistemic authority (6.1.1):** `user_confirmed` / `user_said` / account / document → **known** (not clarifiable). `inferred`/`suggested` → likely/ambiguous. Device/GPS ≠ residence known. Life Setup first-person NLP persists as `user_said` (not inferred). Clarify questions must address USER (never “mi chiamo…” as ORA).
- Local AI: `MEMORY_GEMINI=1` + `GEMINI_API_KEY`; clarify uses Provider Manager whenever available (soft-fail keeps ambiguity).
- `MEMORY_DEBUG=1` for evidence/resolution in response.

## Life Object Engine — modello canonico (SHADOW + Semantic Integrity + Digital Twin Knowledge, 2026-08-07)

**Life Objects = verità canonica sulla realtà dell’utente** (HOME, VEHICLE, UNIVERSITY, JOB, …).
**Gemini = consultant; backend = autorità** (Semantic Validator sempre prima del persist).
**Digital Twin Knowledge Model:** `facts` / `hypotheses` / `decisions` / `goals`(link) / `memory` + timeline semantica. **Fact mai cancellato** (supersede/archive). Hypothesis mai auto-promossa.
Conversation, Goal, Documents, Brain, Proactive, Home, Travel, Study **continuano a esistere**: non vengono eliminati. Diventano **satelliti / fonti** che leggono e aggiornano i Life Object — non posseggono più “la verità” da soli.
Enrichment backend: narrative versionata, questions, insights, temporal, health spiegabile; split **identity / state**. Gemini opzionale via Provider Manager; fallback italiano deterministico.

```
                 ┌──────────────────────────┐
                 │      LIFE OBJECTS        │  ← canonical truth (shadow writes)
                 └────────────▲─────────────┘
        read/write │          │          │
   Documents V2   Goal Engine   Brain / Conversation / Proactive
   Life Experience Travel/Study Home (ancora Goal-aware; V3 UI OFF)
```

- Package: `backend/life_objects/` — models, repository, service, reasoner, enrichment, semantic_validator, title_generator, property_registry, assimilation, link_states, knowledge_gaps, **knowledge_model/**, provenance, identity_state, home_v3, dedupe, linking, memory, router, shadow hooks
- Pipeline: Document → OCR → Document AI → Life Object AI → **Semantic Validator** → **Knowledge ingest** → Canonical Object
- Flags: `LIFE_OBJECT_ENGINE_ENABLED=1` (shadow ON), `LIFE_OBJECT_HOME_UI_ENABLED=0` (UX invariata), `LIFE_OBJECT_GEMINI=1` (fallback se assente)
- Collection: `life_objects` (`identity`/`state`/`facts`/`hypotheses`/`decisions`/`memory`/`narrative`/`insights`/`temporal`/`health` 2.0 + typed provenance)
- API: `/api/life-objects/*` + narrative/questions/insights/health/history/enrich + **`/{id}/facts|hypotheses|decisions|timeline|knowledge`** + minimal confirm/reject/outcome + `home-v3-feed` (auth; unused by main UI)
- Docs: `LIFE_OBJECT_*`, `LIFE_KNOWLEDGE_MODEL.md`, `DIGITAL_TWIN_MODEL.md`, `FACTS_HYPOTHESES_DECISIONS.md`
- **Home V3 Life Objects = PREDISPOSTO, non shippato.** Home resta Goal-aware.

## Life Setup Gate (Sprint 1 + 2B, 2026-08-08)

Application **initial state** before Home. Home Quiet Premium stays unaware.

```
Auth → resolveLifeSetupGate(userId) → /life-setup | /(tabs) Home
```

- Module: `frontend/src/life-setup/gate.ts`
- Local persistence: AsyncStorage `ora.lifeSetupCompleted.<userId>` (`1`/`0`)
- Unlock Home only when `session.status === 'completed'` (or feature disabled). `interrupted` / `skipped` / `cancelled` ≠ completed
- Offline: trust local completed; else fail-closed → life-setup
- Complete path: successful `lifeSetupComplete` → `completeLifeSetupGate(userId)` → `routeByLifeSetupGate`
- Entry points: cold start `app/index.tsx`, post-auth `routeAfterAuth`, tabs shell redirect (2nd line of defense)
- UI: `LifeSetupConversationScreen` at `/life-setup`; `PlaceholderLifeSetup` kept for rollback only
- Soft-exit (Esci / Più tardi): FE `allowSoftExit = ?resume= || start.resumed`; show only when `allowSoftExit && !done` (`frontend/src/life-setup/softExit.ts`). First-run incomplete never shows soft-exit; backend may still emit exit/postpone actions.

## Minimum Life Context V1 (Sprint 3, 2026-08-08)

First-launch wrap/`ui.done` is gated by **semantic MLC coverage**, not by exhausting `DOMAIN_GAPS` or a fixed question count.

```
answer → infer_known_from_text (+ profile) → evaluate_mlc_coverage → plan_next
  → wrap only if MLC sufficient → wrap_up_turn (ui.done)
```

- Module: `backend/ai_life_strategist/minimum_life_context.py` (`mlc-v1` **heuristic**, not irreversible domain law)
- Nuclei: `identity`, `current_situation`, `life_places`, `responsibilities`, `immediate_priority`
- **Addressed** = `covered` | `skipped` (explicit refuse/postpone) | `implicit` (rich core context). **Not** “question was asked” (`asked_keys` only de-prioritize)
- `immediate_priority` strongly preferred (one ask even when implicit); rich core (4 covered) can still suffice without perfect priority phrasing
- One utterance may cover multiple nuclei; planner asks highest-gain unaddressed gap
- NLP heuristics (`infer_known_from_text`) persist via profile `source=inferred` + `status=suggested` (`source_confidence` ~0.55) — not high-certainty
- Persistence: `known_facts` on sessions + `life_profiles`; `session.meta.mlc_coverage` (not a UI checklist)
- Documents V2 optional; Gate Sprint 2B unchanged

## Conversational Experience V1 + Walkthrough 4.1 + AI Rendering 4.2 (2026-08-08)

Copy/rhythm layer on top of MLC + Gate — **not** a frontend conversation engine.

```
greeting (deterministic shell + 1 open Q)
  → answer → infer facts (deterministic)
  → Gemini StrategistPlan SAME call: acknowledgement + spoken_question
      (+ conversational_bridge XOR ack) + next_best_question
  → render_conversational_turn validates AI copy → else SAFE deterministic fallback
  → MLC sufficient → ONE optional Gemini wrap synthesis (structured facts)
      → else hardened / SAFE wrap → CTA Entra in ORA
  → lifeSetupComplete → completeLifeSetupGate → Home
```

### DETERMINISTIC vs AI (Sprint 4.2 Architecture A)

| DETERMINISTIC (authority) | AI (Gemini via ProviderManager) |
|---------------------------|----------------------------------|
| MLC coverage, gaps, gate, completion | `acknowledgement` (≤1 sentence) |
| Fact inference & profile persistence | `spoken_question` (natural ask) |
| `next_best_question` + `question_goal` (intent) | Wording only — intent frozen by planner |
| Greeting shell, actions/UI contract | Optional wrap `spoken_text` (rare, end only) |
| Location / soft-exit / Home unlock | Quiet Premium Italian phrasing |
| SAFE fallbacks if Gemini fails / `force_fallback` | Must pass `validate_rendered_text` + goal check |

**Critical invariant:** never render `lavori come {x}` unless `x` is a short structured `lavoro.ruolo` title (`looks_like_role_title`). Free-text priority / responsibilities must not become a job title.

- Module: `backend/ai_life_strategist/conversational_voice.py` (`render_conversational_turn`, `validate_rendered_text`, `safe_*_fallback`, `render_wrap_synthesis`)
- Reasoner: same-call spoken fields on `StrategistPlan` (`reasoner.py`)
- Turn assembly: `conversation_planner.py` (greeting / active / wrap)
- No second Gemini call on the happy active-turn path
- No progress bar / checklist / % in UI; soft progress only when near-complete + rich facts (4.1)
- FE thinking: in-thread “ORA sta pensando…” while composer disabled (no modal)
- First-run pre-MLC: FE hides Esci / Più tardi (backend cancel/postpone unchanged)
- life_places assist: action `use_current_location` → browser geolocation → `POST /api/life-setup/reverse-geocode` (Nominatim city) → user confirm → `POST /api/life-setup/confirm-location` (city only; **no** coord persistence; **no** expo-location)
- User-facing strings must not expose MLC / coverage / Life Graph / planner jargon
- Documents V2 pipeline unchanged; proposal copy frames upload as optional accelerator; turn actions include Non ora / Preferisco rispondere

## Life Experience / Strategist (2026-08-06)

- AI-first Life Experience: reasoning loop every turn → structured `StrategistPlan`.
- Gemini via Provider Manager with structured context JSON; deterministic Italian fallback.
- CE origin `life_setup` accepted; route `/life-setup` = conversational Life Experience behind the Gate.
- Collections: `life_setup_sessions`, `life_profiles`.
- Home adapter: **Italian benefit cards** after setup («Adesso posso…») + soft resume if interrupted — **no** Life Setup section.
- Proactive generator: benefit-driven suggestions + soft resume; never «Completa il profilo».
- Docs: `LIFE_EXPERIENCE.md`, `AI_REASONING_LOOP.md`, `AI_PROMPTING_GUIDE.md`, `AI_DECISION_POLICY.md`, `CONVERSATION_EXPERIENCE.md`.
- Adapter stubs only: email, open_banking, whatsapp, weather.

## Stack

| Layer | Choice |
|-------|--------|
| Mobile/Web client | Expo 54, React Native, TypeScript, expo-router |
| API | FastAPI + Uvicorn |
| DB | MongoDB via Motor |
| Auth | JWT ORA (HS256) + bcrypt; Google Login V2: GIS web + native Google Sign-In → ID token → `backend/social_auth/`; Apple ID-token verify; Emergent bridge legacy optional |
| LLM | Provider Manager `backend/llm/` — Gemini (default) → OpenAI → Ollama → Emergent; typed failover + process-local circuit breaker; non required at boot |

### Provider reliability contract (V2.8.3a)

Provider adapters translate external failures into a shared taxonomy. Quota,
rate limit, timeout, network, authentication/configuration, unavailable model
and malformed provider responses may fail over. An unknown ORA/application
error is non-failoverable and fails fast, so switching vendors cannot hide a
schema or implementation bug.

`LLMNotConfigured` means no enabled/configured provider. If at least one
configured provider was attempted, skipped for cooldown, or otherwise failed,
the manager raises `LLMProviderUnavailable` with at most eight sanitized
`provider/failure_kind/retryable/timestamp` records. No prompt, response,
credential, header or raw exception is retained.

The circuit breaker is bounded and process-local. Quota/rate-limit receive a
short cooldown, network/timeout a shorter one, and auth/configuration a longer
one. Numeric `Retry-After` can extend the cooldown up to five minutes; the
request never sleeps. `/llm/status` reads recent in-memory state without a
provider probe, continuous polling or distributed health claim.
| Design system | **ORA Quiet Premium** + **Signature Language** — `design_guidelines.json`, `frontend/src/theme/*`, shell modes in `frontend/src/shell/` (`ambient` / `focus` / `immersive`), primitives in `frontend/src/components/ui/` |
| Local deps | `backend/requirements-local.txt` (Emergent CDN packages excluded) |

## Repository map

```
backend/
  server.py              # thin FastAPI entry
  deps.py                # env, db, auth helpers, service getters
  routers/               # HTTP routers mounted under /api
  decision_engine/       # ranking & decisions
  life_graph/            # nodes/edges
  knowledge/             # node knowledge
  auto_link/             # decision↔node proposals
  context_assembler/     # context snapshots
  permissions/           # consents & capabilities
  connectors/            # google_calendar, apple_calendar
  ingestion/             # event pipeline
  documents/             # document intelligence
  documents/intelligence/# pipeline, taxonomy, analyzer, calendar drafts
  home/                  # Home V2 aggregator + ranking + adapters
                         # INTERNAL ranking (codes/weights) ≠ PRESENTATION
                         # (reason_presentation.format_reason_summary → human Italian)
  intent_engine/         # Intent Classification — single brain for flow routing
  action_engine/         # Guided conversational flows (consumes Intent)
    study/               # Study plan model, generator, confirm, Google/tools/Brain
    travel/              # Travel Project: period, maps, calendar confirm, Brain/Home
  goal_engine/           # Goal identity/lifecycle (shadow; no Goal UX yet)
  proactive_engine/      # IF/WHEN/HOW/WHY intervene → suggestions + Home ORA TI CONSIGLIA
  conversation_engine/   # Entry orchestrator (NOT chatbot) → Semantic→Intent→Gap→Goal→AE
  semantic_engine/       # Structured extraction + Gap Analyzer (Gemini optional)
  ai_life_strategist/    # Life Experience reasoning loop + StrategistPlan (Gemini + IT fallback)
  life_setup/            # First-launch Life Experience session + Life Profile persistence/sync
  life_objects/          # Life Object Engine (core identity; SHADOW mode)
  daily_intelligence/    # daily summary (situation indicators)
  behavioral_intelligence/
  behavior_aware_decisions/
  explainability/
  action_center/
  social_auth/           # Google/Apple verify, identities, linking
  llm/                   # Provider Manager + adapters (gemini/openai/ollama/emergent)
  security/              # token vault
  tests/                 # pytest
frontend/
  app/                   # expo-router screens (Home Quiet Premium + /situazione)
  app/(tabs)/            # Ambient IA: Home · Contesti · ORA · Memoria · Profilo (Documenti/Aggiungi href:null)
  app/action/[sessionId] # Action Engine UI — Focus shell chrome (no Ambient nav)
  src/api/client.ts      # HTTP client incl. /home
  src/auth/              # Adapter Google unico (.web GIS / .native SDK), availability, Apple helper
  src/shell/             # Application Shell V1: OraShellMode, AmbientTabBar, FocusScreen/Chrome, ImmersiveScreen
  src/components/home/quiet/ # Home Quiet Premium (+ polish 2.1: FocusActions, surface Focus, vertical Horizon)
  src/components/home/v2 # Legacy helpers + /situazione PrioritaList
  src/action-engine/     # ActionEngine.open(item) central entry
  src/conversation-engine/ # ConversationEngine.start → bridges to AE UI
  src/theme/          # Quiet Premium: tokens, palettes, ThemeProvider, motion, haptics, shadows
  src/components/ui/  # Design primitives (AppScreen, AppCard, AppButton, GlassContainer, …)
docs/                    # CONVERSATION_ENGINE_* + ACTION_ENGINE_* + HOME_V2_* + …
scripts/                 # local automation
.emergent/               # legacy Emergent runtime (non-portable)
.cursor/                 # Cursor autonomy rules/agents/hooks
```

## API surface (high level)

All routes under `/api` via `ALL_ROUTERS`:

- `auth` — register, login, google-session, me, logout
- `decisions`, `legacy_tasks`
- `life_graph`, `knowledge`, `auto_link`, `context`
- `permissions`, `connectors`, `ingestion`
- `google_calendar`, `apple_calendar`
- `daily`, `behavior`, `behavior_shadow`
- `documents`, `home` (V2 intelligence dashboard), `intent`, `action-engine`, `goals` (Goal Engine — backend only, unused by UI), `life-objects` (Life Object Engine — shadow; unused by main UI), `suggestions` (Proactive Engine), `conversation` (Conversation Engine orchestrator), `admin`, `memory`

Health:

- `GET /api/` → `{ "app": "ORA", "status": "ok" }`
- `GET /api/health` → app + database + llm configured flag + integration flags (no secrets)
- `GET /api/home` → Home V2 aggregate (`primary_focus`, situation, priorities, insights, resume, `ora_ti_consiglia` ≤3, warnings); ranking `home-rank-1.4` with temporal ownership (`ACTIVE` / `UPCOMING` / `EXPIRED_*` / `SUPERSEDED`) so actionable canonical LifeOsPlan shells outrank stale legacy plan decisions; Life OS CTAs → `/goal-workspace/{planId}`; optional `dev_rank_trace` when `HOME_RANK_TRACE`/`DEV`; Goal-aware when `GOAL_ENGINE_ENABLED` (item `goal_*` refs + dedupe — `docs/GOAL_AWARE_HOME.md`); Proactive when `PROACTIVE_ENGINE_ENABLED` — `docs/PROACTIVE_ENGINE_ARCHITECTURE.md`; Conversation resume via CE adapter — `docs/CONVERSATION_ENGINE_ARCHITECTURE.md`
- AI Core Life OS context: session `active_object_ref` / `current_plan_item_ref` / recent object refs (previews only); durable adaptations via `update_object` (revision + evidence preserve); `POST /api/life-os/session-focus` binds Workspace → chat continuity
- `/api/conversation/*` → start / message / continue / cancel / resume / history / summary (flag `CONVERSATION_ENGINE_ENABLED`); Conversation resume items when `CONVERSATION_ENGINE_ENABLED` — `docs/CONVERSATION_ENGINE_ARCHITECTURE.md`
- `POST /api/conversation/start|resume` + `/{id}/message|continue|cancel|pause` + history/summary — entry orchestrator (bridges to Action Engine UI)
- `GET /api/home/situation` → full situation view payload
- `POST /api/home/actions` → complete / snooze / ignore / correct / insight / banner
- `POST /api/home/refresh` → rebuild ranking snapshot
- `POST /api/intent/classify` → Intent Classification Engine (deterministic; optional LLM enrich)
- `POST /api/action-engine/open` → classify Intent → start/resume guided flow
- `GET /api/action-engine/sessions/{id}` → session + current turn
- `POST /api/action-engine/sessions/{id}/answer|back|draft|search-docs|preview|modify|confirm|complete|cancel`
- `GET/PATCH/DELETE /api/study-plans/{id}` (+ sessions actions, sync/retry)
- Mongo: `study_plans`, `study_sessions` (UTC; default TZ Europe/Rome)
- Goal Engine (shadow + Home context; **no Goal UX**): `GET/POST/PATCH/DELETE /api/goals`, `POST /api/goals/search|merge`, `POST /api/goals/{id}/archive`, `GET /api/goals/{id}/timeline`
- Mongo: `goals`, `goal_events` — Study/Travel confirm upserts Goals when `GOAL_ENGINE_ENABLED=1`
- Life Object Engine (shadow + enrichment + Digital Twin Knowledge): `GET/POST/PATCH/DELETE /api/life-objects`, search/merge/link/reason/trend/status; `/{id}/narrative|questions|insights|health|history|relationships|temporal` + refresh/enrich; `/{id}/facts|hypotheses|decisions|timeline|knowledge` (+ confirm/reject/outcome write minimi); `GET /home-v3-feed` (OFF). Mongo `life_objects`. Shadow hooks from Documents consume, Goal upsert, Travel/Study confirm → best-effort enrich + knowledge ingest. `LIFE_OBJECT_HOME_UI_ENABLED=0` → no Home UX change.
- Proactive Engine: `GET/POST /api/suggestions/*` (list, regenerate, search, dismiss/accept/complete/snooze/explain); Mongo `proactive_suggestions`, `proactive_learning`. Email/Finance/Weather/Health/WhatsApp **predisposed only** — never invent facts.

## Application Shell V1 (Signature Language)

Three presentation modes (`OraShellMode` in `frontend/src/shell/`):

| Mode | Role | Chrome |
|------|------|--------|
| `ambient` | Life OS browsing (tabs) | `AmbientTabBar` — floating glass bottom on phone/tablet; compact left rail **fixed `AMBIENT_RAIL_WIDTH` (80px)** at `desktop` breakpoint (`useBreakpoint`, not `Platform.OS===web`). Rail must not use `flex:1` (that stole ~50% width). Scene = remaining viewport. `useAmbientInset` only clears bottom bar — never `paddingLeft` for the rail. |
| `focus` | One-task guided work | `FocusScreen` + `FocusChrome` — single back **or** close, progress “N di M” when known, no Ambient nav. Action decision column uses `FOCUS_DECISION_MAX_WIDTH` (720), independent of Home editorial width. |
| `immersive` | Full attention | `ImmersiveScreen` foundation (Life Setup / deep flows keep their own UI) |

Primary Ambient IA: **Home · Contesti · ORA · Memoria · Profilo**. Documenti and Aggiungi stay as routes with `href: null` (reachable from Profilo). Center **ORA** opens the Conversation Engine Ask path (`/(tabs)/ora` + `OraInput`), not Aggiungi and not a chat. Glass via `GlassContainer` for Ambient nav only. Ambient ↔ Focus transition ~240ms; respects reduce-motion.

**Contesti Life Map V1 (Prompt 5):** Ambient screen `/(tabs)/contesti` composes existing reads only — `GET /life-setup/profile`, `GET /study-plans`, `GET /travel-projects` — via `frontend/src/components/contexts/quiet/` (`buildContextsMap`). No Contesti/Context Engine backend, no Life Graph UI, no Home priorities reuse. Sections omit when empty. Presentation labels for domains mirror `DOMAIN_LABELS_IT` (FE) without inventing missing areas. Life Objects list APIs exist (shadow) but are **not** wired into Contesti V1 to avoid duplicate/HOME-flag coupling.

Action proof path: `/action/[sessionId]` uses Focus chrome + `useTheme` (Light/Dark). Understood-summary chips are presentation-hidden in Focus (session slots unchanged).

**INTERNAL ≠ PRESENTATION (Micro-batch 3.S):** Ranking keeps `ReasonFactor` codes/weights for score/order. `reason_summary` / `explanation.summary` are human Italian from `home.reason_presentation` (never `"Tipo travel"` label joins). Study exam questions use entity `subject`/`exam` only — never Home/insight `title` / `display_title` as exam identity (`Quando è l'esame di {Subject}?` vs neutral `Quando è l'esame?`).

## Local topology

```
MongoDB :27017  →  FastAPI :8000  →  Expo web :8081 (EXPO_PUBLIC_BACKEND_URL)
```

Google Login V2: `localhost` e `127.0.0.1` sono Authorized JavaScript Origins distinti per GIS (`:8081`); il popup restituisce l'ID token in callback, mai nell'URL ORA. Google Calendar OAuth è separato: callback backend `:8000`, client secret/scopes/refresh token propri. Il backend verifica firma, issuer, scadenza, subject, nonce quando presente e `aud` contro `GOOGLE_ALLOWED_CLIENT_IDS` (fallback legacy esplicito ai soli client ID Login).

## Data store

MongoDB collections created/indexed at startup (users, tasks, decisions, life_nodes/edges, node_knowledge, link_proposals, context_snapshots, memories, permission_*, ingestion_events, connector_instances, secret_vault, google_oauth_sessions, documents-related, `home_snapshots` / `home_item_state` / `home_insights`, behavioral collections, `goals` / `goal_events`, `life_objects`, `proactive_suggestions` / `proactive_learning`, …).

Document binaries: local storage under `backend/data/documents/` (S3 backend stubbed for future).

## Memory Proposal & Governed Learning V2.8.3

```text
AI MemoryCandidate
→ schema/budget validation
→ deterministic Memory Governance
→ PROMOTE | CLARIFY | REJECT | SUPERSEDE | FORGET_ALLOWED | FORGET_DENIED
→ idempotent user-scoped persistence
→ observation
→ AI reasons again before user-facing claim
```

`MemoryCandidate` è opzionale, bounded e general-purpose: summary/value, open `kind` e
`identity_key`, authority, epistemic status, confidence, temporal scope, sensitivity,
provenance e relationship refs. La policy non interpreta domini o keyword: valida
durabilità, ownership, evidenza, incertezza, sensibilità e collisioni d'identità.
Quando presente, `identity_key` è la chiave canonica di collisione; l'open `kind`
resta fallback descrittivo e non può essere assunto stabile tra chiamate provider.
Le correzioni creano una nuova revisione canonica e marcano la precedente
`superseded`; Forget marca `forgotten`, senza delete distruttivo. `reasoning_epoch`
e `governance_key` impediscono doppie scritture sullo stesso turno/client-resume.

La collection sorgente resta `memories`; `life_memory_snapshots` resta cache derivata.
Indici non distruttivi: `(user_id,status,updated_at)` e unique sparse
`(user_id,governance_key)`. Il Context Broker legge soltanto record attivi e rende le
memorie promosse recuperabili cross-session. Nessuna Situation o device signal viene
promossa automaticamente.

Stage A espone soltanto un indice opaco dell'esistenza di Memory attiva; i contenuti
restano Stage B-only. Il ranking rispetta gli `source_hints` AI validati e distingue
ref governati mutabili da evidence Life Memory derivata/read-only. Guardrail di re-entry
impediscono claim di save/forget senza persistenza e contraddizioni dopo una mutation riuscita.

## External integrations

| Integration | Path | Local notes |
|-------------|------|-------------|
| Emergent Google login | `auth.emergentagent.com` + demobackend session-data | Not portable |
| Emergent LLM | `emergentintegrations` + `EMERGENT_LLM_KEY` | Key + package required |
| Google Calendar OAuth + write sync | `connectors/google_calendar` + `documents/intelligence/google_sync` | Scopes `calendar.events`; vault Fernet; see `docs/GOOGLE_CALENDAR_ARCHITECTURE.md` |
| Documents V2 (intelligent actions) | `documents/` + `intelligence/{service,study_tools,admin_extract}` + FE `DocumentUtilityPanel` | Pipeline `intel-docs-2.0`; study/quiz/admin APIs; see `docs/DOCUMENTS_V2_ARCHITECTURE.md` |
| Apple Calendar | expo-calendar / mock flag | Device or mock |
| litellm wheel | Emergent asset URL in requirements | May fail outside Emergent |

## Hosting / deploy (current)

- Historical preview: `https://ora-decision-engine.preview.emergentagent.com`
- iOS package id: `com.emergent.oradecisionengine.b7escs`
- Cursor-local target: Mongo + uvicorn `:8000` + Expo (`EXPO_PUBLIC_BACKEND_URL`)

## Local run (summary)

See `README.md` and `scripts/dev`. Details and gaps live in `docs/DEVELOPMENT_STATE.md`.
# V2.8.4 — Unified uncertainty contract

The canonical path is `AI Core → CognitiveDecision.uncertainty → runtime governance →
Context Broker / capability → observation → AI re-entry`. `MissingInformation.ref` provides
a bounded semantic identity for retrieval/ask/defer/assume decisions and repeated-question
protection; it is not a domain slot or router. Runtime governance validates schema, budgets,
question presence, repeated refs and unsafe assumptions, while the AI remains the sole owner
of whether uncertainty matters and which strategy is appropriate.

Only bounded aggregate metadata is observable. Question text, user text, raw evidence and
private reasoning are not persisted as telemetry. Existing Memory clarification remains a
governed compatibility surface; Life Setup remains bootstrap UX/policy; Action/Intent flows
remain legacy compatibility and are not extended as production reasoning owners.

# V2.8.5 — Life Context Graph

New module `backend/context_graph/` (`models.py`, `repository.py`, `service.py`), collection
`context_edges`, owned exclusively by `ContextGraphService`. It is deliberately separate from
the pre-existing, unrelated `backend/life_graph/` + `backend/knowledge/` + `backend/auto_link/`
subsystem: that subsystem is node-centric (creates its own duplicate node entities, e.g. a
`home`/`car` node), uses a closed `RelationType` enum that silently collapses any unrecognized
value to `generic`, and is consumed by ~15 unrelated product surfaces (Home, Documents, Action
Engine, Goal Engine, Life Setup, Proactive Engine) with no `ai_core` coupling today. Extending
it for AI-Core-governed epistemic edges would have required either duplicating canonical
entities as graph nodes (explicitly against the V2.8.5 design constraint) or breaking its
closed-vocabulary invariant for 15 unrelated consumers. The new module instead stores only
edges, using each entity's own existing canonical ref as node identity — no new node
collection, no duplication, minimal/reversible footprint (one new Mongo collection).

**Graph convergence decision: COEXISTENCE WITH A STRONG BOUNDARY** (CPO-approved), not a
canonical-merge and not an adapter-over-`life_graph`. `context_graph` is the sole source of
truth for relationships the AI Core itself authors; `life_graph`/`knowledge`/`auto_link` remain
canonical for their existing non-conversational consumers; `life_objects` remains canonical for
LifeObject↔LifeObject Digital Twin relationships. No bidirectional sync between the two worlds.
If a future surface needs to show AI-authored relationships, the correct extension is a
read-side projection from `context_graph`, never a write into `life_graph`.

Canonical path: `AI Core → CognitiveDecision.context_graph_updates → governance (schema/ref/
self-loop) → ContextGraphService.apply (ownership/idempotency/supersession) → observation → AI
re-entry`, and on the read side: `ContextNeed → Source Registry → life_context_graph source →
bounded 1-2 hop edge lookup seeded from AI-hinted refs + active Situation/Plan/Goal → ContextFact
evidence → AI reasoning`. Idempotency reuses Memory's `governance_key = f"{reasoning_epoch}:
{index}"` pattern (list of ≤2 proposals per turn); revision/history reuses Situation's
optimistic-concurrency shape. No second LLM call, no embedding call, no new database
technology — MongoDB only, exactly as instructed.

# V2.8.6a — Calendar foundation hardening (not yet an AI Core capability)

`backend/timezone_service.py` is a general-purpose, authority-tiered timezone resolver
(`resolve_user_timezone`) usable by any future AI Core capability without a live Google call or
GPS-derived residence inference — precedence: an explicit `users.settings.timezone` value
(`user_confirmed`) → the most recently synced calendar event's own IANA timezone, already
persisted locally on `life_nodes` by ingestion (`connector_calendar`) → a single named
`system_fallback` constant, always reported as such, never presented as confirmed. This is the
one new general-purpose primitive this batch introduces; everything else hardens existing
Calendar write/consent/idempotency machinery in place (real-provider `create_event` now checks
`extendedProperties.private.ora_event_id` before creating, exactly as the fake provider already
did; `GoogleCalendarSyncService.reschedule_draft()` is the first canonical update path for
document-derived drafts; `connectors/google_calendar/consent.py` wraps the existing
`PermissionService` for a future non-HTTP AI Core tool handler). The AI Core tool registry is
unchanged — Calendar remains bounded, read-only evidence only until V2.8.6b.

# V2.8.6b — AI-native Calendar Intelligence

Calendar becomes an AI Core capability, not a second reasoning system: one new module
`backend/conversation_engine/ai_core/tools/calendar_caps.py` wraps the V2.8.6a-hardened services
(`CalendarGateway`/`InternalCalendarProvider`, `GoogleCalendarSyncService`, `timezone_service`,
`connectors/google_calendar/consent.py`) behind four capabilities registered in the existing
`ToolRegistry` — `get_calendar_events` (`READ_ONLY`), `create_calendar_event`,
`update_calendar_event`, `cancel_calendar_event` (`REVERSIBLE_WRITE`, not
`CONSEQUENTIAL_WRITE`, which would hard-block them unconditionally). No new orchestrator, no
"CalendarFlow", no new confirmation UI, no new governance code, no new idempotency mechanism and
no Context Graph changes were introduced — each of those already existed for a general-purpose
reason and is reused as-is:

- **Confirmation**: reuses the pre-existing `response_mode="act"` mechanism (propose → wait for
  the user's next message → `response_mode="tool"`). No calendar-specific confirmation surface
  exists or was needed.
- **Governance**: reuses `_blocks_side_effect(uncertainty)`, which already applies to any
  `REVERSIBLE_WRITE` tool call — a calendar write with blocking uncertainty is stripped and
  downgraded to `answer` with zero calendar-specific governance code.
- **Idempotency**: local-draft idempotency reuses `InternalCalendarProvider.create_from_candidate`'s
  existing `(user_id, source_document_id, source_event_candidate_id)` keying, with
  `source_document_id="ai_core_conversation"` and `source_event_candidate_id=f"epoch:{reasoning_epoch}"`
  — a retried tool call for the same reasoning epoch never creates a duplicate local draft or
  Google event (Google-side idempotency itself is the V2.8.6a `create_event` fix, unchanged here).
- **Canonical ref**: AI-managed events use `calendar:{draft_id}` (`ced_...`), the same ref shape
  the Context Broker's `_calendar` source and the Context Graph already recognized since V2.8.5.
  Raw ingested Google events (`ingestion_events`, events the user already had before ORA touched
  anything) are surfaced by `get_calendar_events` for conflict-awareness evidence only, with
  `calendar_ref: None` — never directly actionable via update/cancel. No legacy-data migration.
- **Persist-before-claim**: `loop.py` gets a fourth instance of the pattern first built for
  Memory (V2.8.3) and Graph (V2.8.5) — `_CALENDAR_CLAIM_RE` detects the AI's own text claiming a
  calendar write succeeded; if no matching `create/update/cancel_calendar_event` Observation with
  `status="ok"` was actually confirmed this turn, a nudge Observation forces one honest re-entry,
  and a second false claim is hard-replaced with an honest retry message.

**Event vs Situation vs Plan vs Memory** is deliberately left to the AI's own judgment — the same
judgment it already applies to Situation vs Memory vs Graph — never a hardcoded decision tree. A
sentence with a time in it does not automatically become a calendar event, and "ricordami di X"
does not automatically mean Calendar either; both are prompt-level guidance (`prompt.py`'s new
"Calendar (temporal capability, V2.8.6b)" section), never a keyword-matched code branch
(`if "calendar" in text` / `if "ricordami" in text` are explicitly absent and statically checked
by `test_ai_native_calendar_v286b.py`'s `test_v`/`test_z`). Calendar's relationship to Situation,
Plan and the Context Graph is likewise AI-proposed via the existing `context_graph_updates`
channel (e.g. `situation → scheduled_as → calendar:ced_...`) using open predicates — the calendar
tool itself never auto-creates that edge, a Life OS plan item is never auto-promoted to a
calendar event, and a correction (e.g. "anzi il notaio è alle 10") updates the same event via its
canonical ref rather than creating a duplicate.

**Timezone**: every create/update resolves timezone exclusively through
`timezone_service.resolve_user_timezone` (or an explicit AI-stated IANA zone), and every write
Observation reports `{tz_name, authority}` back to the AI — no new hardcoded `Europe/Rome` was
added to the AI-native path; the constant remains solely `timezone_service.py`'s own documented
system-fallback default.

**Conflict awareness**: `get_calendar_events` computes a bounded, deterministic O(n²) overlap
check (capped at 20 events, ≤10 reported pairs) over the same bounded local window it already
returns — evidence only, the AI decides whether an overlap matters. No new scheduling engine, no
Google FreeBusy call (deferred as a documented future follow-up, not built in V1).

**Preparation for Continuous Life Reasoning** (not implemented, path only): `new event → local
draft (calendar_event_drafts) → canonical ref (calendar:ced_...) → Context Broker's existing
`_calendar` source → AI-proposed Context Graph relation → future reasoning surfaces`. No
background/proactive loop was added in this batch.

**calendar.read revocation policy (V2.8.6b final hardening gate)**: `get_calendar_events` checks
`calendar.read` consent before including any `source: "google_external"` item (the
`ingestion_events` mirror of previously-imported Google events) — a revoked connector immediately
stops that evidence from reaching the AI, even though the underlying documents are never deleted
(revocation is a visibility change, not a destructive cleanup). `source: "ora_managed"` events
(`calendar_event_drafts`, ORA's own local record) are unaffected by Google consent state — they
remain visible as ORA's own commitment, with `source` already making that provenance explicit so
they are never presented as current Google state. The payload carries `google_events_included`
and, when `false`, a `google_events_note` explaining why to the AI, so it never claims the
calendar is empty of Google commitments — it says access needs to be reauthorized instead. The
default time window (when the AI passes neither `time_min` nor `time_max`) resolves to a
UTC-aware "now", not the server's naive local clock — this was a pre-existing correctness gap
(naive-vs-aware ISO string comparison can silently exclude real events depending on the server's
local timezone offset) found while adding the tests above, fixed as part of the same batch.

**update_calendar_event on a cancelled event**: rejected explicitly and typed
(`status="rejected"`, `failure_kind="event_cancelled"`) before any consent check or Google call —
never reactivated, never recreated, never silently redirected to a different event. The AI is
told to ask the user rather than guess what they actually want.

# V2.9.1 — Life Change Signal (Continuous Life Reasoning foundation)

New module `backend/life_signals/` (`models.py`, `repository.py`, `service.py`, `emitters.py`),
collection `life_change_signals`. It is the event-driven foundation for the pipeline

```
life mutation → LifeChangeSignal → [V2.9.2] impact reasoning → [V2.9.3] attention → intervention
```

and it deliberately stops at the first arrow. **V2.9.1 answers "WHAT CHANGED?" and nothing
else.** It does not decide that a change matters (V2.9.2) and does not decide whether ORA should
speak (V2.9.3). Keeping those three questions in separate sprints is a binding architectural
constraint, not a scheduling convenience: collapsing them is exactly how a Life OS degrades into
"a chatbot with reminders".

**It is not a second brain.** A LifeChangeSignal is a neutral infrastructural fact — "a known
part of this user's life state was mutated and the mutation persisted". It carries no intent, no
notification text, no suggestion, no AI-assigned urgency or importance, and no domain label. No
new reasoning engine, no new orchestrator, no new generator was introduced; the existing AI Core,
Context Broker, Situation, Memory, Context Graph, Life OS, Calendar and Proactive Engine are all
unchanged in their own semantics.

**Emission point.** `conversation_engine/ai_core/loop.py` is, in production code, the *single*
call site of `SituationService.apply`, `ContextGraphService.apply` and
`MemoryGovernanceService.process`, and the executor for every Calendar and Life OS write
capability. Emitting there — from the exact places where each subsystem has already reported a
persisted outcome — gives one reviewable wiring point and required zero change to any mutation
subsystem's own code or contract. The `life_signals.emitters` adapters hold every rule about
which outcomes qualify, so `loop.py` gains only five thin `_emit_life_change(...)` calls.

**Three invariants**, enforced per adapter and covered by `test_life_change_signal_v291.py`:

- *Persist-before-signal* — only an outcome the owning subsystem itself reports as persisted
  produces a signal. A `response_mode="act"` proposal, a `consent_required` denial, a CLARIFY, a
  REJECT, a REVISION_CONFLICT, an explicit `operation="none"`, a read, or any failure produces
  nothing at all. No change ⇒ no signal ⇒ no future AI cost.
- *Idempotent* — the dedupe key derives from the stable identity of the mutation (entity ref +
  revision for Situation/Graph; `reasoning_epoch` + capability for Calendar/Life OS; the
  deterministic `mem_` id plus governance key for Memory), never a timestamp or a fresh UUID. A
  unique sparse index on `(user_id, dedupe_key)` enforces this at the storage layer too, so even
  a race cannot produce a duplicate. Where no stable discriminator is available the adapter fails
  closed rather than risk a duplicate storm.
- *Terminal* — emitting never mutates a life entity, never creates a Context Graph edge, never
  creates a proactive suggestion, and never emits a second signal. There is no
  mutation → signal → mutation loop.

**Refs reuse the existing canonical namespace** (`context_graph.models.is_recognized_ref`) rather
than inventing a second one; a structurally unrecognized ref is refused, not stored. A Context
Graph edge id (`lce_...`) is *not* a canonical ref, so a graph signal points at the edge's
**subject** — the entity whose relationships changed — and carries the object in `affected_refs`.
`affected_refs` only ever holds refs already present in the mutation result: V2.9.1 performs no
graph expansion and never asks the AI what else might be affected. That is V2.9.2's job.

**Privacy**: the stored document is refs plus technical metadata — never conversation text,
entity payloads, document content, tokens or secrets. A future consumer re-resolves authorized
context through the existing Context Broker instead of reading a duplicated copy of the user's
life. The Context Broker itself is deliberately *not* given a `life_change_signals` source: the
signal serves future asynchronous reasoning, not the normal per-turn answer.

**Failure isolation**: `LifeSignalService.emit()` never raises, and `loop.py`'s
`_emit_life_change` wraps it again. The primary mutation has already committed when the emitter
runs, so a signal-layer failure loses a derived event while leaving the user's real life state
correct — never a rollback. The failure stays observable through the
`life_change_signal_failures` trace counter and a warning log, never silently swallowed.

**Event-driven, never polling**: no cron, no scheduler, no background worker, no periodic Mongo
scan and no periodic LLM call was added. V2.9.1 adds **zero LLM calls** and **zero external
calls** — the signal is fully deterministic.

**Consumer contract** (no consumer ships yet): `list_pending(user_id, limit)` /
`count_pending` / `mark_processed` / `mark_failed`. Bounded (≤20), user-scoped, deterministically
ordered by `(created_at, id)`, and retry-safe because it neither locks nor mutates on read — a
consumer that crashes mid-batch simply sees the same signals again. Claiming/locking is
deliberately unimplemented: there is no worker to contend with, and a distributed lock here would
be premature.

**Connected mutation sources**: Situation, Life Memory, Context Graph, Life OS (plan/object),
Calendar. **Deferred**: Documents — its persistence points are spread across several
`documents.update_one` call sites in `documents/` and `documents/intelligence/` with no single
canonical AI-native mutation boundary, so connecting it would have meant either duplicating
emission logic across many sites or inventing a boundary this sprint was told not to design.
Four correct sources beat nine fragile ones.

# V2.9.2 — Impact Reasoning ("SO WHAT?")

New module `backend/life_reasoning/` (`models.py`, `repository.py`, `prompt.py`, `context.py`,
`service.py`), collection `life_impact_assessments`. It consumes the V2.9.1 signal store and
answers the second of the three questions:

```
V2.9.1  WHAT CHANGED?      deterministic runtime
V2.9.2  SO WHAT?           AI reasoning over bounded context   ← this batch
V2.9.3  SHOULD I SPEAK?    attention / intervention policy
```

**The pass**: `list_pending → deterministic batching → bounded context → ONE reasoning call per
batch → ImpactAssessment persisted → signals marked processed`. It is explicitly invoked —
`ImpactReasoningService(db).run_pass(user_id)` — with no worker, cron, scheduler or polling. A
user with no pending signals returns before any retrieval or reasoning happens, so the
`no change ⇒ no signal ⇒ no AI call` chain from V2.9.1 holds end to end.

**Batching is the cost model.** Signals are clustered when their canonical refs overlap directly
or when a Context Graph edge already connects them, using union-find over the bounded pending
set: three correlated changes cost one reasoning call, not three. Unrelated signals are
deliberately *not* merged — a shared prompt would let one part of the user's life contaminate the
conclusions drawn about another. Bounds: ≤5 signals per pass, ≤3 batches, ≤5 signals per batch,
so a pass costs at most three reasoning calls regardless of backlog. Clustering is fully
deterministic: same input, same batches, same order.

**Context resolution reuses existing infrastructure only** — there is no second context loader.
Relationships come from `ContextGraphService.relevant_edges` (the same bounded API the Context
Broker's own graph source uses, depth ≤2, ≤10 edges), evidence comes from
`ContextBroker.retrieve(stage="B", ...)` with its own Stage B budget, time comes from
`timezone_service.resolve_user_timezone`, and the capability catalogue comes from
`ToolRegistry.list_public()` — names only, never schemas or vendor brands. This is the first
place ORA uses the graph to widen the *meaning* of a change rather than merely to answer a turn,
and it is still bounded: seeded from the signal's own refs, never a global traversal, and it
never creates a relation.

**The ImpactAssessment contract** carries `impacts` (a single bounded list discriminated by
`kind` ∈ dependency | risk | opportunity | constraint | conflict | missing_information), plus
`relevance`, `confidence`, `requires_more_context`, `next_step_kind`, `focal_refs`,
`evidence_refs`, `evidence_count` and a short `reason_summary`. `epistemic_status` and
`authority` are **reused verbatim** from `MemoryCandidate`/`ContextEdge` — ORA has one epistemic
model and must not grow a third. The CPO sketch listed `impacts`, `unresolved_needs`,
`opportunities` and `contradictions` as four fields; they are modelled as one list plus a `kind`
discriminator because four near-identical parallel lists would each need their own bounds and
prompt section while `kind × epistemic_status` is strictly more expressive.

**What it deliberately cannot express**: there is no `notify`, `send_now`, `surface_home`,
`interrupt`, `batch_notification`, `message_to_user`, `chain_of_thought` or `thinking` field.
Even if a model emits them, the typed contract has nowhere to put them (asserted by test). No
chain-of-thought is ever requested or persisted — `reason_summary` is a bounded operational
conclusion, explicitly "what you concluded, not how you thought".

**Failure honesty**, all three paths asserted by test: an unavailable or unparseable provider
produces no assessment and leaves the signals pending; an unreadable Context Broker is treated as
different from an empty life (`ContextUnavailable` → defer, no AI call, no conclusion); and a
persistence failure never marks signals processed. Signals are consumed *only* after the
assessment is durably written — persist before consume, mirroring V2.9.1's persist before signal.

**Idempotency**: `batch_key` is a deterministic, order-independent hash of the signal ids in the
batch, enforced by a unique sparse index on `(user_id, batch_key)`. A replayed batch marks its
signals processed without writing a second assessment; a genuinely new signal (a correction, a
later change) yields a new batch key and a new, distinguishable assessment.

**Boundaries preserved**: no proactive suggestion, no notification, no message, no tool
execution, no Plan/Calendar/Memory/Graph mutation — verified by test even at maximum relevance. A
`capability_hint` may *point at* a capability ORA already has, and is validated against the live
registry so an invented capability name is dropped rather than stored as if it existed; nothing
is ever executed. The Proactive Engine, Context Broker, Context Graph, Memory governance and
Calendar semantics are all untouched.

**Provider access is exclusively through Provider Manager** (`llm.manager.get_manager().chat`),
so V2.8.3a failover and the circuit breaker stay in force; a static test forbids any direct
vendor import in the module.

**Commercial neutrality** is a prompt-level contract, asserted by test: when a change opens a real
choice the model may raise an `opportunity` noting that comparing options would help and name the
criteria that matter *for this user* — total cost, quality, reliability, fit, risk, stated
preferences — while optimising for the user's interest and never for whoever might be selling. It
must never name a company, product, vendor, brand or offer, and never invent a price or a rate:
V2.9.2 searches for nothing and must not imply that it has.

# V2.9.3 — Attention & Intervention Intelligence ("SHOULD I SPEAK?")

New module `backend/life_attention/` (`models.py`, `repository.py`, `prompt.py`, `context.py`,
`gate.py`, `service.py`), collection `life_attention_decisions`. It consumes V2.9.2's assessments
and closes the three-question sequence:

```
V2.9.1  WHAT CHANGED?      deterministic runtime
V2.9.2  SO WHAT?           AI reasoning over bounded context
V2.9.3  SHOULD I SPEAK?    AI judgement + deterministic system permission   ← this batch
```

**The central separation is between relevance and permission.** V2.9.2 can conclude that
something matters; that is not the same as being allowed to say it. V2.9.3 keeps the two
authorities in separate fields and never merges them:

- `ai_delivery` — what the model judged would help, kept verbatim even when overruled.
- `delivery` — what the deterministic gate permits. **This is the only field anything acts on.**

`life_attention/gate.py` can only ever move the outcome QUIETER along
`silent ← defer ← home ← ask_user ← propose_action ← notify`; a test asserts the one-way property
across every possible model choice. That is what makes it structurally impossible for a prompt —
or a model output — to grant ORA permission to interrupt someone.

**Silence is a first-class outcome.** An assessment reaching this layer does not imply a
suggestion. `silent` decisions are still persisted, deliberately: a decision *not* to speak is
what stops the next pass re-evaluating the same conclusions, and it is what makes "why did ORA
stay quiet?" an answerable question.

**Safety is never delegated to the prompt.** The model is told explicitly that it does *not*
decide whether the user is asleep, busy, has notifications enabled, or has already been told
this. It is not even shown those facts (`prompt_view` withholds `notifications_allowed`,
`quiet_hours`, `likely_sleep`, `interruption_cost` and `user_dismiss_rate`), so it cannot reason
around them. Interruption cost is computed deterministically from the resolved clock, real
calendar overlap, measured suggestion volume and recorded dismissal history.

**No second Proactive Engine was built.** A permitted decision becomes a `SuggestionCandidate`
and goes through the *existing* pipeline. `ProactiveEngineService.regenerate` was refactored by
extraction into `submit_candidates`, which both the legacy domain generators and the AI-native
path now call — so scoring, the `would_assistant_speak` gate, dedupe, learning and the
notification policy apply identically to both, and neither path can skip a check the other
honours. Legacy generators are untouched and coexist.

Three arguments exist on `submit_candidates` solely for the AI-native caller, all defaulting to
legacy behaviour: `quiet_hours_override`/`likely_sleep_override` supply values resolved through
`timezone_service` instead of the gate's fixed Europe/Rome approximation, and
`infer_activity_from_titles=False` disables the legacy "is the user driving?" calendar-title
keyword guess. Real occupancy still applies — the AI-native path knows the user is *busy*, and
declines to guess *what at*.

**A scoring ceiling was found and fixed.** `would_assistant_speak` requires a `generic` candidate
to reach 0.55, but importance/urgency/confidence alone top out at ~0.54 for a candidate carrying
neither a deadline nor a goal link. Every legacy generator happens to carry one or the other, so
the ceiling was invisible until a source emitted neither — it made the AI-native path effectively
unable to surface anything short of a perfect 1.0/1.0/1.0. The fix is one optional, domain-neutral
`quality_hint` on `SuggestionCandidate` (actionability and novelty, as judged by the emitting
layer), contributing a bounded explainable factor. Legacy generators leave it `None` and score
exactly as before, verified by the unchanged 232-test Proactive Engine suite.

**Dedupe is ref-based, not fuzzy.** Before submitting, the pass checks active suggestions —
legacy included — for overlapping canonical refs, comparing `meta.focal_refs` and the legacy
entity-id columns. Two items about the same entity are the same interruption to the person
reading them, however differently they are worded.

**Nothing is dispatched.** The reused notification policy structurally never returns
`send_now=True`, so a `notify` decision produces a Home item with a deferred batch window, never
a push. No tool is executed, no Plan/Calendar/Memory/Graph is written, and there is no worker,
cron, scheduler or polling: `AttentionService.run_pass(user_id)` is explicitly invoked, and a
user with no pending assessments returns before any context load or reasoning call.

# V2.9.4 — Continuous Life Reasoning orchestration

New module `backend/life_orchestration/` (`state.py`, `service.py`, `scheduler.py`), collection
`life_orchestration_state`. It turns the three previously hand-invoked passes into one operating
pipeline:

```
life mutation → LifeChangeSignal → ImpactAssessment → AttentionDecision → (only if permitted) Suggestion
```

**EVENT-DRIVEN, NOT POLLING-DRIVEN.** This is the load-bearing distinction and it is structural,
not stylistic:

- The worker blocks on `asyncio.Queue.get()`. While nothing changes it consumes no CPU, opens no
  cursor and touches Mongo zero times.
- A deferred decision gets ONE `asyncio.sleep` scheduled for its own moment — a one-shot alarm,
  not a loop that wakes up to look around.
- Recovery runs once, a few seconds after boot. There is no periodic re-scan.

A static test enforces this by parsing the module's AST and asserting that **no loop anywhere
contains a sleep call**, which is precisely the shape of a poll. The chain therefore holds end to
end: `no change ⇒ no signal ⇒ no wake-up ⇒ no reasoning ⇒ no AI cost`.

**Where the trigger lives.** `loop.py`'s `_emit_life_change` already knew when a signal was really
persisted; it now also calls `schedule_user_reasoning(user_id)` there, and only there. The call is
best-effort by construction — it never blocks, never raises and never awaits a provider — so a
mutation's response time is unaffected and eventual consistency is explicit: the user is answered
long before the pipeline concludes anything.

**Durability over convenience.** The in-process queue is an accelerator, never the queue of
record. A signal stays `pending` in Mongo until an assessment consumes it, so a dropped wake-up, a
full queue, a cancelled task or a dead process costs latency and never work. That is why
`schedule_user_reasoning` is allowed to fail silently, and why shutdown cancels rather than
drains.

**Coalescing.** One user gets at most one pending pass. Five near-simultaneous mutations produce
one pipeline, not five: subsequent wake-ups are counted and dropped, and a change arriving *while*
a pass runs sets a redo flag so it is picked up immediately afterwards rather than lost.

**Lease.** One collection, one granularity: the whole user pass. Leasing signals, assessments and
decisions separately would triple the bookkeeping to protect the same thing, because the expensive
resource is not any single record but the pair of AI calls a pass makes. The lease exists ONLY to
prevent double AI spend across processes — the unique indexes on `dedupe_key`, `batch_key` and
`decision_key` already make duplicate persistence impossible — so a lost or expired lease costs
money, never consistency. It is user-scoped, TTL-bounded (120s), reclaimable after a crash,
released only by its own owner, and identified by an opaque per-process id that is deliberately
not a hostname, pid or anything about the user.

Acquisition is written explicitly (try-take → check-exists → insert) rather than relying on an
upsert provoking a unique-index violation: if that index were ever missing, an upsert would
silently insert a second row and hand out a second lease, and *a lease that quietly stops working
is worse than no lease* because it looks like protection.

**Bounded pass.** `MAX_CYCLES = 2` — a second cycle exists only to pick up work that appeared
while the first ran, never to drain a backlog in a loop. Each sub-service keeps its own budget
(V2.9.2: ≤5 signals, ≤3 batches; V2.9.3: ≤5 assessments, ≤3 batches), so one pass is bounded above
by six reasoning calls and normally costs two. An idle user costs zero — checked before the lease
is even taken, so an idle pass does not write a single document.

**Failure isolation.** Impact failure leaves the signals pending and never fabricates an
assessment for attention to reason about. Attention failure leaves the assessment pending while
the signal stays correctly consumed. Both record a **per-user, per-pipeline** exponential backoff
(60s → 1h) in `life_orchestration_state`, deliberately distinct from the Provider Manager's
global, per-vendor circuit breaker: one stops hammering a provider, the other stops re-running one
user's pass in a tight loop.

**No recursion.** Nothing the pipeline produces feeds it again: creating an ImpactAssessment, an
AttentionDecision or a Suggestion emits no LifeChangeSignal. Emission is confined to the five
life-mutation points wired in V2.9.1, and a test asserts a full pass ends with exactly one signal
— the one it consumed.

**Legacy coexistence.** The orchestrator never calls `ProactiveEngineService.regenerate`, which
would re-run every legacy domain generator for free. It reaches the Proactive Engine only through
the `submit_candidates` path V2.9.3 already separated, so automatic reasoning adds no legacy cost.

## V2.9.4 — Deferred re-evaluation hardening

V2.9.3 persisted `defer_until` and nothing read it. V2.9.4's first phase made deferrals
*discoverable* (a one-shot timer, startup recovery) but deliberately stopped short of
reconsidering them — a genuine reconsideration needs a *second* decision about the same
assessments, which changes V2.9.3's idempotency contract and was flagged as a CPO decision rather
than settled inside an orchestration sprint. This hardening closes that point: a `defer` whose
moment arrives is now genuinely reconsidered by the AI.

**AI DECIDES. SYSTEM GUARANTEES.** — the load-bearing distinction, unchanged from V2.9.2/V2.9.3
and now extended to reconsideration: **the AI decides whether a deferral is still appropriate; the
system only bounds *automatic reconsideration***. The system may check eligibility, apply the
identical V2.9.3 gate, prevent duplicate work and cap *how many times* it will automatically ask
again — it may never itself conclude "deferred three times, therefore silent". That verdict, if it
happens, is the AI's, reached the same way as any first-time silent.

**Revision chain.** Every `AttentionDecision` now carries a `root_attention_key` — a stable,
order-independent hash of its assessment refs, shared by every reconsideration of the same
question — and an `attention_revision` counter. `decision_key` is `root` for revision 1
(identical to the pre-hardening key, so nothing written before this sprint changes identity) and
`root:rN` for revision N>1, so a retry of the same revision collides on the existing unique index
while a genuine reconsideration is a new key. History is append-only: a superseded decision keeps
its `delivery`, gains only `superseded_by`, and `latest_for_root` finds the current one by highest
revision regardless of whether that pointer write landed.

**Refresh, never re-derive.** A reconsideration re-fetches the *same* ImpactAssessment(s) by id and
a *refreshed operational context* (clock, quiet/sleep, calendar occupancy, notification
permission, learning, interruption cost) — it never re-runs Impact Reasoning (V2.9.2) and never
re-derives new assessments. Cost is therefore 0 Impact + at most 1 Attention call per due chain per
pass.

**The automatic budget is a COST ceiling, not a verdict.** `MAX_AUTOMATIC_DEFER_REEVALUATIONS = 3`
bounds how many times the system will *automatically* ask the AI to reconsider one root question.
Exhausting it sets `auto_re_evaluation_exhausted` and stops the automatic timer for that chain —
the decision itself stays exactly whatever the AI last chose (including `defer`, unforced toward
`silent`). A brand-new `LifeChangeSignal` about the same corner of someone's life still opens a
fresh root and reasons normally; only *automatic* reconsideration of the *same* exhausted question
is capped.

**Persistence order.** Build the new decision → persist it → *only then* mark the previous one
superseded → done. If the insert fails, the old deferral is untouched and fully retryable — no
Mongo transaction was introduced because this ordering already makes every step safe to retry or
lose independently, matching every other idempotency contract in this pipeline.

**Concurrency.** Reuses the same per-user lease V2.9.4's first phase introduced; `decision_key`'s
unique index is the second, storage-level line of defense against two processes reconsidering the
same chain at once.

**Suggestion path.** A reconsideration that produces a user-facing surface goes through the
existing Proactive Engine (`submit_candidates`) exactly like a first-time decision — no bypass, no
second engine, and the existing ref-based dedupe prevents a duplicate Home card for the same
question.

## V2.9.4 — Timer durability: two separate guarantees, not one atomic operation

The one-shot deferred-wake timer lives only in process memory (`life_orchestration/scheduler.py`'s
`_deferred_tasks`). Mongo's `defer_until` is the durable fact. **These are two separate writes to
two separate places, never one atomic operation** — persisting a `defer` decision and arming its
timer happen in the same code path (`_run_one`, right after a pass) but are not transactional, so a
process can die between them, or later, taking only the timer down with it. The correct mental
model is:

* **Mongo = durable source of truth.** A `defer` decision and its `defer_until` survive any crash.
* **Process-local timers = ephemeral wake-ups.** An accelerator, exactly like the in-process queue
  V2.9.4 already relies on for signals — never the record of what needs doing.
* **Startup recovery = complete, batch-bounded reconstruction.** Not a best-effort sample.

**Bounded query is not truncated recovery.** `OrchestrationService.iter_users_with_future_deferrals`
(and its siblings for pending signals, pending assessments, and already-due deferrals) page through
their collection in stable `_id` order, one indexed, capped batch at a time, until the collection is
exhausted — never a single capped read that silently drops whatever sorts past the cap. A boot with
51 users holding a future deferral rebuilds all 51 timers, in two pages, not 50. Each individual read
stays bounded (never a full-collection scan); the total work performed is not.

**Why this is still not polling.** Between pages, `recover_pending` yields to the event loop with
`await asyncio.sleep(0)` — a cooperative yield, not a wait: it returns control for one tick and
resumes immediately, so a large backlog costs time rather than blocking anything else the process is
doing. It never waits for a duration, never re-queries "has anything changed?" — that is the
structural difference from polling this whole module is built around. The walk is still finite: it
stops the moment a page comes back shorter than the batch size, runs exactly once per boot (fired as
a background task that startup never awaits), and is naturally idempotent — the same `_id`-cursor
walk run twice arms nothing twice, because `arm_deferred_timer` already refuses to duplicate a live
timer per user.

# PX1.1 — Calendar write consent (P0 fix)

A **real consent bug**, found by the PX1.1 audit of the legacy "Calendario automatico (soglia 90%)"
setting and fixed here. It is recorded in full because the shape of the mistake matters more than
the diff.

**What happened.** At the end of the document analysis pipeline,
`DocumentIntelligenceService._maybe_auto_add_calendar` read a stored user preference. If it was on,
and exactly one recognised event scored above `calendar_auto_add_threshold` (default 0.90), it
called:

```python
await self.confirm_event(user_id=..., doc_id=..., event_id=..., sync_to_google=True)
```

`confirm_event` is *the user's own confirmation function* — the one the UI calls when a person taps
confirm. Calling it from the pipeline created a calendar draft and synced a real event into the
user's real Google Calendar, unattended.

**Why it is a bug and not a feature.** Calendar Intelligence (V2.8.6b) states the contract plainly:
a WRITE requires explicit confirmation. This path bypassed it, with a confidence score standing in
for consent. A confidence score is a statement about the *model*, never a statement about what the
*person* agreed to, and no threshold converts one into the other. Note that connector-level consent
(`calendar.write`, granted at OAuth) was not the missing piece: that grants ORA the *ability* to
write, never permission for any *particular* write.

**The fix.** `_maybe_auto_add_calendar` now always refuses, returning
`{"attempted": False, "reason": "explicit_confirmation_required"}`. Nothing else about the pipeline
changes: the event is still extracted, still stored, still surfaced as a proposal. The only removed
capability is the system's ability to accept that proposal on the user's behalf.

The function was kept rather than deleted at its call site so the refusal is explicit and testable,
rather than an absence that could be reintroduced by accident.

**The preference.** `calendar_auto_add_enabled` is now inert, and `get_document_prefs` always
reports it as `False` — echoing a stored `true` would tell a client that unattended writes are
enabled when they cannot happen, which is the one thing a consent surface must never get wrong. The
field stays in the payload for client compatibility only.

**Tests.** `tests/test_documents_v2.py::test_calendar_write_always_requires_explicit_confirmation`
replaces an earlier test that asserted auto-add *refused* under certain conditions (low confidence,
several candidates, ambiguous date) — which implied it *proceeded* otherwise. It did. The contract
is now unconditional, and the test drives the exact shape that used to write: preference on, single
proposed event, unambiguous date, confidence 0.99.
