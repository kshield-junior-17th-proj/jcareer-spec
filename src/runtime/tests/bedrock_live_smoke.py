from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    if os.getenv("ALLOW_BEDROCK_LIVE", "false").lower() != "true":
        raise SystemExit("Bedrock live smoke is locked; set ALLOW_BEDROCK_LIVE=true explicitly")
    if os.getenv("CONFIRM_SYNTHETIC_BEDROCK_CALL") != "JCAREER_SYNTHETIC_ONLY":
        raise SystemExit(
            "Bedrock live smoke requires CONFIRM_SYNTHETIC_BEDROCK_CALL=JCAREER_SYNTHETIC_ONLY"
        )
    aws = shutil.which("aws")
    if not aws:
        raise SystemExit("AWS CLI is not installed")

    request_path = Path(__file__).with_name("bedrock_live_smoke.json")
    completed = subprocess.run(
        [
            aws,
            "bedrock-runtime",
            "converse",
            "--region",
            "ap-northeast-2",
            "--cli-input-json",
            f"file://{request_path.as_posix()}",
            "--output",
            "json",
            "--no-cli-pager",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise SystemExit("Bedrock Converse call failed; inspect AWS access without printing credentials")

    decoded = None
    for encoding in ("utf-8", locale.getpreferredencoding(False), "cp949"):
        try:
            decoded = completed.stdout.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise SystemExit("Bedrock response encoding could not be decoded safely")
    body = json.loads(decoded)
    response_text = body["output"]["message"]["content"][0]["text"]
    usage = body["usage"]
    if not response_text:
        raise AssertionError("Bedrock response text is empty")

    print("J-Career Bedrock live smoke: PASS")
    print("model=APAC Nova Lite")
    print(f"input_tokens={usage['inputTokens']}, output_tokens={usage['outputTokens']}")
    print(f"response={response_text}")


if __name__ == "__main__":
    main()
