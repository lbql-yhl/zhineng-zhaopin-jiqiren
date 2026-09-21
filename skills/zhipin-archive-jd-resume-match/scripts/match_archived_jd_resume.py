#!/usr/bin/env python3
"""Match a stored BOSS/Zhipin JD and resume using SQLite-only inputs."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "zhipin-boss-recruitment-bot" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from sqlite_store import (  # noqa: E402
    DEFAULT_DB,
    MATCHER_VERSION,
    analysis_cache_key,
    connect,
    get_analysis_cache,
    get_jd_hard_gates,
    get_latest_jd,
    get_resume,
    insert_match_record,
    mark_processed,
    plain_result,
    put_analysis_cache,
    record_stage_metric,
    resume_snapshot_hash,
)


TECH_TERMS = [
    "figma",
    "sketch",
    "photoshop",
    "ps",
    "illustrator",
    "ai",
    "axure",
    "ui",
    "ux",
    "交互",
    "视觉",
    "设计系统",
    "运营",
    "增长",
    "海外",
    "中东",
    "社交",
    "社区",
    "直播",
    "语音房",
    "英语",
    "阿拉伯语",
    "广告",
    "投放",
    "买量",
    "优化",
    "1v1",
    "ai社交",
    "AI社交",
    "聊天",
    "语聊",
    "直播社交",
]

MIDDLE_EAST_TERMS = ["中东", "MENA", "mena", "沙特", "迪拜", "阿联酋", "卡塔尔", "科威特", "阿拉伯"]
OVERSEAS_TERMS = ["海外", "出海", "全球", "国际", "中东", "东南亚", "欧美", "拉美", "MENA", "mena"]
VOICE_CHAT_TERMS = ["语聊", "语音房", "聊天室", "语音直播", "语音社交"]
SOCIAL_APP_TERMS = ["1v1", "1v1社交", "社交", "语音", "直播社交", "语聊", "语音房", "ai社交", "AI社交", "社交app", "社交App", "直播app", "直播App"]
UI_TERMS = ["ui", "UI", "界面设计", "视觉设计", "交互", "产品设计"]
ADS_TERMS = ["广告", "投放", "优化师", "买量", "投放优化", "素材优化"]
NON_CHINA_NATIONALITY_TERMS = [
    "外籍",
    "外国籍",
    "非中国籍",
    "非中国国籍",
    "国籍非中国",
    "不是中国籍",
    "马来西亚籍",
    "新加坡籍",
    "印尼籍",
    "印度籍",
    "越南籍",
    "泰国籍",
    "菲律宾籍",
    "美国籍",
    "英国籍",
    "加拿大籍",
    "澳大利亚籍",
]


def has_text(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def has_positive_text(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    for word in words:
        needle = word.lower()
        start = 0
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            prefix = lowered[max(0, index - 8) : index]
            if not re.search(r"(没有|未|无|不具备|缺少|暂无|没做过|未负责|未参与)", prefix):
                return True
            start = index + len(needle)
    return False


def parse_years(*values: str | None) -> float | None:
    text = " ".join(value or "" for value in values)
    numbers = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*年", text)]
    if numbers:
        return max(numbers)
    months = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*个月", text)]
    if months:
        return max(months) / 12
    return None


def parse_age(*values: str | None) -> int | None:
    text = " ".join(value or "" for value in values)
    match = re.search(r"(\d{2})\s*岁", text)
    if not match:
        return None
    age = int(match.group(1))
    return age if 16 <= age <= 80 else None


def has_years_at_least(text: str, minimum: float) -> bool:
    years = parse_years(text)
    return years is not None and years >= minimum


def hard_requirement_check(job: dict[str, Any], resume: dict[str, Any]) -> tuple[bool, list[str]]:
    requirements = job.get("requirements") or []
    raw_resume_text = str(resume.get("resume_text") or "")
    structured_parts = [
        f"{resume.get('age')}岁" if resume.get("age") is not None else "",
        str(resume.get("education_level") or ""),
        str(resume.get("candidate_name") or ""),
        str(resume.get("target_role") or ""),
        str(resume.get("city") or ""),
        str(resume.get("years_experience") or ""),
        str(resume.get("education_level") or ""),
        " ".join(str(value) for value in (resume.get("features") or {}).values()),
        " ".join(str(value) for value in (resume.get("feature_evidence") or {}).values()),
        " ".join(str(value) for value in (resume.get("skills") or [])),
        " ".join(str(value) for value in (resume.get("languages") or [])),
        " ".join(" ".join(str(value or "") for value in item.values()) for item in (resume.get("experience") or [])),
        " ".join(" ".join(str(value or "") for value in item.values()) for item in (resume.get("projects") or [])),
    ]
    resume_text = " ".join(part for part in [raw_resume_text, *structured_parts] if part)
    features = resume.get("features") or {}
    years = parse_years(str(resume.get("years_experience") or ""), resume_text)
    age = parse_age(str(features.get("age") or ""), resume_text)
    fresh = bool(int(resume.get("is_fresh_graduate") or 0)) or features.get("is_fresh_graduate") == "1"
    missing: list[str] = []

    job_allows_fresh = any(req.get("label") == "entry_level" for req in requirements)
    if fresh and not job_allows_fresh:
        missing.append("岗位不是应届生岗位，候选人偏应届/实习背景")

    for req in requirements:
        if req.get("requirement_type") != "hard":
            continue
        category = req.get("category")
        label = req.get("label")
        min_value = req.get("min_value")
        max_value = req.get("max_value")
        value = req.get("value") or label or ""
        if category == "experience" and label in {"min_years", "years_range"}:
            if years is None or (min_value is not None and years < float(min_value)):
                missing.append(f"工作年限未满足：JD 要求 {value}")
            elif max_value is not None and years > float(max_value):
                missing.append(f"工作年限超出岗位范围：JD 要求 {value}")
        elif category == "education" and label == "bachelor_or_above":
            if features.get("has_bachelor") != "1" and not has_text(resume_text, ["本科", "硕士", "博士"]):
                missing.append("学历未满足本科及以上")
        elif category == "education" and label == "college_or_above":
            if features.get("has_college") != "1" and not has_text(resume_text, ["大专", "专科", "本科", "硕士", "博士"]):
                missing.append("学历未满足大专及以上")
        elif category == "age" and label == "max_age":
            max_age = int(max_value) if max_value is not None else None
            if age is None:
                missing.append(f"未看到年龄信息：JD 要求 {value}")
            elif max_age is not None and age >= max_age:
                missing.append(f"年龄未满足：JD 要求 {value}，候选人 {age} 岁")
        elif category == "language" and label == "english":
            if features.get("has_english") != "1":
                missing.append("未看到英语能力证据")
        elif category == "language" and label == "arabic":
            if features.get("has_arabic") != "1":
                missing.append("未看到阿拉伯语能力证据")
        elif category == "nationality" and label == "china_only":
            if has_text(resume_text, NON_CHINA_NATIONALITY_TERMS):
                missing.append("国籍未满足：JD 要求中国籍/不能是非中国籍")
        elif category == "domain" and label == "social_product_design":
            if features.get("has_social_product_design") != "1":
                missing.append("未看到社交软件/社交产品设计经历")
        elif category == "domain" and label == "middle_east_region_1y":
            if not has_positive_text(resume_text, MIDDLE_EAST_TERMS) or not has_years_at_least(resume_text, float(min_value or 1)):
                missing.append("未看到 1 年以上海外中东地区负责经验")
        elif category == "domain" and label == "voice_chat_business":
            if not has_positive_text(resume_text, VOICE_CHAT_TERMS):
                missing.append("未看到语聊或语音房项目经历")
        elif category == "domain" and label == "overseas_middle_east_ops_2y":
            if not has_positive_text(resume_text, MIDDLE_EAST_TERMS) or not has_positive_text(resume_text, ["运营"]) or not has_years_at_least(resume_text, float(min_value or 2)):
                missing.append("未看到 2 年以上海外中东地区运营经验")
        elif category == "domain" and label == "overseas_region_any":
            if not has_positive_text(resume_text, OVERSEAS_TERMS):
                missing.append("未看到海外地区负责经验")
        elif category == "domain" and label == "social_ads_product_1y":
            overseas_keyword_pass = has_positive_text(resume_text, OVERSEAS_TERMS) and has_positive_text(resume_text, SOCIAL_APP_TERMS)
            original_pass = has_positive_text(resume_text, ADS_TERMS) and has_positive_text(resume_text, SOCIAL_APP_TERMS) and has_years_at_least(resume_text, float(min_value or 1))
            if not original_pass and not overseas_keyword_pass:
                missing.append("未看到 1 年以上社交/直播/语聊/语音房/AI社交产品投放经验")
        elif category == "domain" and label == "overseas_social_ads_keyword":
            if not has_positive_text(resume_text, OVERSEAS_TERMS) or not has_positive_text(resume_text, SOCIAL_APP_TERMS):
                missing.append("未看到海外经历 + 1v1/社交/语音/语聊/直播社交/AI社交任一关键词")
        elif category == "domain" and label == "social_product_ui_1y":
            if not has_positive_text(resume_text, UI_TERMS) or not has_positive_text(resume_text, SOCIAL_APP_TERMS) or not has_years_at_least(resume_text, float(min_value or 1)):
                missing.append("未看到 1 年以上社交App UI设计经验")
    return (not missing, missing)


def matched_terms(job: dict[str, Any], resume: dict[str, Any]) -> list[str]:
    text = " ".join([str(job.get("jd_text") or ""), str(resume.get("resume_text") or ""), " ".join(resume.get("skills") or [])])
    return [term for term in TECH_TERMS if has_text(text, [term]) and has_text(str(resume.get("resume_text") or ""), [term])]


def match_hard_requirements(job: dict[str, Any], resume: dict[str, Any]) -> dict[str, Any]:
    hard_pass, missing_hard = hard_requirement_check(job, resume)
    decision = "BOSS_FORWARD_HR" if hard_pass else "REJECT_DAILY_REPORT"
    matched_evidence = "硬性要求通过" if hard_pass else "JD硬性要求未通过"
    missing_evidence = "；".join(missing_hard) if missing_hard else ""
    summary = (
        f"匹配结论：{decision}。硬性条件：{'通过' if hard_pass else '未通过'}。"
        f"{'缺失项：' + missing_evidence if missing_evidence else ''}"
    )
    return {
        "decision_tier": decision,
        "hard_pass": hard_pass,
        "hard_fail_reasons": "；".join(missing_hard),
        "matched_evidence": matched_evidence,
        "missing_evidence": missing_evidence,
        "summary": summary,
        "recommend_reason": "",
        "risk_reason": "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--job-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    cache_hit = False
    with connect(Path(args.db)) as conn:
        job = get_latest_jd(conn, args.job_ref)
        resume = get_resume(conn, args.job_ref, args.candidate_ref)
        gates = get_jd_hard_gates(conn, job["job_ref"])
        snapshot_hash = resume_snapshot_hash(resume)
        jd_version = str(gates.get("jd_version") or job.get("updated_at") or "legacy")
        cache_key = analysis_cache_key(
            str(resume.get("candidate_key") or args.candidate_ref),
            job["job_ref"],
            snapshot_hash,
            jd_version,
            MATCHER_VERSION,
        )
        cached = get_analysis_cache(conn, cache_key)
        if cached is not None:
            match_result = cached["result"]
            cache_hit = True
        else:
            match_result = match_hard_requirements(job, resume)
            put_analysis_cache(
                conn,
                cache_key=cache_key,
                candidate_key=str(resume.get("candidate_key") or args.candidate_ref),
                job_ref=job["job_ref"],
                candidate_ref=args.candidate_ref,
                snapshot_hash=snapshot_hash,
                jd_version=jd_version,
                matcher_version=MATCHER_VERSION,
                result=match_result,
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        record_stage_metric(
            conn,
            stage="jd_match",
            duration_ms=duration_ms,
            job_ref=args.job_ref,
            candidate_ref=args.candidate_ref,
            model_calls=0,
            cache_hit=cache_hit,
            note=f"jd_version={jd_version};matcher_version={MATCHER_VERSION}",
        )
        match_args = SimpleNamespace(
            job_ref=args.job_ref,
            candidate_ref=args.candidate_ref,
            matched_at=None,
            **match_result,
        )
        inserted = insert_match_record(conn, match_args)
        processed = mark_processed(
            conn,
            args.job_ref,
            args.candidate_ref,
            resume.get("candidate_name"),
            match_result["decision_tier"],
            match_result["summary"],
        )
        conn.commit()
    output = {
        "database_path": str(Path(args.db).resolve()),
        "match_id": inserted["id"],
        "processed_candidate_id": processed["id"],
        "job_ref": args.job_ref,
        "candidate_ref": args.candidate_ref,
        "decision_tier": match_result["decision_tier"],
        "hard_pass": match_result["hard_pass"],
        "matched_evidence": match_result["matched_evidence"],
        "risk_reason": match_result["risk_reason"],
        "analysis_cache": "hit" if cache_hit else "miss_stored",
        "jd_version": jd_version,
        "matcher_version": MATCHER_VERSION,
    }
    print(plain_result(**output))


if __name__ == "__main__":
    main()
