from __future__ import annotations

import argparse

from smoke import login, request, wait_ready


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--explanation",
        required=True,
        choices=("AVAILABLE", "UNAVAILABLE_PROVIDER"),
    )
    parser.add_argument("--cache", choices=("hit", "miss"))
    args = parser.parse_args()

    wait_ready()
    status, jobs = request("/api/v1/jobs")
    assert status == 200 and jobs, jobs
    token, _ = login("candidate@jcareer.test")
    status, recommendations = request(
        "/api/v1/candidates/me/recommendations", token=token
    )
    assert status == 200, recommendations
    assert recommendations["recommendation_status"] == "AVAILABLE"
    assert recommendations["explanation_status"] == args.explanation
    assert recommendations["items"]
    if args.cache:
        assert recommendations["cache"] == args.cache, recommendations
    print(
        "J-Career outage probe: PASS "
        f"(explanation={recommendations['explanation_status']}, cache={recommendations['cache']})"
    )


if __name__ == "__main__":
    main()
