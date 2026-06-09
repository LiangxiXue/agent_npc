d727b0f Initial memory-driven NPC agent snapshot
9ed495f Add layered context and lore retrieval architecture
261094c Add player UI and harden quest workflow
ec7d32e Speed up NPC turns with background memory jobs
2d64bc2 Update docs for current agent architecture
0e3af6a Set project Python version
bbf7990 Harden LLM retries and simplify preview retrieval
b2fef82 Show NPC response timing breakdown
91c4789 Refine NPC casual dialogue guidance
5da83ac Refactor long-term memory pipeline
0c5fe51 Clarify LLM provider priority in README
57c98e6 Refactor workflow around narrative environment
856c804 Add NPC character mind layer
1906835 Document autonomous NPC tick research
14dbb03 Merge autonomous NPC tick research
e895667 feat: add autonomous runtime storage schema
1160b2c feat: dispatch world events to npc inbox
c3f2b6a feat: add npc action catalog
bf5cd92 feat: add llm constrained autonomous tick
5c7821c feat: add autonomous mailbox plan and trace apis
4c10fd9 docs: add autonomous npc demo scripts
6acf69b feat: add living world ruins demo
ad178e2 (origin/codex/living-world-demo) feat: add traveler living world runtime
38f0803 feat: record living world timing breakdowns
67db4bd fix: preserve traveler event payloads in living world traces
9050127 feat: accumulate living world arc progress
c012cb9 fix: avoid reapplying resolved arc outcome
42e6a96 feat: add traveler exploration planning context
523553f fix: include traveler id in exploration context
d7a9564 feat: route traveler exploration through leads
7808105 fix: hand off exploration leads to local NPCs
d534083 fix: fallback invalid autonomous npc decisions
d24f8d1 test: require allowed autonomous fallback actions
6825ed3 fix: map mira autonomous actions to safe intents
ceeb435 feat: add optional idle npc scheduling probes
7c39617 fix: keep idle npc probes from driving arc chaos
556ed1a feat: explain exploration routing in timeline export
22d570d test: assert npc validation reason in timeline export
2e6f269 feat: add living world acceptance demo controls
169282c fix: keep traveler mock demo fully offline
bb750fd (codex/living-world-demo) docs: update readme for living world runtime
e19512e (origin/main, origin/HEAD, main) docs: clarify LLM agent README framing
d4142ee (HEAD -> codex/traveler-dialogue-trace, origin/codex/traveler-dialogue-trace) Add traveler classroom traces and Sable route demo
