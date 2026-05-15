# Data Artifacts

`data/` 只保留可复查的演示、历史和评测输出。SQLite 数据库是运行时生成物，已由 `.gitignore` 排除。

## Current trace

- `agent_trace_export.json`：当前统一导出的演示 trace，可由 Web UI 或 `python scripts/export_trace.py` 刷新。

## eval

- `memory_eval_report.json`：`python scripts/run_memory_eval.py` 生成的完整评测报告。
- `memory_eval_summary.md`：评测摘要，适合报告和展示引用。
- `memory_eval_state.db`：评测临时数据库，不需要保留，运行脚本时会自动重建。

## history

- 保存旧版本 trace 和复现模板，作为迭代证据；不参与当前 demo 主链路。
