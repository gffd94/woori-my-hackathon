---
name: tdd-skill
description: Follow a specification-driven test-first workflow for small coding tasks, especially when requirements include concrete examples and a project defines its own test command.
---

# TDD Skill

Use this skill when implementing a small feature from an existing specification and tests are part of the requested workflow.

## Workflow

1. Read the applicable project instructions and specification. Identify the requested scope, target files, test command, and files the user asked to leave unchanged.
2. Treat the specification as the source of expected behavior. Do not add behavior that it does not describe. If requirements are materially ambiguous, ask before encoding an assumption.
3. When asked to derive tests from examples, write one test per example row. Use the project's requested test framework, assertion library, module-loading style, and language for test names.
4. Run the requested test command after writing tests. Report failures accurately. If implementation is explicitly deferred, do not create it; a missing-module failure is an expected consequence and must be reported as such.
5. Implement only the requested production file, keeping the solution as small as the specification permits. Do not modify the specification or user-authored tests unless explicitly asked.
6. Run the requested test command again after implementation. Report the command and the actual pass/fail counts; never describe unrun checks as passing.

## Scope and project rules

Follow local instructions for file locations, approval requirements, technology choices, and exceptions to the normal workflow. A project may define an exercise area where production edits or spec changes are allowed; respect that boundary and do not carry its exception into unrelated folders.

Before writing, confirm the target path is inside an authorized writable workspace. If the filesystem rejects a write, report the exact path and restriction; do not silently write to a different location and claim the requested path was updated.

## Completion report

Summarize files changed, the test command and its result, and any requested files left untouched. Clearly state blockers or unverified items.