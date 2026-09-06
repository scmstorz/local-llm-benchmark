# Source packet: Agentic software development and the reality gap

This packet deliberately does not form a continuous argument. It contains five
source-separated evidence cards. Each card preserves the scope, method,
measurements and limitations of its own publication. Section order does not
imply importance, and no cross-source conclusion is supplied.

The stable labels `[S01]` through `[S25]` exist for evaluation traceability.
They must not appear in the candidate output.

## Source 1 - SWE-Lancer

**Publication:** Samuel Miserendino, Michele Wang, Tejal Patwardhan and
Johannes Heidecke, *SWE-Lancer: Can Frontier LLMs Earn $1 Million from
Real-World Freelance Software Engineering?*, ICML 2025.

**Source type:** Execution-based benchmark constructed from paid freelance
software-engineering work.

[S01] SWE-Lancer contains 1,488 software-engineering tasks originally posted
on Upwork for the Expensify codebase, with USD 1 million in actual historical
payouts. Its 764 individual-contributor tasks, worth USD 414,775, ask a model
to implement bug fixes or features in a repository. Its 724 management tasks,
worth USD 585,225, ask a model to select the best proposal among alternatives
that freelancers submitted for a real issue. Task payouts ranged from small
bug fixes to feature implementations worth tens of thousands of dollars.

[S02] Individual-contributor patches were evaluated with browser-based
end-to-end tests written by professional engineers and triple-verified for
quality. Models did not see those tests. Management answers were compared with
the proposal selected in the original project; a separate validation campaign
with experienced engineers reported 99 percent agreement with those original
choices. These are stronger verifiers than judging code style or textual
plausibility alone, but they still operationalize success through the available
tests and recorded management decision.

[S03] On the 502-task public Diamond split used in the paper, the strongest
evaluated model, Claude 3.5 Sonnet, solved 26.2 percent of individual-
contributor tasks and 44.9 percent of management tasks at pass@1. Across both
categories it scored 36.1 percent and captured USD 208,050 of USD 500,800 in
available payouts. On the complete dataset it captured about USD 403,000 of
USD 1 million. These figures describe the specific 2024-2025 models, scaffold
and dataset version evaluated in the paper; they are not a current leaderboard.

[S04] More inference effort changed the result. For o1 on Diamond individual-
contributor tasks, pass@1 rose from 9.3 percent at low reasoning effort to 16.5
percent at high effort. Allowing six additional attempts nearly tripled the
estimated share of tasks solved by o1. A preliminary model-first, human-
fallback calculation estimated that five o1 attempts before escalation could
reduce total cost by 33.5 percent. That calculation assumed fast verification,
historical freelance prices and the API costs used in the study; the authors
note that real verification can take more than 24 hours.

[S05] The benchmark is broader than short function-generation tests but not a
sample of all software work. Every task came from one company, one codebase and
one freelance platform; infrastructure engineering and greenfield development
were underrepresented. Freelance issues can be more self-contained than full-
time engineering work. Agents could not ask clarifying questions, and the
evaluation was text-only even when original issues contained visual material.
The public 2023-2024 issues also create possible training-data or search
contamination, so browsing must be disabled or controlled.

## Source 2 - SWE-agent

**Publication:** John Yang et al., *SWE-agent: Agent-Computer Interfaces Enable
Automated Software Engineering*, NeurIPS 2024.

**Source type:** Agent-system design study with interface ablations and
execution-based software benchmarks.

[S06] SWE-agent treats a language model as a computer user whose interface can
be designed for its particular limitations. Its agent-computer interface
provides a compact set of commands for navigating repositories, searching,
viewing and editing files, plus concise feedback and guardrails. The study
holds the underlying model fixed while changing this interface, so it measures
how much of a model's capability the surrounding system can elicit.

[S07] With GPT-4 Turbo, SWE-agent resolved 12.47 percent of the full SWE-bench
test set, compared with 1.31 percent for the retrieval-augmented, non-agentic
baseline reported in the same evaluation. On the 300-case SWE-bench Lite
subset, the complete interface resolved 18 percent, versus 11 percent for a
shell-only agent. These were state-of-the-art results at publication time, not
evidence about the best models or agents available later.

[S08] Interface ablations materially changed success with the same model. On
SWE-bench Lite, removing the dedicated editor reduced resolution from 18 to
10.3 percent; keeping the editor but removing lint-based guardrails reduced it
to 15 percent. Showing either only 30 lines or an entire file performed worse
than a 100-line viewer. An iterative search interface that encouraged the
agent to inspect matches one by one scored 12 percent, while summarized search
scored 18 percent. More tools or more context were therefore not automatically
better.

[S09] Trajectory analysis exposed operational signals hidden by a pass rate.
At least one edit failed in 51.7 percent of GPT-4 Turbo trajectories. Successful
runs finished at a median of 12 steps and USD 1.21, whereas unsuccessful runs
averaged 21 steps and USD 2.52. An automated failure classification attributed
about 52 percent of unresolved Lite cases to incorrect or overly specific
implementations and 23.4 percent to cascading failed edits; its labels agreed
with the authors on 87 percent of a hand-checked sample.

[S10] The study demonstrates a model-by-interface interaction, not an intrinsic
score for GPT-4 or a timeless recipe for agents. Its main results used one
historical model generation, a public benchmark of Python repository issues
and a finite cost budget. The interface was designed around observed model
behavior and then tested for some portability to Claude 3 Opus. Different
models, tasks, tools, feedback strength and context strategies can move the
capability boundary again.

## Source 3 - Measuring AI Ability to Complete Long Software Tasks

**Publication:** Thomas Kwa et al., *Measuring AI Ability to Complete Long
Software Tasks*, NeurIPS 2025, arXiv revision 4 dated July 2026.

**Source type:** Multi-model capability evaluation using human task duration
as the difficulty scale.

[S11] The paper defines a model-agent's 50-percent task-completion time horizon
as the human-expert task duration at which the fitted probability of agent
success is 50 percent. The main suite combines 66 newly constructed shorter
software tasks with HCAST and RE-Bench tasks, for 170 tasks in total. Human
experts supplied completion-time baselines, agents attempted the tasks, and a
logistic model related success probability to human task duration. Each
evaluated agent consisted of a model plus a scaffold.

[S12] Across 11 frontier models released from 2019 through early 2025, the
estimated 50-percent horizon doubled every 207 days, with a bootstrapped
95-percent interval of 166 to 240 days. GPT-2's estimated horizon was about two
seconds; o3's was about 110 minutes and it succeeded on several tasks taking
humans more than four hours. The authors are more confident in the trend's
slope than in the absolute horizon assigned to any one model.

[S13] Reliability changes the interpretation. The historical growth rate for
the 80-percent horizon was similar, but models' 80-percent horizons were four
to six times shorter than their 50-percent horizons. The dataset was not large
enough to estimate very high reliability such as 95 percent confidently. A
model that sometimes finishes an hours-long task therefore does not follow
from this evidence to be dependable on hours-long work.

[S14] Qualitative comparison suggested that newer agents were better at tool
use, logical reasoning and adapting after mistakes rather than repeating
failed actions. Agents still performed worse on less structured or "messier"
tasks, especially when feedback loops were weak or relevant information had to
be sought proactively. Human task duration predicted success, but domain,
scaffold, task structure and the reference human population also affected the
measured horizon.

[S15] The tasks rarely required interaction with other people or agents,
dynamic environments, severe resource constraints or production-grade
reliability, and most offered relatively clear automated feedback. The paper's
month-long-agent dates are explicitly conditional extrapolations: they assume
the measured exponential trend continues and generalizes to real software
work. The authors warn that task-distribution and external-validity problems
could prevent that inference.

## Source 4 - Experienced open-source developer productivity

**Publication:** Joel Becker, Nate Rush, Beth Barnes and David Rein,
*Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer
Productivity*, METR, July 2025.

**Source type:** Randomized controlled trial on real repository work with
screen recordings and self-reported implementation time.

[S16] Sixteen experienced open-source developers completed 246 real bug fixes,
features and refactors in mature repositories to which they regularly
contributed. They averaged about five years of experience in the relevant
repository, and tasks averaged two hours. Each issue was specified before
random assignment to AI-allowed or AI-disallowed work. In the AI condition,
developers primarily used Cursor Pro with Claude 3.5 or 3.7 Sonnet. Total
implementation time included work before and after pull-request review.

[S17] Allowing early-2025 AI tools increased measured completion time by an
estimated 19 percent. Before assignment, developers had predicted that AI
would make them 24 percent faster. After participating, they still estimated
that AI had made them 20 percent faster. Economics and machine-learning
experts had also forecast large speedups. The result is therefore both a
productivity finding for this setting and a measured gap between perceived and
observed impact.

[S18] Several observations help explain the measured slowdown without proving
one single mechanism. Developers accepted fewer than 44 percent of AI
generations, most reported making major changes to clean up generated code,
and the labeled recordings attributed about 9 percent of AI-allowed time to
reviewing and cleaning AI output. Participants also reported that models often
missed tacit repository context, conventions and compatibility constraints
that experienced maintainers already knew.

[S19] The study distinguishes its question from autonomous coding benchmarks.
Benchmarks typically give a fully autonomous agent a well-scoped task, large
inference budgets and an algorithmic verifier. This trial studied a human using
AI in repositories with real review, testing, documentation and style
requirements. A strong benchmark result and a human productivity loss need not
be logically inconsistent when the task distribution, success definition,
tooling and human-agent workflow differ.

[S20] The authors warn against generalization. The sample contained only 16
developers, all highly experienced with their repositories and their quality
standards; selected issues were real but tended toward the shorter side of
their work. The treatment captured tools available from February through June
2025. The result does not establish that AI slows most developers, novices,
people entering unfamiliar codebases, other workflows or future systems.

## Source 5 - DORA 2025 State of AI-assisted Software Development

**Publication:** Derek DeBellis et al., *DORA 2025 State of AI-assisted
Software Development Report*, DORA and Google, version 2025.2.

**Source type:** Global cross-sectional survey, qualitative interviews and
model-based observational analysis.

[S21] The report draws on 4,867 technology-professional survey respondents and
78 semi-structured interviews. Survey recruitment combined open community
channels with a supplemental panel, and respondents from more than 100
countries participated. The interviews ran from July 2024 through July 2025;
76 of the 78 interviewees were in the United States. Survey responses were
self-reported, and not every respondent saw every question because people were
randomly assigned to four overlapping survey paths.

[S22] Ninety percent of survey respondents reported using AI at work. More
than 80 percent perceived that AI had increased their individual productivity,
although 41 percent described the increase as only slight. Fifty-nine percent
perceived improved code quality, while 30 percent reported little or no trust
in AI-generated code. These figures measure reported use, perception and
trust; they are not direct telemetry or randomized productivity effects.

[S23] In DORA's adjusted observational models, higher AI adoption was
associated with higher reported individual effectiveness, code quality, team
performance, organizational performance, product performance and software-
delivery throughput. It was also associated with greater software-delivery
instability and showed no measurable relationship with friction or burnout.
The report interprets this pattern as local acceleration entering a larger
sociotechnical system whose review, delivery and coordination mechanisms may
not adapt automatically.

[S24] DORA tested 15 candidate organizational capabilities and retained seven
that showed substantial evidence of interacting with AI adoption: a clear and
communicated AI stance, healthy data ecosystems, AI-accessible internal data,
strong version-control practices, working in small batches, user-centric
focus, and quality internal platforms. Different capabilities moderated
different outcomes; the model does not say that buying one tool or adopting
all seven practices guarantees performance.

[S25] The report calls AI an amplifier of organizational strengths and
dysfunctions and recommends treating adoption as a systems problem. This is an
interpretation of survey associations, interviews, prior literature and a
theory-driven Bayesian analysis, not a randomized organizational experiment.
The authors explicitly advise organizations to use the findings to form
hypotheses, run experiments and measure results in their own context.
