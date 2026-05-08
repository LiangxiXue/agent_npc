# Test Plan

## Goal

Verify that the MVP behaves like an Agent system with stateful actions, not a plain chatbot.

## Automated Tests

Run:

```bash
python -m unittest discover -s tests -v
```

Current test file:

```text
tests/test_workflow.py
```

## Covered Behaviors

### Low Trust Refusal

Input:

```text
我想打听一下地下遗迹的入口。
```

Expected:

- intent: `withhold_ruins_entrance`
- no location unlock
- trust remains 20

### Quest Completion

Input:

```text
我把你丢失的钥匙找回来了。
```

Expected:

- intent: `complete_lost_key_quest`
- trust becomes 30
- affection becomes 38
- quest status becomes `completed`
- player receives `tavern_discount_coupon`
- tool calls include memory and state-changing tools

### Memory/State-Based Unlock

Inputs:

```text
我把你丢失的钥匙找回来了。
上次我帮你找回钥匙了，现在能告诉我遗迹入口吗？
```

Expected:

- second intent: `reveal_ruins_entrance`
- unlocked locations include `underground_ruins_entrance`
- interaction logs are persisted

### Trace Logging

Expected:

- interaction log stores decision;
- interaction log stores tool calls;
- interaction log stores state changes.
- interaction log stores workflow steps.

### Chinese Memory Retrieval

Expected:

- after returning Lina's key, a later Chinese input mentioning `钥匙` and `入口` retrieves the `lost_key` memory;
- the retrieved memory then helps the decision layer choose `reveal_ruins_entrance`.

## Manual UI Test

Run:

```bash
streamlit run app.py
```

Then perform the same three inputs in the UI and verify:

- current NPC state panel changes;
- retrieved memories are visible;
- tool calls are visible;
- state changes are visible;
- interaction log expands correctly.
