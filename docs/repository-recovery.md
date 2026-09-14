# Local repository recovery

`LocalRepo` records an effect's original and intended file contents before changing any file. It replaces each file atomically and records completion after all replacements finish. Retries reuse the saved contents and skip files already at their intended contents, so an interrupted multi-file append does not append twice.

The adapter now offers tier 1 idempotent application plus lookup. The coding-agent experiment's crash outcome is therefore `COMMITTED_BY_RETRY`; its resulting code and invariant verdicts are unchanged. A naive caller still duplicates appends because it assigns a new effect ID on every attempt.

Keep `.interlock-effects.jsonl` and its sidecars with the repository for as long as any effect may be retried. The target's records are separate from the gate's journal and are needed to distinguish this effect's changes from preexisting text. Reconcile unresolved effects from older versions manually before upgrading: those versions did not save target postimages.

Recovery checks authority and premises before resuming. If some files were changed before a crash and the approval is then revoked or a premise goes stale, the outcome stays unresolved with execution unknown. It cannot honestly report that nothing happened. Changes outside the recorded original and intended contents also require reconciliation; recovery does not overwrite them. Successfully recorded effects remain queryable after later edits.

Multi-file changes are recoverable, not an atomic transaction visible to arbitrary filesystem readers. Other writers must coordinate through the same adapter; unrestricted external writes can race the final checks. File and symbol premises continue to have the granularity limitations described in the main README.
