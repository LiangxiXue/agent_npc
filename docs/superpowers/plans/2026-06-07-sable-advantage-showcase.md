# Sable Advantage Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a real-LLM Traveler trace that reaches `sable_advantage` through a subtle ambitious-patron profile, with enough rounds and dialogue for classroom demonstration.

**Architecture:** Keep the existing arc runtime authoritative. Add a Traveler YAML profile that naturally overweights Sable-route actions without presenting as an obvious merchant, verify the profile loads, then run and inspect exported JSON until the final outcome is `sable_advantage`.

**Tech Stack:** Python, pytest, YAML Traveler profiles, existing `scripts/run_traveler_world_demo.py`, JSON/Markdown timeline export.

---

### Task 1: Add Subtle Sable-Leaning Profile

**Files:**
- Modify: `tests/test_traveler_profile.py`
- Create: `data/travelers/ambitious_patron_scholar.yaml`

- [ ] **Step 1: Write the failing profile-loader test**

Add a test asserting that `ambitious_patron_scholar` loads, is not framed as a merchant, starts near Sable, and has prestige/curiosity-driven private goals.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_profile.py::TravelerProfileLoaderTest::test_loads_ambitious_patron_scholar_profile -q`

Expected: `FileNotFoundError` while the YAML file does not exist.

- [ ] **Step 3: Add the YAML profile**

Create a profile for an ambitious independent patron-scholar whose public story is research sponsorship, while private goals favor exclusivity, informal channels, and Sable's network.

- [ ] **Step 4: Run profile tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_traveler_profile.py -q`

Expected: all profile loader tests pass.

### Task 2: Run and Verify Sable Outcome

**Files:**
- Create: `data/traces/sable_advantage_llm_run/*.json`
- Create: `data/traces/sable_advantage_llm_run/*.md`

- [ ] **Step 1: Run real LLM trace**

Run: `.\.venv\Scripts\python.exe scripts\run_traveler_world_demo.py --profile ambitious_patron_scholar --rounds 20 --max-npc-ticks 0 --export-dir data\traces\sable_advantage_llm_run`

Expected: exported JSON and Markdown, Traveler mode `llm`.

- [ ] **Step 2: Inspect JSON acceptance**

Check `total_rounds`, `final_arc_outcome`, per-round `mode`, dialogue coverage, and cumulative arc scores. Required final outcome is `sable_advantage`.

- [ ] **Step 3: Iterate if needed**

If the outcome is `guardian_advantage`, increase Sable-route profile pressure. If the outcome is `chaotic_lockdown`, reduce conflict/deception language and avoid chaos-triggering actions. Re-run until accepted.
