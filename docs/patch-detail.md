# Patch Deployment Notes (Task 4)

## 1) Bug Fix Done (triage-engine)

I fixed validation in triage-engine so empty or whitespace-only symptoms are rejected.

- File: `triage-engine/main.py`
- Fix used:

```python
if not isinstance(symptoms, str) or not symptoms.strip():
```

Impact:
- Request body like `""` or `"   "` now returns `400 MISSING_SYMPTOMS`.
- Prevents invalid triage requests from entering AI flow.

## 2) httpx CVE Simulation (Security Patch)

The vulnerable dependency was `httpx==0.23.0`.

Patched to:
- `triage-engine/requirements.txt` -> `httpx==0.27.2`
- `triage-engine/requirements-dev.txt` -> `httpx==0.27.2`

Validation steps:
1. Rebuild image with new tag.
2. Run unit tests (`pytest test_main.py -v`).
3. Re-run Trivy/CI scanner.
4. Confirm old httpx CVE finding is gone.