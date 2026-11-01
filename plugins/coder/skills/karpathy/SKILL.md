---
name: karpathy
description: 日常编码纪律。写新代码、改代码、重构、补测试、常规 code review 时，必须先加载本 skill：约束最小实现、只改必要的行、暴露假设、给出可验证的成功标准。架构选型、API 与兼容性契约、高风险评审不适用，改用 linus-torvalds。
---

# Karpathy Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 分工与同时加载

- 本 skill 负责日常实现纪律；架构选型、API 与兼容性契约、高风险评审由 `linus-torvalds` 裁决。
- 两个 skill 同时命中时：`linus-torvalds` 出技术裁决与审查结论，本 skill 负责落地时的改动纪律。
- 结论冲突时以 `linus-torvalds` 的裁决为准；实现范围仍按本 skill 的"只改必要行"执行。

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- Business semantics the request doesn't pin down — rounding, ordering, idempotency, timeout, retry — are interpretation choices: surface them first.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code — unless the abstraction names an invariant or a trust boundary that would otherwise stay implicit.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for scenarios that cannot occur by construction (type system, or validated earlier in the same function).
- These are NOT impossible and need explicit failure paths: external input, file/network I/O, deserialization, concurrency, third-party APIs.
- If you write 200 lines and it could be 50 without losing observable behavior, invariants, or real error paths, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
