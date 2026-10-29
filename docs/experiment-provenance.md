# Dataset provenance in controlled runs

The controlled launcher saves the agent revision and selected model settings in
`experiment.json`. Its `dataset` field also records the resolved task directory,
the dataset Git commit, and whether files in the selected task directories were
modified or untracked when the run started. Compare these fields across arms.
Changes outside the selected tasks, such as a top-level `.DS_Store`, do not
invalidate the slice.

A real run rejects dirty selected tasks before starting Harbor or creating an
output directory. Use `--allow-dirty` only for a labeled local smoke test; both
agent and dataset dirtiness remain recorded. Dry runs can preview dirty inputs
without resolving credentials or launching Harbor.

For an unversioned task directory, the revision and dirtiness are `null`, rather
than a claim that the inputs are clean. Such a run is allowed, but matching
paths do not prove matching content. This metadata describes inputs at startup;
keep the task checkout unchanged until every arm has finished.

This change is separate from agent behavior. For selective main promotion it
requires only the standalone launcher port `8f5c060`, with no graph experiment.
