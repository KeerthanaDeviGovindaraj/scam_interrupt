# For Gayatri: show the agent's case notes in the demo (optional, 10 minutes)

The deepagents planner writes a readable case file for every risky transfer at
`data/agent_fs/cases/<transfer_id>/notes.md`. Showing it next to the LangSmith trace is the
LangChain demo moment.

1. Add this endpoint to `backend/app.py` (near the other `/api/cases` routes):

```python
@app.get("/api/cases/{transfer_id}/notes")
def case_notes(transfer_id: int):
    from . import agent
    return {"transfer_id": transfer_id, "notes": agent.read_notes(transfer_id)}
```

2. On the dashboard, add a "Case notes" link per transfer that opens
   `/api/cases/<id>/notes`, or render `notes` in a `<pre>` box.
