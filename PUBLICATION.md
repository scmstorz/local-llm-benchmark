# Public release policy

This project is developed in a local research repository that contains more
material than the public GitHub repository. Public releases are clean snapshots
with their own history. The local research history is never pushed directly.

## Included

The public snapshot is built from an explicit allowlist:

- Python package code and offline tests;
- versioned benchmark tasks, prompts, synthetic fixtures, and verifier
  contracts;
- model catalog, lifecycle policy, and cohort manifests;
- harness capability inventories and isolation profiles;
- the exactly pinned Pi integration;
- curated public-safe Markdown and JSON reports;
- methodological documentation;
- root packaging and repository documentation; and
- the public-snapshot exporter itself.

## Excluded

The following remain local even if they are tracked in the research history:

- copyrighted source articles and paper text;
- personal writing inputs and non-public holdouts;
- rendered prompts containing private inputs, raw responses, Ollama event
  streams, and agent trajectories;
- candidate-to-model mappings and interactive judge bundles;
- raw run directories and machine-specific paths (sanitized aggregate
  experiment IDs may remain in curated reports);
- screenshots and other case-study working assets;
- the chronological research diary and mutable project status notes; and
- editor, environment, dependency, cache, and build artifacts.

Project-authored reference dossiers are public where they summarize and cite
sources without reproducing them. All log-incident fixtures are synthetic.

## Reproducible export

Create a snapshot only from a clean committed worktree:

```bash
python3 scripts/export_public_snapshot.py /tmp/local-llm-benchmark-public
```

The exporter copies only tracked allowlisted paths and prints every tracked
path it excluded. It refuses to overwrite a non-empty destination.

Run the repository-owned privacy, file and local-link gate before creating a
Git history:

```bash
python3 scripts/audit_public_snapshot.py /tmp/local-llm-benchmark-public
```

The exported directory is then audited as a new repository. At minimum:

```bash
cd /tmp/local-llm-benchmark-public
git init
git add -A
git diff --cached --check -- README.md PUBLICATION.md scripts
python3 scripts/run_public_tests.py
git status --short
```

The initial root snapshot preserves byte-identical frozen benchmark artifacts,
including a few historical Markdown hard breaks and extra final blank lines.
Running `git diff --cached --check` over the entire root addition would flag
those bytes. Do not reformat hash-bound artifacts merely to make that initial
check quiet. The scoped command above checks the newly maintained release
surface; normal later commits should use an unscoped `git diff --check`.

The full research-repository test suite is a separate gate. It additionally
depends on locally installed Pi packages, non-redistributed source fixtures and
the private commit history referenced by frozen experiment plans; it is not a
valid command for a clean public snapshot.

Before a push, also inspect the staged path list and URLs manually. A dedicated
scanner such as Gitleaks should be added when it is available, but it does not
replace the repository-owned gate or manual inspection of benchmark content.

## History boundary

The public `main` branch begins with the first sanitized snapshot. Subsequent
public releases should be built from this same allowlist and committed on top
of the public branch. This retains a useful public history without disclosing
files that existed only in the local research history.

The local research branch and public branch are intentionally not expected to
share ancestry.

## Licensing

No open-source license has been selected yet. Publication makes the source
visible, but normal copyright restrictions remain until a license file is
added by the repository owner.
