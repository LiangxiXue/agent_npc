# Final Course Presentation Source Brief

## Confirmed Presentation Profile

- Language: Chinese.
- Output: PPTX only.
- Length: 14 slides for an 8-10 minute course report.
- Audience: course instructor first, classmates second.
- Core message: this is a runnable and traceable LLM character-agent system, not a plain chatbot.
- Content balance: technical architecture about 45%, real demo and trace evidence about 35%, evaluation and future work about 20%.
- Visual style: serious course-report style. Use clean diagrams, tables, trace excerpts, screenshots, and restrained highlights. Avoid large AI-generated tech backgrounds, neon/cyber styling, flashy product-launch visuals, or overly game-like decoration.
- Evidence rule: use only the current repo, course report, screenshots, traces, docs, and Git/GitHub history. Do not invent metrics.
- Git history: include one concise project-evolution evidence page with key commit nodes and branch context.
- Speaker notes: include Chinese speaker notes, about 30-45 seconds per slide.

## Key Evidence Sources

- `course_report_zh.md` / `course_report_zh.pdf`: primary narrative, architecture, evaluation, and trace example.
- `project_README.md` and `docs_README.md`: current project scope, runtime entry points, verification and docs index.
- `player_ui_desktop.png` and `player_ui_mobile.png`: real interface evidence.
- `classroom_showcase_trace.md`: multi-NPC classroom showcase trace.
- `sable_advantage_trace.md`: Sable route case study.
- `git_history_oneline.txt`, `git_branches.txt`, `github_remote_heads.txt`: local and remote Git evidence.

## Proposed Slide Spine

1. Cover: memory-driven verifiable LLM character-agent system.
2. Problem: role chat is not world state.
3. Goal: state + memory + validation + trace.
4. Project evolution: key Git milestones.
5. System architecture: observation to timeline export.
6. Module boundary: observation, memory, mind, decision, validation, state, trace.
7. Memory and retrieval: recent context, lore, long-term memory, background jobs.
8. NPCMind and ActionValidator: flexible language under rule control.
9. Autonomous NPC runtime: event inbox, ActionCatalog, constrained decisions.
10. Traveler runtime: profile-driven automatic exploration.
11. Real interface and trace evidence: UI plus classroom showcase.
12. Sable route case: language behavior versus state mutation.
13. Evaluation and limits: evidence matrix, limitations, next metrics.
14. Closing: controllable LLM characters need traceable execution.
