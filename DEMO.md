# Plumbline demo script

## LangChain deep agents track (60 seconds)

**Before judging:** run `ollama serve` (with `gpt-oss:20b` pulled), start the app, open How it thinks. Pre-run one claim
(CLM-2207) so a finished live run with a trace link is ready, and keep a second one (CLM-2223) unrun to start live.

1. **The problem (10 s).** "Property managers, rent reviewers and lenders pay for building work they never saw.
   Plumbline's deep agent checks every claim against the building itself: CoStar records, Vexcel aerial imagery and
   Matterport 3D scans."
2. **Start a live run (15 s).** Claims → CLM-2223 → Run agent. As steps stream in, point out:
   the coordinator writes its **to-do list** (`write_todos`), sends **sub-agents** (records clerk, roof inspector,
   interior inspector) through `task`, reads its **long-term memory** of the vendor from `/memories/`.
3. **Plan changes (10 s).** Open How it thinks on the finished CLM-2207 run: plan v1 vs v2, with the step the agent
   added after a check failed (e.g. "Draft a note to the contractor about the 16,000 sq ft gap").
4. **File system + memory (10 s).** Evidence folder: `plan.md`, one JSON per data call, `findings.md`, `decision.md`.
   Memory tile: the vendor note the agent updated, which the next run reads.
5. **Human in the loop (10 s).** The run stopped at `record_decision` (`interrupt_on`). Review → Approve: the same run
   resumes ("Person approved: agent resumed the same run"). Money never moves without a person; amounts come from
   plain-code tools, and the rules overrule the agent if it contradicts them.
6. **Trace + cost (5 s).** Open LangSmith trace. "All of this runs on free models: Groq's free tier first, and Ollama on
   this laptop when Groq rate-limits. It cost us nothing."

Backup if the network fails: Ollama alone runs the agent offline; if that fails too, the recorded plan replays.

## Solana track (30 seconds)

**Before judging:** Phantom installed, Testnet mode on, Devnet selected; app wallet funded (`/api/solana/status`).
Run DRW-0412 so it waits in Review (Lender view). Keep the Explorer tab ready.

1. "The AI finds the evidence, but it can't move money. Only a person's signature can, and Solana proves what they
   approved." Review → Connect Phantom → Release $461,538, hold $138,462 → sign in Phantom.
2. Open "Recorded on Solana ↗": one transaction paid the builder, moved $138,462 into a 2-of-2 holding account
   (lender + Plumbline) and recorded the evidence fingerprint in a memo.
3. Verify evidence → green. Edit the evidence (demo) → red: "Evidence changed after approval." Undo.
4. "New scan verified: release $138,462" → sign again: the held money moves with both signatures and its own receipt.

If Phantom misbehaves, disconnect it: the same flow runs with the demo lender key.

## Numbers to have ready
- 5,245 properties in the CoStar kit, 99% checkable against all three layers; 15,092 Matterport scans.
- Live evaluation: the agent's decisions match the plain-code rules on the demo claims (`python -m scripts.eval_agent`).
- Free models only: Groq free tier (8,000 tokens/minute per model) with per-call fallback to local Ollama.
