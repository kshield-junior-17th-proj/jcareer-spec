from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx


OPENDART_BASE_URL = "https://opendart.fss.or.kr"
OPENDART_COMPANY_GUIDE_URL = (
    "https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019002"
)
OPENDART_DISCLOSURE_GUIDE_URL = (
    "https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001"
)
SNAPSHOT_SCHEMA_VERSION = "jcareer-opendart-company-snapshot-v1"
MAX_RESPONSE_BYTES = 1_000_000
MAX_DISCLOSURES = 5
CORP_CODE_PATTERN = re.compile(r"^[0-9]{8}$")
RECEIPT_NUMBER_PATTERN = re.compile(r"^[0-9]{14}$")
DATE_PATTERN = re.compile(r"^[0-9]{8}$")


class OpenDartError(RuntimeError):
    """A stable internal error that never carries an upstream URL or API key."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _clean_text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:maximum]


def _date_or_empty(value: Any) -> str:
    text = _clean_text(value, maximum=8)
    return text if DATE_PATTERN.fullmatch(text) else ""


def _market_label(corp_class: str) -> str:
    return {
        "Y": "KOSPI",
        "K": "KOSDAQ",
        "N": "KONEX",
        "E": "기타법인",
    }.get(corp_class, "확인 필요")


def company_names_match(local_name: str, dart_name: str) -> bool:
    """Conservative name comparison used only as a mis-link guard."""

    def normalise(value: str) -> str:
        value = value.casefold()
        value = re.sub(r"(?:주식회사|\(주\)|㈜)", "", value)
        return re.sub(r"[^0-9a-z가-힣]", "", value)

    left = normalise(local_name)
    right = normalise(dart_name)
    return bool(left and right and left == right)


def public_snapshot(snapshot: object) -> dict[str, object] | None:
    """Return the exact public projection even if stored JSON was tampered with."""

    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return None
    company = snapshot.get("company")
    disclosures = snapshot.get("disclosures")
    if not isinstance(company, dict) or not isinstance(disclosures, dict):
        return None
    corp_class = _clean_text(company.get("market_class"), maximum=1)
    projected_company = {
        "legal_name": _clean_text(company.get("legal_name"), maximum=120),
        "english_name": _clean_text(company.get("english_name"), maximum=160),
        "market_class": corp_class,
        "market_label": _market_label(corp_class),
        "stock_name": _clean_text(company.get("stock_name"), maximum=120),
        "stock_code": _clean_text(company.get("stock_code"), maximum=6),
        "industry_code": _clean_text(company.get("industry_code"), maximum=20),
        "established_on": _date_or_empty(company.get("established_on")),
        "fiscal_month": _clean_text(company.get("fiscal_month"), maximum=2),
    }
    if not projected_company["legal_name"]:
        return None
    rows = disclosures.get("items")
    projected_rows: list[dict[str, object]] = []
    if isinstance(rows, list):
        for row in rows[:MAX_DISCLOSURES]:
            if not isinstance(row, dict):
                continue
            projected_rows.append(
                {
                    "receipt_ref": _clean_text(row.get("receipt_ref"), maximum=40),
                    "report_name": _clean_text(row.get("report_name"), maximum=240),
                    "submitted_on": _date_or_empty(row.get("submitted_on")),
                    "market_class": _clean_text(
                        row.get("market_class"), maximum=1
                    ),
                    "remarks": _clean_text(row.get("remarks"), maximum=120),
                }
            )
    source_kind = snapshot.get("source_kind")
    if source_kind not in {"synthetic_fixture", "live_open_api"}:
        source_kind = "unknown"
    disclosure_state = disclosures.get("state")
    if disclosure_state not in {"AVAILABLE", "NO_DATA", "UNAVAILABLE"}:
        disclosure_state = "UNAVAILABLE"
    error_category = disclosures.get("error_category")
    if error_category not in {
        None,
        "CONFIGURATION",
        "NO_DATA",
        "RATE_LIMITED",
        "UPSTREAM_REJECTED",
        "UPSTREAM_UNAVAILABLE",
        "INVALID_RESPONSE",
    }:
        error_category = "UPSTREAM_UNAVAILABLE"
    content_hash = _clean_text(snapshot.get("content_sha256"), maximum=64)
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        content_hash = ""
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "provider": "OpenDART",
        "source_kind": source_kind,
        "synthetic": snapshot.get("synthetic") is True,
        "retrieved_at": _clean_text(snapshot.get("retrieved_at"), maximum=40),
        "company": projected_company,
        "disclosures": {
            "state": disclosure_state,
            "items": projected_rows,
            "error_category": error_category,
        },
        "financials": {
            "state": "NOT_REQUESTED_V1",
            "items": [],
            "note": "재무 수치의 기간·연결 기준 설계 전에는 자동 요약하지 않습니다",
        },
        "score_effect": "NONE",
        "source_guides": {
            "company": OPENDART_COMPANY_GUIDE_URL,
            "disclosures": OPENDART_DISCLOSURE_GUIDE_URL,
        },
        "content_sha256": content_hash,
    }


SYNTHETIC_FIXTURES: dict[str, dict[str, object]] = {
    "90000001": {
        "company": {
            "legal_name": "아크웨이브",
            "english_name": "ARCWAVE SYNTHETIC LAB",
            "market_class": "E",
            "stock_name": "",
            "stock_code": "",
            "industry_code": "62010",
            "established_on": "20180412",
            "fiscal_month": "12",
        },
        "disclosures": [
            {
                "receipt_ref": "SYN-DART-ARC-001",
                "report_name": "[합성] 사업보고서",
                "submitted_on": "20260331",
                "market_class": "E",
                "remarks": "합성 예시",
            },
            {
                "receipt_ref": "SYN-DART-ARC-002",
                "report_name": "[합성] 주요사항보고서(신규 서비스 투자)",
                "submitted_on": "20260718",
                "market_class": "E",
                "remarks": "합성 예시",
            },
        ],
    },
    "90000002": {
        "company": {
            "legal_name": "모자이크웍스",
            "english_name": "MOSAIC WORKS SYNTHETIC LAB",
            "market_class": "E",
            "stock_name": "",
            "stock_code": "",
            "industry_code": "63111",
            "established_on": "20200220",
            "fiscal_month": "12",
        },
        "disclosures": [
            {
                "receipt_ref": "SYN-DART-MOS-001",
                "report_name": "[합성] 사업보고서",
                "submitted_on": "20260401",
                "market_class": "E",
                "remarks": "합성 예시",
            }
        ],
    },
    "90000003": {
        "company": {
            "legal_name": "포지데이터",
            "english_name": "FORGE DATA SYNTHETIC LAB",
            "market_class": "E",
            "stock_name": "",
            "stock_code": "",
            "industry_code": "58222",
            "established_on": "20161108",
            "fiscal_month": "12",
        },
        "disclosures": [],
    },
}


class OpenDartClient:
    """Fetch and project OpenDART into a bounded recruiting-profile snapshot.

    The live path is opt-in. The default fixture path never performs network I/O
    and only exposes clearly marked synthetic data.
    """

    def __init__(
        self,
        *,
        mode: str = "fixture",
        api_key: str = "",
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if mode not in {"disabled", "fixture", "live"}:
            raise OpenDartError("CONFIGURATION", "OpenDART 실행 모드를 확인해 주세요")
        self.mode = mode
        self._api_key = api_key
        self._timeout_seconds = min(max(timeout_seconds, 0.5), 15.0)
        self._transport = transport
        self._clock = clock

    @classmethod
    def from_environment(cls) -> "OpenDartClient":
        timeout_text = os.getenv("OPENDART_TIMEOUT_SECONDS", "5")
        try:
            timeout_seconds = float(timeout_text)
        except ValueError:
            timeout_seconds = 5.0
        return cls(
            mode=os.getenv("OPENDART_MODE", "fixture").strip().lower(),
            api_key=os.getenv("OPENDART_API_KEY", ""),
            timeout_seconds=timeout_seconds,
        )

    def refresh_company(self, corp_code: str) -> dict[str, object]:
        corp_code = corp_code.strip()
        if not CORP_CODE_PATTERN.fullmatch(corp_code):
            raise OpenDartError("INVALID_CORP_CODE", "OpenDART 고유번호는 숫자 8자리여야 합니다")
        if self.mode == "disabled":
            raise OpenDartError("DISABLED", "OpenDART 연동이 현재 비활성화되어 있습니다")
        observed_at = self._clock().astimezone(timezone.utc)
        if self.mode == "fixture":
            return self._fixture_snapshot(corp_code, observed_at)
        return self._live_snapshot(corp_code, observed_at)

    def _fixture_snapshot(
        self, corp_code: str, observed_at: datetime
    ) -> dict[str, object]:
        fixture = SYNTHETIC_FIXTURES.get(corp_code)
        if not fixture:
            raise OpenDartError(
                "NO_DATA",
                "합성 OpenDART 예시에서 해당 고유번호를 찾을 수 없습니다",
            )
        disclosures = list(fixture["disclosures"])
        return self._snapshot(
            corp_code=corp_code,
            company=dict(fixture["company"]),
            disclosures={
                "state": "AVAILABLE" if disclosures else "NO_DATA",
                "items": disclosures,
                "error_category": None,
            },
            observed_at=observed_at,
            source_kind="synthetic_fixture",
            synthetic=True,
        )

    def _live_snapshot(
        self, corp_code: str, observed_at: datetime
    ) -> dict[str, object]:
        if len(self._api_key) != 40:
            raise OpenDartError(
                "CONFIGURATION", "OpenDART 인증키 설정을 확인해 주세요"
            )
        company_payload = self._request_json(
            "/api/company.json", {"corp_code": corp_code}
        )
        company = self._project_company(company_payload)

        start_date = (observed_at.date() - timedelta(days=365)).strftime("%Y%m%d")
        end_date = observed_at.date().strftime("%Y%m%d")
        try:
            disclosure_payload = self._request_json(
                "/api/list.json",
                {
                    "corp_code": corp_code,
                    "bgn_de": start_date,
                    "end_de": end_date,
                    "page_no": "1",
                    "page_count": str(MAX_DISCLOSURES),
                    "sort": "date",
                    "sort_mth": "desc",
                },
                no_data_allowed=True,
            )
            if disclosure_payload is None:
                disclosures = {
                    "state": "NO_DATA",
                    "items": [],
                    "error_category": None,
                }
            else:
                disclosures = {
                    "state": "AVAILABLE",
                    "items": self._project_disclosures(disclosure_payload),
                    "error_category": None,
                }
        except OpenDartError as error:
            disclosures = {
                "state": "UNAVAILABLE",
                "items": [],
                "error_category": error.category,
            }

        return self._snapshot(
            corp_code=corp_code,
            company=company,
            disclosures=disclosures,
            observed_at=observed_at,
            source_kind="live_open_api",
            synthetic=False,
        )

    def _request_json(
        self,
        path: str,
        params: dict[str, str],
        *,
        no_data_allowed: bool = False,
    ) -> dict[str, object] | None:
        query = {"crtfc_key": self._api_key, **params}
        try:
            with httpx.Client(
                base_url=OPENDART_BASE_URL,
                timeout=self._timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.get(path, params=query)
            if response.status_code != 200:
                raise OpenDartError(
                    "UPSTREAM_UNAVAILABLE", "OpenDART 응답을 확인할 수 없습니다"
                )
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise OpenDartError(
                    "INVALID_RESPONSE", "OpenDART 응답 크기가 허용 범위를 벗어났습니다"
                )
            payload = response.json()
        except OpenDartError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError):
            raise OpenDartError(
                "UPSTREAM_UNAVAILABLE", "OpenDART 응답을 확인할 수 없습니다"
            ) from None
        if not isinstance(payload, dict):
            raise OpenDartError(
                "INVALID_RESPONSE", "OpenDART 응답 형식을 확인할 수 없습니다"
            )
        status = payload.get("status")
        if status == "000":
            return payload
        if status == "013" and no_data_allowed:
            return None
        category = {
            "010": "CONFIGURATION",
            "011": "CONFIGURATION",
            "012": "CONFIGURATION",
            "013": "NO_DATA",
            "014": "UPSTREAM_UNAVAILABLE",
            "020": "RATE_LIMITED",
            "021": "UPSTREAM_REJECTED",
            "100": "UPSTREAM_REJECTED",
            "101": "UPSTREAM_REJECTED",
            "800": "UPSTREAM_UNAVAILABLE",
            "900": "UPSTREAM_UNAVAILABLE",
            "901": "CONFIGURATION",
        }.get(str(status), "UPSTREAM_UNAVAILABLE")
        message = {
            "CONFIGURATION": "OpenDART 연동 설정을 확인해 주세요",
            "NO_DATA": "OpenDART에서 해당 기업 정보를 찾을 수 없습니다",
            "RATE_LIMITED": "OpenDART 요청 한도에 도달했습니다",
            "UPSTREAM_REJECTED": "OpenDART 요청 조건을 확인해 주세요",
            "UPSTREAM_UNAVAILABLE": "OpenDART 응답을 확인할 수 없습니다",
        }[category]
        raise OpenDartError(category, message)

    @staticmethod
    def _project_company(payload: dict[str, object]) -> dict[str, object]:
        corp_class = _clean_text(payload.get("corp_cls"), maximum=1)
        legal_name = _clean_text(payload.get("corp_name"), maximum=120)
        if not legal_name or corp_class not in {"Y", "K", "N", "E"}:
            raise OpenDartError(
                "INVALID_RESPONSE", "OpenDART 기업개황 형식을 확인할 수 없습니다"
            )
        stock_code = _clean_text(payload.get("stock_code"), maximum=6)
        if stock_code and not re.fullmatch(r"[0-9]{6}", stock_code):
            stock_code = ""
        fiscal_month = _clean_text(payload.get("acc_mt"), maximum=2)
        if fiscal_month and not re.fullmatch(r"(?:0[1-9]|1[0-2])", fiscal_month):
            fiscal_month = ""
        return {
            "legal_name": legal_name,
            "english_name": _clean_text(payload.get("corp_name_eng"), maximum=160),
            "market_class": corp_class,
            "market_label": _market_label(corp_class),
            "stock_name": _clean_text(payload.get("stock_name"), maximum=120),
            "stock_code": stock_code,
            "industry_code": _clean_text(payload.get("induty_code"), maximum=20),
            "established_on": _date_or_empty(payload.get("est_dt")),
            "fiscal_month": fiscal_month,
        }

    @staticmethod
    def _project_disclosures(payload: dict[str, object]) -> list[dict[str, object]]:
        rows = payload.get("list")
        if not isinstance(rows, list):
            raise OpenDartError(
                "INVALID_RESPONSE", "OpenDART 공시목록 형식을 확인할 수 없습니다"
            )
        projected: list[dict[str, object]] = []
        for row in rows[:MAX_DISCLOSURES]:
            if not isinstance(row, dict):
                continue
            receipt_number = _clean_text(row.get("rcept_no"), maximum=14)
            report_name = _clean_text(row.get("report_nm"), maximum=240)
            submitted_on = _date_or_empty(row.get("rcept_dt"))
            if not (
                RECEIPT_NUMBER_PATTERN.fullmatch(receipt_number)
                and report_name
                and submitted_on
            ):
                continue
            projected.append(
                {
                    "receipt_ref": receipt_number,
                    "report_name": report_name,
                    "submitted_on": submitted_on,
                    "market_class": _clean_text(row.get("corp_cls"), maximum=1),
                    "remarks": _clean_text(row.get("rm"), maximum=120),
                }
            )
        return projected

    @staticmethod
    def _snapshot(
        *,
        corp_code: str,
        company: dict[str, object],
        disclosures: dict[str, object],
        observed_at: datetime,
        source_kind: str,
        synthetic: bool,
    ) -> dict[str, object]:
        corp_class = str(company.get("market_class", ""))
        company = {**company, "market_label": _market_label(corp_class)}
        snapshot: dict[str, object] = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "provider": "OpenDART",
            "source_kind": source_kind,
            "synthetic": synthetic,
            "corp_code": corp_code,
            "retrieved_at": observed_at.isoformat(),
            "company": company,
            "disclosures": disclosures,
            "financials": {
                "state": "NOT_REQUESTED_V1",
                "items": [],
                "note": "재무 수치의 기간·연결 기준 설계 전에는 자동 요약하지 않습니다",
            },
            "score_effect": "NONE",
            "source_guides": {
                "company": OPENDART_COMPANY_GUIDE_URL,
                "disclosures": OPENDART_DISCLOSURE_GUIDE_URL,
            },
        }
        snapshot["content_sha256"] = _canonical_hash(snapshot)
        return snapshot
