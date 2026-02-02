# Cursor Skills – Calibration Tracker Project
# Purpose: Teach the AI *how* to think and act when working in this codebase
# These are executable competencies, not buzzwords

############################################
## CORE PYTHON ENGINEERING
############################################
Skill: python_application_engineering
- Write clean, idiomatic Python 3.11+
- Use type hints everywhere
- Prefer small, composable functions
- Avoid global state
- Refactor safely and incrementally

############################################
## DESKTOP APP DEVELOPMENT
############################################
Skill: desktop_gui_development
- Build responsive Windows-first desktop apps
- Use Tkinter, PySide6, or PyQt appropriately
- Keep UI logic thin
- Use threading or async for long operations
- Prevent UI freezes at all costs

############################################
## CALIBRATION & MEASUREMENT LOGIC
############################################
Skill: calibration_workflows
- Model real-world calibration lifecycles
- Enforce immutability of finalized records
- Support revisioning and superseded entries
- Preserve historical accuracy
- Respect tolerances, units, and traceability

############################################
## DATA MODELING & DOMAIN DESIGN
############################################
Skill: domain_modeling
- Use dataclasses or Pydantic models
- No raw dicts across module boundaries
- Validate invariants at model boundaries
- Prefer explicit fields over flexible blobs

############################################
## DATA PERSISTENCE
############################################
Skill: local_persistence_engineering
- Design safe SQLite schemas
- Write and review migrations
- Centralize read/write logic
- Prevent silent corruption
- Support import/export safely

############################################
## VALIDATION & DEFENSIVE PROGRAMMING
############################################
Skill: defensive_validation
- Validate user input aggressively
- Fail loudly and clearly
- Never silently coerce types
- Handle edge cases explicitly
- Reject invalid states early

############################################
## FILESYSTEM & PATH SAFETY
############################################
Skill: filesystem_safety
- Use pathlib exclusively
- Handle spaces, permissions, and locks
- Confirm destructive operations
- Never hardcode absolute paths
- Assume the filesystem will betray you

############################################
## LOGGING & AUDIT TRAILS
############################################
Skill: audit_logging
- Use Python logging module
- Produce human-readable logs
- Record before/after values
- Timestamp all critical actions
- Support traceability and review

############################################
## TESTING & QUALITY
############################################
Skill: test_engineering
- Write unit-testable logic
- Prefer pytest
- Avoid reliance on real system time
- Inject dependencies for determinism
- Test failure cases, not just success

############################################
## REFACTORING & TECH DEBT CONTROL
############################################
Skill: maintainability_guarding
- Identify growing complexity early
- Reduce function and class size
- Eliminate TODO accumulation
- Prefer clarity over cleverness
- Protect future maintainers

############################################
## PERFORMANCE AWARENESS
############################################
Skill: pragmatic_performance
- Optimize startup time
- Avoid premature optimization
- Measure before tuning
- Keep performance predictable

############################################
## DOCUMENTATION & COMMUNICATION
############################################
Skill: technical_documentation
- Write clear docstrings
- Comment non-obvious logic
- Document configuration options
- Explain tradeoffs briefly

############################################
## AI BEHAVIORAL CONSTRAINTS
############################################
Skill: disciplined_ai_behavior
- Do not invent APIs or schemas
- Do not introduce frameworks casually
- Ask whether changes age well
- Preserve existing behavior by default

End of skills.