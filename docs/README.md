# Docs Index

文档按用途分组。当前实现以四 NPC、多任务、Hybrid RAG、后台记忆 worker、LLM 友好长期记忆类型和玩家端像素 UI 为基准。

## design

- `architecture.md`：当前系统架构、同步玩家回合和后台记忆任务分层。
- `memory_mechanism.md`：短期记忆、长期记忆、lore、Memory Policy、后台 memory jobs 和 RAG 检索机制。
- `hybrid_rag_design.md`：Hybrid RAG 当前设计摘要。
- `hybrid_rag_migration_plan.md`：从 typed retrieval 到 Hybrid RAG 的阶段记录；现在主要作为历史迁移记录。
- `retrieval_layer.md`：可插拔 embedding provider、embedding cache、SQLite/FAISS backend 和 fallback 行为。
- `llm_integration.md`：OpenAI-compatible LLM 接入方式、decision/response/memory 路径和失败回退策略。
- `multi_npc.md`：Lina/Ron/Mira/Sable 四 NPC、任务隔离、社交策略和当前行为范围。

## operations

- `run_commands.md`：常用启动、worker、测试、构建和维护命令速查。

## evaluation

- `test_plan.md`：测试范围、命令、当前测试数量和评测口径。

## delivery

- `demo_script.md`：课堂演示流程，包含 Streamlit 调试台、React 玩家端和四 NPC 命令行演示。
- `report_outline.md`：课程报告提纲，按当前实现更新。
- `ai_usage_statement.md`：AI 使用说明草稿。

## reference

- `project_proposal.md`：原项目选题计划。它是需求和范围参考，不代表当前实现逐字状态；当前状态以根目录 `README.md` 和 `docs/design/` 为准。
