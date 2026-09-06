# Source-grounded writing track

This track tests whether a model can transform a fixed evidence packet and a
separate user brief into useful German professional writing. It is distinct
from both summarization and online research:

- candidate models receive the same frozen evidence;
- candidates do not browse or select sources;
- the evidence packet is not a prepared narrative;
- the requested output must synthesize across sources and integrate the user's
  own position;
- research quality and source selection will be evaluated later in a separate
  online-research track.

## Input design

Cases use two candidate-visible artifacts:

1. a source-separated evidence packet with stable location labels;
2. exactly three user-authored thoughts with separate stable labels.

The runner verifies both hashes and injects them into different prompt
placeholders. Judge bundles preserve them as separate files. This prevents the
source material from becoming a project-authored article that candidates only
need to shorten.

Evidence packets use atomic source cards. Each card identifies its source,
evidence type, measured findings and limitations. Cards do not contain
cross-source transitions, an overall thesis or a recommended conclusion.

## Development cases

- [`ai-transformation-value-gap`](dev/ai-transformation-value-gap/README.md)
- [`agentic-software-development-reality-gap`](dev/agentic-software-development-reality-gap/README.md)
