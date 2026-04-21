# Semgrep test fixture for no-exception-in-except-tuple rule.
# Run: semgrep --test --config semgrep-rules/ semgrep-rules/

# POSITIVE: trailing Exception, no alias

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, Exception):
    pass

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, TypeError, Exception):
    pass

# POSITIVE: trailing Exception, with alias (Group G regression form)

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, Exception) as exc:
    pass

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, TypeError, Exception) as exc:
    pass

# POSITIVE: leading Exception, no alias

# ruleid: no-exception-in-except-tuple
try:
    pass
except (Exception, ValueError):
    pass

# POSITIVE: leading Exception, with alias

# ruleid: no-exception-in-except-tuple
try:
    pass
except (Exception, ValueError) as exc:
    pass

# POSITIVE: middle Exception, no alias

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, Exception, TypeError):
    pass

# POSITIVE: middle Exception, with alias

# ruleid: no-exception-in-except-tuple
try:
    pass
except (ValueError, Exception, TypeError) as exc:
    pass

# NEGATIVE: bare single-exception clauses

# ok: no-exception-in-except-tuple
try:
    pass
except ValueError as exc:
    pass

# ok: no-exception-in-except-tuple
try:
    pass
except Exception as exc:
    pass

# ok: no-exception-in-except-tuple
try:
    pass
except Exception:
    pass
