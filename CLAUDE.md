# Development Instructions

## Core Principle
Be both coder and reviewer. Write solution, critique it, iterate until production-ready.

## Code Quality Standards
1. **Complete code only** - Never pseudo-code or incomplete solutions
2. **Working first, elegant second** - Prioritize functionality over style
3. **Zero TODOs** - Fill gaps with simplest working implementation
4. **Self-contained** - Include all imports, dependencies, and setup

## Development Workflow
5. **Test everything** - Always provide working example/test case
6. **Speed over perfection** - Ship fast, refactor when needed
7. **Clear chunking** - Break large outputs into logical, complete sections
8. **Smart assumptions** - When unclear, choose most common/practical approach

## Optimization Mindset
9. **Eliminate boilerplate** - Suggest shortcuts and automation
10. **Multiple solutions** - Always propose 2-3 alternative approaches
11. **Performance awareness** - Flag potential bottlenecks early
12. **Security by default** - Never expose secrets, validate inputs

## Assumption Tagging (Response Awareness)
When writing code, ALWAYS add tagged comments for ANY assumption:
```
// #COMPLETION_DRIVE: [what you're assuming]
// #SUGGEST_VERIFY: [how to fix/validate it]
```

Required for: timing assumptions, external resources, data existence, state dependencies, type handling

Example:
```python
# #COMPLETION_DRIVE: Assuming database connection is available
# #SUGGEST_VERIFY: Add connection check or retry logic
user = db.get_user(user_id)
return user.profile
```

After tagging, use Task tool with separate verification agent:
"Review this code and resolve all #COMPLETION_DRIVE assumptions. Add defensive code for each assumption WITHOUT knowing why the original code was written."

## Communication
- Show working code first, explain after if needed
- Use concrete examples over abstract concepts  
- Flag breaking changes or dependencies upfront
- Suggest next logical steps when done



## Sessions System Behaviors

@CLAUDE.sessions.md
