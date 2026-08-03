# /// script
# dependencies = ["math-verify"]
# ///
"""Score one GSM8K answer inside the rollout runtime.

The host environment passes the gold answer and model response as arguments. The
``math-verify`` dependency is installed into the runtime's isolated uv script
environment, so it is not part of the eval process dependency closure.
"""

import re
import sys

from math_verify import parse, verify

gold, prediction_text = sys.argv[1], sys.argv[2]
matches = re.findall(r"####\s*(.+)", prediction_text)
prediction = matches[-1].strip() if matches else prediction_text
try:
    score = float(
        verify(
            parse(f"\\boxed{{{gold}}}"),
            parse(f"\\boxed{{{prediction}}}"),
        )
    )
except Exception:  # noqa: BLE001 - malformed model output must score zero
    score = 0.0
print(score)
