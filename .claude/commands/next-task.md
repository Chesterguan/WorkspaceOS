Read the following files for context:
- CLAUDE.md
- agent/STATE.md
- agent/DECISIONS.md
- agent/NEXT_TASK.md

Then:
1. Execute the task described in NEXT_TASK.md with minimal changes
2. Only access files listed in the Scope section
3. Run any tests specified in the Scope section
4. On success:
   - Update agent/STATE.md (status, last completed task, timestamp)
   - Update agent/NEXT_TASK.md with the logical next task
   - Log any significant decisions to agent/DECISIONS.md
5. On failure:
   - Retry once with a different approach
   - If still failing, write to agent/BLOCKERS.md with exact error and stop
6. Output only: changes made + test results + next task summary
