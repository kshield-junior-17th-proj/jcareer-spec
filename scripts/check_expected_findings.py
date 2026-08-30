#!/usr/bin/env python3
"""EXPECTED_FINDINGS 재현 검증 — V1 P0-05 수정판.

V1 결함:
  - 스캐너 출력이 비어도 SCANNER 5건 전부 통과
  - GAP-CACHE-01 이 리소스 존재만으로 통과
  - GAP 주석이 아무 .md 에만 있어도 인정

V2:
  - SCANNER = plan_assertion AND scanner_assertion 둘 다 충족해야 PASS
  - scanner 결과가 비었거나 rule_id 미검출이면 FAIL (fail-closed)
  - ABSENCE 근거 주석은 .tf 또는 ABSENCE_MANIFEST.md 에서만 인정
"""
import argparse, json, pathlib, re, sys

try:
    import yaml
except ImportError:
    print("::error::pyyaml 필요"); sys.exit(2)


def walk(mod):
    for r in mod.get("resources", []):
        yield r
    for c in mod.get("child_modules", []):
        yield from walk(c)


def load_plan(p):
    plan = json.load(open(p, encoding="utf-8"))
    root = plan.get("planned_values", {}).get("root_module", {})
    return [{"type": r.get("type"), "address": r.get("address"),
             "values": r.get("values") or {}} for r in walk(root)]


class ScannerSchemaError(Exception):
    pass


def _norm_addr(s):
    """리소스 주소 정규화. tfsec 는 module.x 접두, checkov 는 file 경로가 붙기도 한다."""
    s = (s or "").strip()
    if not s:
        return ""
    s = s.split(":")[-1].strip()          # "path/main.tf:aws_x.y" → "aws_x.y"
    if s.startswith("module."):
        parts = s.split(".")
        if len(parts) > 2:
            s = ".".join(parts[2:])
    return s


def load_scanner(paths):
    """tfsec / checkov JSON 을 (tool, rule_id, resource) 집합으로 정규화.

    V2 결함(V2-P0-05B): results 가 dict(checkov) 인데 list 로 순회해 AttributeError.
    V2.1: 스키마를 명시적으로 분기하고, 알 수 없는 형태는 설명 가능한 실패로 올린다.
    """
    hits, loaded, errors = set(), 0, []
    for p in paths:
        f = pathlib.Path(p)
        if not f.is_file() or f.stat().st_size == 0:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{p}: JSON 파싱 실패 ({e})")
            continue
        if not isinstance(data, dict):
            errors.append(f"{p}: 최상위가 object 가 아님 ({type(data).__name__})")
            continue
        res = data.get("results")
        matched = False
        if isinstance(res, list):                                   # tfsec
            matched = True
            for r in res:
                if not isinstance(r, dict):
                    errors.append(f"{p}: tfsec results 원소가 object 가 아님"); break
                rid = r.get("long_id") or r.get("rule_id") or r.get("id")
                if rid:
                    hits.add(("tfsec", str(rid), _norm_addr(r.get("resource"))))
        elif isinstance(res, dict):                                 # checkov
            matched = True
            fc = res.get("failed_checks")
            if fc is None:
                errors.append(f"{p}: checkov results 에 failed_checks 가 없음")
            elif not isinstance(fc, list):
                errors.append(f"{p}: checkov failed_checks 가 배열이 아님")
            else:
                for r in fc:
                    if not isinstance(r, dict):
                        errors.append(f"{p}: checkov failed_checks 원소가 object 가 아님"); break
                    rid = r.get("check_id")
                    if rid:
                        hits.add(("checkov", str(rid), _norm_addr(r.get("resource"))))
        if not matched:
            if isinstance(data.get("failed_checks"), list):         # checkov (평면형)
                for r in data["failed_checks"]:
                    if isinstance(r, dict) and r.get("check_id"):
                        hits.add(("checkov", str(r["check_id"]), _norm_addr(r.get("resource"))))
            else:
                errors.append(f"{p}: 알 수 없는 스캐너 스키마 — results 키가 없거나 형식 불명")
        loaded += 1
    if errors:
        raise ScannerSchemaError("; ".join(errors))
    return hits, loaded


def anchor_in_tf(tfdir, gap_id):
    d = pathlib.Path(tfdir)
    if not d.exists():
        return False
    cands = list(d.rglob("*.tf")) + [p for p in d.rglob("ABSENCE_MANIFEST.md")]
    for f in cands:
        try:
            if gap_id in f.read_text(encoding="utf-8", errors="replace"):
                return True
        except Exception:
            pass
    return False


def nested_all(values, dotted):
    """중첩 경로의 **모든** 값을 반환한다.

    V2 결함(V2-P0-05): 리스트의 첫 원소만 따라가서 WAF 두 번째 규칙을 놓쳤다.
    """
    cur = [values]
    for part in dotted.split("."):
        nxt = []
        for c in cur:
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict) and part in item:
                        nxt.append(item[part])
            elif isinstance(c, dict) and part in c:
                nxt.append(c[part])
        cur = nxt
        if not cur:
            return []
    out = []
    for c in cur:
        if isinstance(c, list):
            out.extend(c)
        else:
            out.append(c)
    return out


def nested(values, dotted):
    v = nested_all(values, dotted)
    return v[0] if v else None


def comparable(value):
    """Provider 스키마의 bool/문자열 bool 표현만 안전하게 정규화한다."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower()
    return str(value)


def check_plan_assertion(pa, res, types_present):
    """반환: (ok, 사유)"""
    if not pa:
        return True, ""
    for t in (pa.get("absent_resource_types") or []):
        if t in types_present:
            return False, f"AS-IS 에 없어야 할 리소스가 선언됨: {t}"
    rt = pa.get("resource_type")
    if pa.get("required_present") and rt and rt not in types_present:
        return False, f"기반 리소스 {rt} 가 plan 에 없음"
    nb = pa.get("absent_nested_block")
    if nb and rt:
        for r in res:
            if r["type"] != rt:
                continue
            hits = [v for v in nested_all(r["values"], nb) if v is not None]
            if hits:
                return False, (f"{nb} 가 {len(hits)}곳에 선언되어 AS-IS 가 아님 "
                               f"({r['address']})")
    eq = pa.get("attribute_equals") or {}
    if eq:
        if rt and rt not in types_present:
            return False, f"{rt} 가 plan 에 없음 — 결함을 심을 대상이 없다"
        if not any(all(comparable(nested(r["values"], k)) == comparable(v)
                       for k, v in eq.items())
                   for r in res if r["type"] == rt):
            return False, f"기대 설정값 {eq} 을 가진 {rt} 가 없음"
    for at in (pa.get("attribute_absent") or []):
        for r in res:
            if r["type"] == rt and nested(r["values"], at):
                return False, f"{at} 가 설정되어 AS-IS 결함이 사라짐"
    comp = pa.get("companion_absent")
    if comp and comp in types_present:
        return False, f"{comp} 가 선언되어 AS-IS 결함이 사라짐"
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--scanner", nargs="*", default=[])
    ap.add_argument("--tfdir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = yaml.safe_load(open(a.spec, encoding="utf-8")) or {}
    findings = spec.get("findings", [])
    res = load_plan(a.plan)
    types_present = {r["type"] for r in res}

    ids = [f.get("id") for f in findings]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        print(f"::error::EXPECTED_FINDINGS 에 중복 id 가 있습니다: {dups}")
        return 1

    try:
        hits, files_loaded = load_scanner(a.scanner)
    except ScannerSchemaError as e:
        print(f"::error::스캐너 결과 스키마 오류 — {e}")
        print("::error::설명 가능한 실패로 종료합니다. traceback 이 아닙니다.")
        return 1

    results, failures = [], []
    for f in findings:
        gid = f.get("id")
        ftype = (f.get("type") or "").upper()
        st, why = "PASS", ""

        if ftype == "DOC":
            st, why = "SKIP", "문서 판정 대상 — CONTROL_ASSESSMENT.yaml"

        elif ftype == "ABSENCE":
            ok, why2 = check_plan_assertion(f.get("plan_assertion"), res, types_present)
            if not ok:
                st, why = "FAIL", why2
            elif not anchor_in_tf(a.tfdir, gid):
                st, why = "FAIL", (f"{gid} 근거 주석이 .tf 또는 ABSENCE_MANIFEST.md 에 없음 "
                                   f"— 의도적 미선언인지 누락인지 구분 불가")

        elif ftype == "SCANNER":
            ok, why2 = check_plan_assertion(f.get("plan_assertion"), res, types_present)
            if not ok:
                st, why = "FAIL", why2
            else:
                sa = f.get("scanner_assertion") or {}
                tool = (sa.get("tool") or "").strip()
                rid = (sa.get("rule_id") or "").strip()
                addr = _norm_addr(sa.get("resource_address"))
                if not rid:
                    st, why = "FAIL", "scanner_assertion.rule_id 미정의 — 명세 자체가 불완전"
                elif not tool:
                    st, why = "FAIL", "scanner_assertion.tool 미정의 (tfsec | checkov)"
                elif tool not in ("tfsec", "checkov"):
                    st, why = "FAIL", f"scanner_assertion.tool 값이 유효하지 않음: {tool}"
                elif not files_loaded:
                    st, why = "FAIL", ("스캐너 결과가 비어 있음 — SCANNER 항목은 "
                                       "실제 검출 없이 통과시키지 않는다")
                else:
                    cand = [h for h in hits if h[0] == tool and h[1] == rid]
                    if not cand:
                        st, why = "FAIL", f"{tool} 결과에 rule_id={rid} 미검출"
                    elif addr:
                        # V2 결함(V2-P0-05A): h[1] in addr 은 빈 문자열이 항상 참이었다.
                        exact = [h for h in cand if h[2] == addr]
                        if not exact:
                            seen_addrs = sorted({h[2] or "(빈 문자열)" for h in cand})
                            st, why = "FAIL", (f"{rid} 는 검출됐으나 리소스 주소가 다름 — "
                                               f"기대 {addr} · 실제 {seen_addrs}")
        else:
            st, why = "FAIL", f"알 수 없는 type: {ftype}"

        results.append({"id": gid, "type": ftype, "title": f.get("title"),
                        "status": st, "detail": why, "source": f.get("source"),
                        "risk": f.get("risk", [])})
        if st == "FAIL":
            failures.append((gid, f.get("title"), why))

    summary = {"layer": a.layer, "scanner_files_loaded": files_loaded,
               "scanner_hits": len(hits), "total": len(results),
               "pass": sum(1 for r in results if r["status"] == "PASS"),
               "fail": len(failures),
               "skip": sum(1 for r in results if r["status"] == "SKIP"),
               "results": results}
    o = pathlib.Path(a.out)
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{a.layer}] 총 {summary['total']} · 통과 {summary['pass']} · "
          f"실패 {summary['fail']} · 문서판정 {summary['skip']} "
          f"(스캐너 파일 {files_loaded}개 · 검출 {len(hits)}건)")
    for gid, title, why in failures:
        print(f"::error::{gid} 재현 실패 — {title} :: {why}")
    if failures:
        print("::error::기대한 GAP 이 재현되지 않았습니다. 코드가 AS-IS 가 아니라는 뜻입니다.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
