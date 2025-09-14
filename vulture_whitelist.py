"""
Optional whitelist for Vulture.

How to use:
  1) Install Vulture: `uv pip install vulture` or `pip install vulture`
  2) First pass (suggestions):
       vulture src --min-confidence 90 --make-whitelist > vulture_whitelist.py
  3) Review/trim the generated stubs; keep only true dynamic usages.
  4) Re-run scan with this file included:
       extra-utils/run-vulture.sh

Notes:
- Keep this file minimal. Only include objects that are referenced dynamically
  (e.g., via getattr, CLI entry points discovered by name, plugin hooks).
- Everything else should be removed from this file so that Vulture can flag it.
"""

# Placeholder: intentionally empty until you generate from a first pass.

