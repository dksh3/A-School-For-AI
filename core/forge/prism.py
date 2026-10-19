"""prism — the divergent→convergent brainstorming engine of the Forge suite.

``prism`` is the "10x superpowers" ideation core. It runs MANY divergent
techniques over one topic (first principles, SCAMPER, role-storming, worst-idea
inversion, random prompts, analogies, constraint removal, reverse, and
brainwriting that builds on prior ideas), records which technique produced each
idea, then converges: impact/feasibility scoring, ranking, top-N selection, and
theme clustering.

Universal by design — the lenses are domain-neutral, so a session works the same
way for coding, writing, research, business, planning, education, creative work,
ops, data, life, or anything else (``Domain.GENERAL`` fallback). Every public
function is fail-open: hostile input (None, ints, objects whose ``__str__`` /
``__bool__`` raise) returns a sensible result and never raises. With ``seed``
set, output is fully deterministic via ``random.Random(seed)``.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from core.forge.models import (
    BrainstormSession,
    Domain,
    Idea,
    _safe_float,
    _safe_int,
    _safe_list,
    _safe_str,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "TECHNIQUES",
    "brainstorm",
    "brainstorm_summary",
    "cluster_ideas",
    "score_ideas",
    "select_top",
]

#: Convergent scoring blend: ``score = impact*0.6 + feasibility*0.4``.
DEFAULT_WEIGHTS: dict[str, float] = {"impact": 0.6, "feasibility": 0.4}

#: Every divergent technique prism knows, in default run order.
TECHNIQUES: tuple[str, ...] = (
    "first_principles",
    "scamper",
    "role_storm",
    "worst_idea",
    "random_prompt",
    "analogy",
    "constraint_removal",
    "reverse",
    "brainwriting",
)

_MAX_COUNT = 500
_MAX_TITLE = 200
_MAX_DESC = 600
_TOPIC_LEN = 300

# Impact/feasibility priors per technique, as (impact_lo, impact_hi, feas_lo,
# feas_hi) on a 0..10 scale. Divergent techniques differ in temperament: e.g.
# constraint_removal is dreamy (low feasibility), brainwriting is incremental
# (high feasibility), worst_idea inversions skew bold (high impact).
_TECH_PRIORS: dict[str, tuple[float, float, float, float]] = {
    "first_principles": (5.0, 9.5, 3.5, 8.5),
    "scamper": (4.5, 9.0, 5.0, 9.5),
    "role_storm": (4.0, 8.5, 5.0, 9.0),
    "worst_idea": (5.5, 9.5, 4.5, 9.0),
    "random_prompt": (3.5, 8.5, 4.0, 9.0),
    "analogy": (5.0, 9.5, 3.5, 8.0),
    "constraint_removal": (5.0, 9.5, 2.5, 7.0),
    "reverse": (4.5, 9.0, 5.0, 9.5),
    "brainwriting": (4.0, 8.5, 6.0, 9.5),
    "baseline": (3.5, 7.5, 5.0, 9.0),
}

# Per-domain anchor phrases so idea copy lands on what the domain actually
# cares about. Any unknown domain falls back to the general phrase.
_DOMAIN_LENS: dict[str, str] = {
    "coding": "the developer or operator workflow",
    "writing": "the reader's experience",
    "research": "the evidence chain",
    "business": "customer value and willingness to pay",
    "planning": "sequencing, owners, and dependencies",
    "education": "learner progress and feedback loops",
    "creative": "the audience's feeling at the reveal",
    "ops": "reliability under load",
    "data": "signal quality and decision usefulness",
    "life": "daily habit fit and energy cost",
    "general": "the people it serves",
}

# --- divergent pools: (title template, description template, theme tag) ------
# {topic} is substituted at generation time. Each pool frames the topic
# differently: decompositions, moves, personas, inversions, forced
# associations, borrowed mechanisms, removed constraints, flipped failures,
# and additive builds.

_FP: tuple[tuple[str, str, str], ...] = (
    (
        "First principles: strip to the irreducible core of {topic}",
        "Decompose {topic} into irreducible parts and delete every assumed "
        "piece whose removal does not collapse the goal; rebuild around what "
        "survives.",
        "essentials",
    ),
    (
        "First principles: rebuild {topic} from raw constraints",
        "Separate the constraints on {topic} that are real physics from the "
        "ones that are merely inherited habit, and design only against the "
        "real ones.",
        "constraints",
    ),
    (
        "First principles: question the founding premise of {topic}",
        "Ask which 'obvious' goal behind {topic} is actually the wrong goal, "
        "and state the real goal plainly before designing anything.",
        "premise",
    ),
    (
        "First principles: zero-base the resources of {topic}",
        "Start {topic} from zero resources and add back only what earns its "
        "place; anything that cannot justify its line item stays out.",
        "focus",
    ),
    (
        "First principles: invert the objective of {topic}",
        "Optimize {topic} for the opposite metric for one minute, keep "
        "whatever that inversion reveals, then choose the metric deliberately.",
        "inversion",
    ),
    (
        "First principles: name the governing forces of {topic}",
        "Name the two or three forces that actually govern the outcome of "
        "{topic}, then design directly against them instead of against "
        "symptoms.",
        "leverage",
    ),
)

_SCAMPER: tuple[tuple[str, str, str], ...] = (
    (
        "SCAMPER Substitute: swap the engine under {topic}",
        "Swap the core material, method, or audience of {topic} for an "
        "opposite-class equivalent and keep only what still works.",
        "swap",
    ),
    (
        "SCAMPER Combine: fold {topic} into an adjacent workflow",
        "Merge {topic} with an unrelated workflow so one motion delivers both "
        "results; name what the shared motion makes possible.",
        "merge",
    ),
    (
        "SCAMPER Adapt: borrow a mature pattern for {topic}",
        "Find a pattern that is solved science in an adjacent field and adapt "
        "it to {topic}; keep the shape, change the materials.",
        "borrow",
    ),
    (
        "SCAMPER Modify: push one attribute of {topic} to its extreme",
        "Magnify or minify one attribute of {topic} - scale, speed, tone, "
        "weight - until the extreme itself becomes the feature.",
        "reshape",
    ),
    (
        "SCAMPER Put-to-other-use: repurpose {topic} for a new audience",
        "Repurpose {topic} for a different audience, moment, or problem than "
        "it was built for; name who benefits first and how they find it.",
        "repurpose",
    ),
    (
        "SCAMPER Eliminate: remove the 'essential' core of {topic}",
        "Remove the most essential-looking element of {topic} and design "
        "around the gap it leaves; what becomes possible without it?",
        "subtract",
    ),
    (
        "SCAMPER Reverse: run {topic} backwards",
        "Reverse or rearrange {topic} - run the stages backwards, flip who "
        "does what - and harvest the difference as a new design.",
        "flip",
    ),
)

_ROLE: tuple[tuple[str, str, str], ...] = (
    (
        "Role-storm as a skeptical first-time user: {topic}",
        "See {topic} only through a first-timer's eyes: what confuses them in "
        "the first 60 seconds, and what would make their first win unlosable?",
        "onboarding",
    ),
    (
        "Role-storm as a ruthless budget owner: {topic}",
        "See {topic} through the eyes of someone who pays for it: which part "
        "would they cut without blinking, and what must earn its line item?",
        "cost",
    ),
    (
        "Role-storm as a craft-obsessed perfectionist: {topic}",
        "See {topic} as a craftsperson would: which detail would they refuse "
        "to ship as-is, and where is quality actually perceived?",
        "quality",
    ),
    (
        "Role-storm as an exhausted end-of-day user: {topic}",
        "See {topic} at zero energy: what works on the worst day, and what can "
        "be removed so nothing requires fresh willpower?",
        "effort",
    ),
    (
        "Role-storm as a curious ten-year-old: {topic}",
        "See {topic} through a child's curiosity: what would make it "
        "delightful to poke at, and what would they call boring?",
        "delight",
    ),
    (
        "Role-storm as a hostile reviewer: {topic}",
        "See {topic} as its harshest critic: which claim would they attack "
        "first, and what evidence would silence them?",
        "risk",
    ),
    (
        "Role-storm as a historian from 2050: {topic}",
        "See {topic} from decades out: what will embarrass us about this "
        "approach, and what will look ahead of its time?",
        "legacy",
    ),
    (
        "Role-storm as a community organizer: {topic}",
        "See {topic} through collective action: who is currently excluded, and "
        "what change brings them in first?",
        "access",
    ),
    (
        "Role-storm as a stand-up comedian: {topic}",
        "See {topic} as a comic would: what is absurd here, and can the "
        "absurdity become the hook instead of the flaw?",
        "humor",
    ),
    (
        "Role-storm as an emergency-room triage nurse: {topic}",
        "See {topic} under surge load: what fails first, and what triage rule "
        "protects the core when everything is on fire?",
        "resilience",
    ),
    (
        "Role-storm as a minimalist designer: {topic}",
        "See {topic} with a deletion budget: what can be removed while keeping "
        "the soul, and what was decoration pretending to be structure?",
        "simplicity",
    ),
    (
        "Role-storm as a data auditor: {topic}",
        "See {topic} as an auditor demanding proof: what evidence would show "
        "it actually works, and which vanity metric should be retired?",
        "evidence",
    ),
)

_WORST: tuple[tuple[str, str, str], ...] = (
    (
        "Worst idea inverted: lead with value, ask second ({topic})",
        "Start from the worst possible take on {topic} - extract and charge "
        "before delivering any value - then invert it: lead with undeniable "
        "value first, ask second.",
        "value",
    ),
    (
        "Worst idea inverted: the first step is one step ({topic})",
        "Start from the worst take on {topic} - seven steps before any result "
        "- then invert it: deliver the first real result in a single step.",
        "speed",
    ),
    (
        "Worst idea inverted: make the first win unlosable ({topic})",
        "Start from the worst take on {topic} - make every user feel stupid - "
        "then invert it: design the first win so it cannot be lost.",
        "clarity",
    ),
    (
        "Worst idea inverted: surface the key action first ({topic})",
        "Start from the worst take on {topic} - hide the important thing "
        "behind three menus - then invert it: the key action is the first "
        "thing anyone sees.",
        "focus",
    ),
    (
        "Worst idea inverted: build the change loop in ({topic})",
        "Start from the worst take on {topic} - assume nothing ever changes - "
        "then invert it: build the change-and-learn loop into the design "
        "itself.",
        "adaptability",
    ),
    (
        "Worst idea inverted: invert the category default ({topic})",
        "Start from the worst take on {topic} - copy the most generic "
        "competitor exactly - then invert it: deliberately flip the category's "
        "default move.",
        "differentiation",
    ),
    (
        "Worst idea inverted: reversible by default ({topic})",
        "Start from the worst take on {topic} - make every action impossible "
        "to undo - then invert it: every action is reversible by default.",
        "safety",
    ),
    (
        "Worst idea inverted: the audience is the hero ({topic})",
        "Start from the worst take on {topic} - talk about ourselves the whole "
        "time - then invert it: the audience is the hero of every "
        "touchpoint.",
        "audience",
    ),
)

_RANDOM: tuple[tuple[str, str, str], ...] = (
    (
        "Random prompt 'garden': tend {topic} like a garden",
        "Forced association: treat {topic} as a garden. What gets pruned, what "
        "gets trellised, and what needs a season of patience before it shows?",
        "organic",
    ),
    (
        "Random prompt 'backpack': pack {topic} for the trail",
        "Forced association: {topic} is a backpack on a long hike. What must "
        "be carried, what is dead weight, and what belongs at base camp?",
        "essentials",
    ),
    (
        "Random prompt 'traffic': redesign the flow of {topic}",
        "Forced association: {topic} is an intersection at rush hour. Where "
        "are the jams, and would a roundabout beat another stoplight?",
        "flow",
    ),
    (
        "Random prompt 'recipe': write {topic} as a recipe",
        "Forced association: {topic} is a recipe. What are the ingredients and "
        "order of operations, and what happens when one ingredient is missing?",
        "structure",
    ),
    (
        "Random prompt 'orchestra': conduct {topic}",
        "Forced association: {topic} is an orchestra. Who is out of tune, who "
        "needs the conductor's attention, and what is merely loud?",
        "coordination",
    ),
    (
        "Random prompt 'kaleidoscope': refract {topic}",
        "Forced association: {topic} is a kaleidoscope. Which fragment, turned "
        "one click, refracts into a beautiful new pattern?",
        "reframe",
    ),
    (
        "Random prompt 'lighthouse': make {topic} a beacon",
        "Forced association: {topic} is a lighthouse. What warning or beacon "
        "does the audience actually need, and what gets lost in fog?",
        "guidance",
    ),
    (
        "Random prompt 'thrift store': find the hidden value in {topic}",
        "Forced association: {topic} is a thrift store. What discarded part of "
        "an old attempt is quietly valuable on the second look?",
        "reuse",
    ),
    (
        "Random prompt 'bicycle': simplify {topic} to pure leverage",
        "Forced association: {topic} is a bicycle. What simple mechanism "
        "removes the need for a motor entirely?",
        "leverage",
    ),
    (
        "Random prompt 'campfire': build a ritual around {topic}",
        "Forced association: {topic} is a campfire. What brings people back "
        "again and again, and what keeps it from going out?",
        "ritual",
    ),
    (
        "Random prompt 'storm': stress-test {topic} in bad weather",
        "Forced association: {topic} is a small boat in a storm. What does it "
        "look like in worst weather, and what is the one thing that must not "
        "get wet?",
        "stress",
    ),
    (
        "Random prompt 'puzzle': find the keystone of {topic}",
        "Forced association: {topic} is a jigsaw puzzle. Which single piece "
        "locks everything else into place and should be found first?",
        "keystone",
    ),
    (
        "Random prompt 'mirror': show the audience themselves in {topic}",
        "Forced association: {topic} is a mirror. What does the audience see "
        "of themselves here, and is that worth returning to?",
        "identity",
    ),
    (
        "Random prompt 'elevator': compress {topic} to 30 seconds",
        "Forced association: {topic} is an elevator ride. Can the whole point "
        "survive 30 seconds, and what gets cut first when it cannot?",
        "compression",
    ),
    (
        "Random prompt 'bridge': name the gap {topic} crosses",
        "Forced association: {topic} is a bridge. Which gap is it actually "
        "crossing, for whom, and what happens to those left on the near side?",
        "connection",
    ),
    (
        "Random prompt 'seeds': make {topic} self-compounding",
        "Forced association: {topic} is a handful of seeds. What tiny start "
        "could grow unattended, and what soil does it need once?",
        "compounding",
    ),
)

_ANALOGY: tuple[tuple[str, str, str], ...] = (
    (
        "Analogy from ant colonies: coordinate {topic} without a manager",
        "Study how ant colonies coordinate without a manager - simple local "
        "rules, stigmergy, redundancy - and port that mechanism into {topic}.",
        "systems",
    ),
    (
        "Analogy from immune systems: give {topic} memory and proportion",
        "Study how immune systems detect, remember, and respond "
        "proportionally, then port that pattern into {topic}: what is the "
        "antibody and what is the memory cell?",
        "defense",
    ),
    (
        "Analogy from jazz improvisation: give {topic} a key and freedom",
        "Study how jazz holds structure plus freedom inside a shared key, and "
        "port that tension into {topic}: where is the head and where is the "
        "solo?",
        "improv",
    ),
    (
        "Analogy from theme parks: choreograph {topic} like a queue",
        "Study how theme parks design queues and choreograph delight, then "
        "port that into {topic}: where is the wait, and where is the reveal?",
        "choreography",
    ),
    (
        "Analogy from emergency rooms: triage {topic} under scarcity",
        "Study how emergency rooms triage under scarcity - severity first, "
        "fast loops, clear handoffs - and port that protocol into {topic}.",
        "triage",
    ),
    (
        "Analogy from origami: fold constraints into elegance for {topic}",
        "Study how origami produces elegance by folding constraints instead of "
        "fighting them, and port that into {topic}: which constraint becomes a "
        "crease?",
        "elegance",
    ),
    (
        "Analogy from libraries: curate discoverability for {topic}",
        "Study how libraries create discoverability through quiet curation, "
        "and port that into {topic}: what is the catalog and what is the "
        "reading room?",
        "curation",
    ),
    (
        "Analogy from beekeeping: tend conditions, harvest surplus ({topic})",
        "Study how beekeepers tend conditions and harvest only the surplus, "
        "then port that ethic into {topic}: what is the hive, and what is the "
        "honey?",
        "stewardship",
    ),
    (
        "Analogy from chess openings: give {topic} principled starts",
        "Study how chess openings favor principled starts that outlast the "
        "first ten moves, and port that into {topic}: what is the opening "
        "repertoire?",
        "strategy",
    ),
    (
        "Analogy from orchards: plant {topic} once, harvest for years",
        "Study how orchards trade one planting for years of harvest, and port "
        "that into {topic}: what is the tree, and what is the seasonal labor?",
        "longevity",
    ),
    (
        "Analogy from public transit: frequency beats luxury for {topic}",
        "Study how public transit creates usefulness with frequency rather "
        "than luxury, and port that into {topic}: what must simply come more "
        "often?",
        "reliability",
    ),
    (
        "Analogy from stage magic: design the reveal of {topic}",
        "Study how stage magic uses misdirection and reveal as design tools, "
        "and port that into {topic}: where should attention go, and when is "
        "the turn?",
        "surprise",
    ),
)

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "Constraint removed: {topic} when budget is unlimited",
        "Assume the money constraint is gone for {topic}. What ambition appears "
        "the moment cost stops the conversation - and which part survives a "
        "real budget?",
        "ambition",
    ),
    (
        "Constraint removed: {topic} when time is unlimited",
        "Assume the deadline is gone for {topic}. Which craft, depth, or "
        "patient move becomes possible - and what is its cheap pilot?",
        "depth",
    ),
    (
        "Constraint removed: {topic} for an audience of one",
        "Assume {topic} serves exactly one specific person. What intimacy or "
        "precision unlocks - and would anyone else still want it?",
        "focus",
    ),
    (
        "Constraint removed: {topic} for an audience of millions",
        "Assume {topic} must serve millions on day one. Which automation or "
        "self-serve move becomes mandatory - and what is its smallest seed?",
        "scale",
    ),
    (
        "Constraint removed: {topic} with zero expertise required",
        "Assume no prior knowledge is allowed for {topic}. What must become "
        "self-explanatory - and what hidden prerequisite was doing damage?",
        "simplicity",
    ),
    (
        "Constraint removed: {topic} where everything is reversible",
        "Assume every action in {topic} can be undone. Which fear disappears, "
        "what do people try first - and which undo is worth building?",
        "safety",
    ),
    (
        "Constraint removed: {topic} with no words allowed",
        "Assume {topic} may not use language at all. What pure form, visual, "
        "or gesture carries the meaning - and what does words-only hide?",
        "expression",
    ),
    (
        "Constraint removed: {topic} that must work offline",
        "Assume {topic} must work with no network. Which fragility disappears, "
        "what must live locally - and which sync is actually needed?",
        "resilience",
    ),
    (
        "Constraint removed: {topic} that must ship today",
        "Assume {topic} must be live by tonight. What is the true minimum "
        "worth shipping - and what does 'tonight' prove about the rest?",
        "urgency",
    ),
    (
        "Constraint removed: {topic} without the current tool",
        "Assume the current tool or platform is gone for {topic}. Which quiet "
        "constraint was shaping everything - and what freedom is worth "
        "keeping?",
        "freedom",
    ),
)

_REVERSE: tuple[tuple[str, str, str], ...] = (
    (
        "Reverse: make the first step of {topic} take 60 seconds",
        "Anti-goal for {topic}: guarantee failure by making the first step "
        "require a 40-page manual. Invert every driver: the first step is "
        "completable in 60 seconds.",
        "onboarding",
    ),
    (
        "Reverse: celebrate the behavior that compounds ({topic})",
        "Anti-goal for {topic}: guarantee failure by rewarding the wrong "
        "behavior loudly. Invert: celebrate exactly the behavior that "
        "compounds and starve the rest of attention.",
        "incentives",
    ),
    (
        "Reverse: act on the cheapest useful signal ({topic})",
        "Anti-goal for {topic}: guarantee failure by waiting for perfect "
        "information. Invert: act on the cheapest useful signal today and "
        "treat each result as a paid-for lesson.",
        "momentum",
    ),
    (
        "Reverse: shrink the surface, deepen the core ({topic})",
        "Anti-goal for {topic}: guarantee failure by growing the surface area "
        "every week. Invert: shrink the surface while deepening the core until "
        "the center is undeniable.",
        "focus",
    ),
    (
        "Reverse: pin the dependencies that matter ({topic})",
        "Anti-goal for {topic}: guarantee failure by leaving every dependency "
        "optional until it breaks. Invert: pin the few dependencies that "
        "matter and make their health visible.",
        "stability",
    ),
    (
        "Reverse: optimize {topic} for week-two daily use",
        "Anti-goal for {topic}: guarantee failure by optimizing for the demo. "
        "Invert: optimize for week-two daily use - the tenth session is the "
        "real customer.",
        "durability",
    ),
)

#: Brainwriting additions: (addition, theme tag). Builds on prior ideas.
_BW_ADDITIONS: tuple[tuple[str, str], ...] = (
    ("a self-serve starter kit", "onboarding"),
    ("a measurement loop with one honest metric", "evidence"),
    ("a community-shared variant", "community"),
    ("a weekly ritual around the first win", "ritual"),
    ("a habit-sized two-minute version", "effort"),
    ("an undo or rollback story", "safety"),
    ("a teach-it-to-a-newcomer version", "clarity"),
    ("a partner-boosted edition", "leverage"),
    ("a stripped pilot for one real user", "focus"),
    ("a celebration moment at first success", "delight"),
)

#: Safety-net pool used only to top up when generators fail.
_BASELINE: tuple[tuple[str, str, str], ...] = (
    (
        "Baseline: start {topic} smaller than feels comfortable",
        "Start {topic} smaller than feels comfortable and let real demand pull "
        "the next layer.",
        "focus",
    ),
    (
        "Baseline: find who is already halfway to {topic}",
        "Find the people already halfway to {topic} and design for the half "
        "they are missing.",
        "audience",
    ),
    (
        "Baseline: make the first win of {topic} unlosable",
        "Design {topic} so the first win is unlosable; everything else can "
        "iterate after trust exists.",
        "momentum",
    ),
    (
        "Baseline: remove one moving part from {topic}",
        "Remove exactly one moving part from {topic} and see which "
        "complication leaves with it.",
        "simplicity",
    ),
    (
        "Baseline: steal a ritual for {topic} from another field",
        "Borrow one proven ritual from an unrelated field and stage it inside "
        "{topic}.",
        "borrow",
    ),
    (
        "Baseline: make {topic} teachable in five minutes",
        "Make {topic} teachable in five minutes; the constraint will expose "
        "what is essential.",
        "clarity",
    ),
)


# --- fail-open internals ----------------------------------------------------

def _fill(template: str, topic: str) -> str:
    """Substitute ``{topic}`` safely. Never raises."""
    try:
        return template.replace("{topic}", topic)
    except Exception:  # noqa: BLE001
        return template


def _roll(rng: random.Random, lo: float, hi: float) -> float:
    """Draw a 0..10-scale score in tenths. Never raises for sane bounds."""
    return round(rng.randint(int(lo * 10), int(hi * 10)) / 10.0, 1)


def _make_idea(
    rng: random.Random,
    technique: str,
    title: str,
    description: str,
    theme: str,
) -> Idea:
    """Build one ``Idea`` with technique-flavored impact/feasibility priors."""
    lo_i, hi_i, lo_f, hi_f = _TECH_PRIORS.get(technique, (4.0, 8.0, 4.0, 8.5))
    tech = _safe_str(technique)
    return Idea(
        title=_safe_str(title)[:_MAX_TITLE],
        description=_safe_str(description)[:_MAX_DESC],
        technique=tech,
        impact=_roll(rng, lo_i, hi_i),
        feasibility=_roll(rng, lo_f, hi_f),
        tags=[tech, _safe_str(theme) or "general"],
    )


def _domain_lens(domain: Domain) -> str:
    """A domain-appropriate anchor phrase. Never raises."""
    try:
        key = domain.value if isinstance(domain, Domain) else _safe_str(domain)
    except Exception:  # noqa: BLE001
        key = ""
    return _DOMAIN_LENS.get(key, _DOMAIN_LENS["general"])


def _gen_pool(
    topic: str,
    domain: Domain,
    rng: random.Random,
    prior: Sequence[Idea],
    technique: str,
    pool: Sequence[tuple[str, str, str]],
    use_domain_lens: bool = False,
) -> Idea | None:
    """Generic technique: pick one lens from ``pool`` and instantiate it."""
    del prior  # pool techniques do not build on prior ideas
    title, desc, theme = rng.choice(pool)
    desc = _fill(desc, topic)
    if use_domain_lens:
        desc += f" Anchor one detail on {_domain_lens(domain)}."
    return _make_idea(rng, technique, _fill(title, topic), desc, theme)


def _gen_brainwriting(
    topic: str,
    domain: Domain,
    rng: random.Random,
    prior: Sequence[Idea],
) -> Idea | None:
    """Brainwriting: build on a prior idea (or seed the sheet)."""
    del domain
    addition, theme = rng.choice(_BW_ADDITIONS)
    base_titles: list[str] = []
    for idea in prior:
        try:
            t = _safe_str(idea.title).strip()
        except Exception:  # noqa: BLE001
            continue
        if t:
            base_titles.append(t)
    if base_titles:
        base = rng.choice(base_titles)
        title = f"Brainwriting: {base} + {addition}"
        desc = (
            f"Build on the earlier idea '{base}' by adding {addition}: keep "
            f"its engine, change exactly one thing, and note what the "
            f"combination unlocks for {topic}."
        )
    else:
        title = f"Brainwriting: seed {topic} with {addition}"
        desc = (
            f"No prior ideas yet - open the sheet by proposing {addition} as "
            f"the first building block of {topic}, so the next pass has "
            f"something to build on."
        )
    return _make_idea(rng, "brainwriting", title, desc, theme)


_GENERATORS: dict[str, Callable[..., Idea | None]] = {
    "first_principles": partial(_gen_pool, technique="first_principles", pool=_FP),
    "scamper": partial(_gen_pool, technique="scamper", pool=_SCAMPER),
    "role_storm": partial(
        _gen_pool, technique="role_storm", pool=_ROLE, use_domain_lens=True
    ),
    "worst_idea": partial(_gen_pool, technique="worst_idea", pool=_WORST),
    "random_prompt": partial(
        _gen_pool, technique="random_prompt", pool=_RANDOM, use_domain_lens=True
    ),
    "analogy": partial(
        _gen_pool, technique="analogy", pool=_ANALOGY, use_domain_lens=True
    ),
    "constraint_removal": partial(
        _gen_pool, technique="constraint_removal", pool=_CONSTRAINTS
    ),
    "reverse": partial(_gen_pool, technique="reverse", pool=_REVERSE),
    "brainwriting": _gen_brainwriting,
}

#: Friendly aliases accepted in the ``techniques`` argument.
_ALIASES: dict[str, str] = {
    "firstprinciples": "first_principles",
    "first_principle": "first_principles",
    "scamper_variant": "scamper",
    "scamper_variants": "scamper",
    "rolestorm": "role_storm",
    "role_storming": "role_storm",
    "rolestorming": "role_storm",
    "worst": "worst_idea",
    "worstideas": "worst_idea",
    "random": "random_prompt",
    "random_prompts": "random_prompt",
    "analogy": "analogy",
    "analogies": "analogy",
    "constraint": "constraint_removal",
    "constraints": "constraint_removal",
    "constraint_removal": "constraint_removal",
    "reverse_brasstorm": "reverse",
    "inversion": "reverse",
    "brain_writing": "brainwriting",
}


def _invoke(
    name: str,
    topic: str,
    domain: Domain,
    rng: random.Random,
    prior: Sequence[Idea],
) -> Idea | None:
    """Run one technique generator; return None instead of raising."""
    gen = _GENERATORS.get(name)
    if gen is None:
        return None
    try:
        return gen(topic, domain, rng, prior)
    except Exception:  # noqa: BLE001
        return None


def _add_unique(ideas: list[Idea], idea: Idea | None, seen: set[str]) -> bool:
    """Append ``idea`` with a collision-free title. Never raises."""
    try:
        if idea is None:
            return False
        title = _safe_str(idea.title).strip() or f"idea {len(ideas) + 1}"
        if title in seen:
            title = f"{title} (variation {len(ideas) + 1})"
        idea.title = title
        seen.add(title)
        ideas.append(idea)
        return True
    except Exception:  # noqa: BLE001
        return False


def _make_rng(seed: Any) -> random.Random:
    """Deterministic RNG when ``seed`` is usable, entropy otherwise."""
    try:
        if seed is None:
            return random.Random()
        return random.Random(seed)
    except Exception:  # noqa: BLE001
        return random.Random()


def _resolve_count(count: Any) -> int:
    """Coerce ``count`` to an int in [0, _MAX_COUNT]. Never raises."""
    try:
        n = _safe_int(count, 12)
    except Exception:  # noqa: BLE001
        n = 12
    return max(0, min(_MAX_COUNT, n))


def _resolve_techniques(techniques: Any) -> list[str]:
    """Normalize the requested technique names; fall back to all. Never raises."""
    default = list(TECHNIQUES)
    try:
        if techniques is None:
            return default
        raw = [techniques] if isinstance(techniques, str) else _safe_list(techniques)
        names: list[str] = []
        for item in raw:
            name = _safe_str(item).lower().strip().replace("-", "_").replace(" ", "_")
            name = _ALIASES.get(name, name)
            if name in _GENERATORS and name not in names:
                names.append(name)
        return names or default
    except Exception:  # noqa: BLE001
        return default


def _resolve_weights(weights: Any) -> tuple[float, float]:
    """Coerce scoring weights to clamped floats. Never raises."""
    w_i, w_f = DEFAULT_WEIGHTS["impact"], DEFAULT_WEIGHTS["feasibility"]
    try:
        if isinstance(weights, dict):
            if "impact" in weights:
                w_i = _safe_float(weights.get("impact"), w_i)
            if "feasibility" in weights:
                w_f = _safe_float(weights.get("feasibility"), w_f)
    except Exception:  # noqa: BLE001
        return DEFAULT_WEIGHTS["impact"], DEFAULT_WEIGHTS["feasibility"]
    return min(10.0, max(0.0, w_i)), min(10.0, max(0.0, w_f))


def _empty_session(obj: Any) -> BrainstormSession:
    """Best-effort session from junk input. Never raises."""
    try:
        return BrainstormSession(topic=_safe_str(obj)[:_TOPIC_LEN])
    except Exception:  # noqa: BLE001
        return BrainstormSession()


def _coerce_session(obj: Any) -> BrainstormSession:
    """Accept a session, dict, or ``to_dict``-able and return a session.

    Hostile input becomes a fresh empty session instead of raising.
    """
    try:
        if isinstance(obj, BrainstormSession):
            return obj
        if isinstance(obj, dict):
            return BrainstormSession.from_dict(obj)
        return BrainstormSession.from_dict(obj.to_dict())
    except Exception:  # noqa: BLE001
        return _empty_session(obj)


def _estimate(idea: Any) -> tuple[float, float]:
    """Deterministic impact/feasibility estimate for unscored ideas.

    Uses a stable rolling hash (never built-in ``hash``, which is randomized
    per process) so estimates are reproducible across runs.
    """
    try:
        text = "|".join(
            _safe_str(getattr(idea, key, "")) for key in ("title", "description", "technique")
        )
        h = 0
        for ch in text:
            h = (h * 131 + ord(ch)) % 1000003
        return round(3.0 + (h % 700) / 100.0, 1), round(3.0 + ((h // 700) % 700) / 100.0, 1)
    except Exception:  # noqa: BLE001
        return 5.0, 5.0


def _idea_axes(idea: Any) -> tuple[float, float]:
    """Clamped (impact, feasibility) in 0..10; estimates when both unset."""
    impact = _safe_float(getattr(idea, "impact", 0.0))
    feas = _safe_float(getattr(idea, "feasibility", 0.0))
    if impact == 0.0 and feas == 0.0:
        impact, feas = _estimate(idea)
    return min(10.0, max(0.0, impact)), min(10.0, max(0.0, feas))


def _score_of(idea: Any) -> float:
    """Safe score accessor for sorting. Never raises."""
    try:
        return _safe_float(getattr(idea, "score", 0.0))
    except Exception:  # noqa: BLE001
        return 0.0


def _idea_view(idea: Any, index: int) -> dict[str, Any]:
    """Compact JSON-safe view of one idea. Never raises."""
    fallback = {
        "title": f"idea {index + 1}",
        "technique": "",
        "score": 0.0,
        "impact": 0.0,
        "feasibility": 0.0,
    }
    try:
        return {
            "title": _safe_str(getattr(idea, "title", "")) or fallback["title"],
            "technique": _safe_str(getattr(idea, "technique", "")),
            "score": round(_safe_float(getattr(idea, "score", 0.0)), 4),
            "impact": round(_safe_float(getattr(idea, "impact", 0.0)), 4),
            "feasibility": round(_safe_float(getattr(idea, "feasibility", 0.0)), 4),
        }
    except Exception:  # noqa: BLE001
        return fallback


# --- public API (all fail-open) --------------------------------------------

def brainstorm(
    topic: Any,
    domain: Any = Domain.GENERAL,
    techniques: Any = None,
    count: Any = 12,
    seed: Any = None,
) -> BrainstormSession:
    """Divergent multi-technique generation, then convergent scoring.

    Runs the requested techniques round-robin until at least ``count`` ideas
    exist (each idea records its producing technique in ``technique_counts``),
    then scores and sorts the session. Fail-open: hostile ``topic``/``domain``/
    ``techniques``/``count``/``seed`` never raise. With ``seed`` set the whole
    session is deterministic.
    """
    ideas: list[Idea] = []
    session: BrainstormSession | None = None
    try:
        topic_s = _safe_str(topic).strip()[:_TOPIC_LEN]
        topic_label = topic_s or "the topic"
        dom = Domain.coerce(domain)
        names = _resolve_techniques(techniques)
        rng = _make_rng(seed)
        n = _resolve_count(count)
        seen: set[str] = set()
        attempts = 0
        max_attempts = max(n, 1) * len(names) * 2 + 10
        while len(ideas) < n and attempts < max_attempts:
            attempts += 1
            name = names[(attempts - 1) % len(names)]
            _add_unique(ideas, _invoke(name, topic_label, dom, rng, ideas), seen)
        # safety net: guarantee at least `count` ideas, whatever happened
        while len(ideas) < n:
            fallback = _gen_pool(topic_label, dom, rng, ideas, "baseline", _BASELINE)
            if not _add_unique(ideas, fallback, seen):
                break
        counts: dict[str, int] = {name: 0 for name in names}
        for idea in ideas:
            key = _safe_str(idea.technique) or "baseline"
            counts[key] = counts.get(key, 0) + 1
        session = BrainstormSession(
            topic=topic_s,
            domain=dom,
            ideas=ideas,
            technique_counts=counts,
        )
    except Exception:  # noqa: BLE001
        session = None
    if not isinstance(session, BrainstormSession):
        try:
            session = BrainstormSession(ideas=list(ideas))
        except Exception:  # noqa: BLE001
            session = BrainstormSession()
    return score_ideas(session)


def score_ideas(session: Any, weights: Any = None) -> BrainstormSession:
    """Convergent phase: score every idea and sort best-first. Never raises.

    ``score = impact*w_impact + feasibility*w_feasibility`` with the default
    weights of 0.6/0.4. Ideas with both axes at zero get a deterministic
    estimate so hand-built or imported sessions still rank meaningfully.
    """
    try:
        sess = _coerce_session(session)
    except Exception:  # noqa: BLE001
        sess = BrainstormSession()
    try:
        w_i, w_f = _resolve_weights(weights)
        for idea in sess.ideas:
            try:
                impact, feas = _idea_axes(idea)
                idea.impact = impact
                idea.feasibility = feas
                idea.score = round(impact * w_i + feas * w_f, 4)
            except Exception:  # noqa: BLE001
                continue
        sess.ideas.sort(key=_score_of, reverse=True)
    except Exception:  # noqa: BLE001
        return sess
    return sess


def select_top(session: Any, n: Any = 3) -> BrainstormSession:
    """Fill ``session.selected`` with the top-``n`` idea titles. Never raises."""
    try:
        sess = _coerce_session(session)
    except Exception:  # noqa: BLE001
        sess = BrainstormSession()
    try:
        k = max(0, min(_MAX_COUNT, _safe_int(n, 3)))
        ranked = sorted(sess.ideas, key=_score_of, reverse=True)
        titles: list[str] = []
        for idx, idea in enumerate(ranked[:k]):
            try:
                title = _safe_str(idea.title).strip() or f"idea {idx + 1}"
            except Exception:  # noqa: BLE001
                title = f"idea {idx + 1}"
            titles.append(title)
        sess.selected = titles
    except Exception:  # noqa: BLE001
        return sess
    return sess


def cluster_ideas(session: Any) -> dict[str, list[str]]:
    """Group idea titles by tag/theme; untagged ideas land in "untagged"."""
    clusters: dict[str, list[str]] = {}
    try:
        sess = _coerce_session(session)
    except Exception:  # noqa: BLE001
        return clusters
    try:
        for idx, idea in enumerate(sess.ideas):
            try:
                title = _safe_str(getattr(idea, "title", "")).strip() or f"idea {idx + 1}"
                tags = [
                    t for t in (_safe_str(x) for x in _safe_list(getattr(idea, "tags", []))) if t
                ]
            except Exception:  # noqa: BLE001
                continue
            for tag in tags or ["untagged"]:
                clusters.setdefault(tag, []).append(title)
    except Exception:  # noqa: BLE001
        return clusters
    return clusters


def brainstorm_summary(session: Any) -> dict[str, Any]:
    """Counts, top ideas, and technique breakdown for a session. Never raises."""
    try:
        sess = _coerce_session(session)
    except Exception:  # noqa: BLE001
        return {}
    try:
        views = [_idea_view(idea, idx) for idx, idea in enumerate(sess.ideas)]
        views.sort(key=lambda v: v["score"], reverse=True)
        total = max(1, len(views))
        counts = {
            _safe_str(k): _safe_int(v, 0) for k, v in dict(sess.technique_counts).items()
        }
        domain = (
            sess.domain.value if isinstance(sess.domain, Domain) else _safe_str(sess.domain)
        )
        return {
            "id": _safe_str(sess.id),
            "topic": _safe_str(sess.topic),
            "domain": domain,
            "slug": _safe_str(sess.slug),
            "idea_count": len(views),
            "selected": [_safe_str(s) for s in _safe_list(sess.selected)],
            "selected_count": len(_safe_list(sess.selected)),
            "technique_counts": counts,
            "techniques_used": sorted(k for k, v in counts.items() if v > 0),
            "top_ideas": views[:5],
            "cluster_sizes": {k: len(v) for k, v in cluster_ideas(sess).items()},
            "averages": {
                "impact": round(sum(v["impact"] for v in views) / total, 3),
                "feasibility": round(sum(v["feasibility"] for v in views) / total, 3),
                "score": round(sum(v["score"] for v in views) / total, 3),
            },
        }
    except Exception:  # noqa: BLE001
        return {}
