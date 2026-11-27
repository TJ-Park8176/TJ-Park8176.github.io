# ************************************************************************
# ** Code Description: 동행복권 최신 로또 당첨번호 무인 수집, 오행 분석 **
# **                   HTML(시안 B) 자동 발행 및 Sitemap 갱신 스크립트    **
# **                                                                    **
# ** Creator: Origincs / Park.TJ                                        **
# ** Creation Date: 2026.11.14                                          **
# ************************************************************************

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KST = timezone(timedelta(hours=9))
# ~~기존 도메인: BASE_URL = "https://tj-park8176.github.io"~~
# Cloudflare 커스텀 도메인(karma.taejoonlabs.com) 공식 전환-2026.11.23
BASE_URL = "https://karma.taejoonlabs.com"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.taejoonlabs.kingofkarma"
DHLOTTERY_LT645_API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={round_no}"
# 동행복권 회차별 1·2등 당첨 판매점(배출점) 공식 JSON 엔드포인트-2026.11.27
DHLOTTERY_WINNING_STORE_API = (
    "https://www.dhlottery.co.kr/wnprchsplcsrch/selectLtWnShp.do"
    "?srchLtEpsd={round_no}&srchWnShpRnk={rank}&pageNum={page}&recordCountPerPage=200"
)
WEEKLY_STORES_REL_URL = "/stores/weekly-winning-stores.html"
SMOK95_ALL_URL = "https://smok95.github.io/lotto/results/all.json"

TAIL_TO_OHANG = {
    3: "목(木)", 8: "목(木)",
    2: "화(火)", 7: "화(火)",
    5: "토(土)", 0: "토(土)",
    4: "금(金)", 9: "금(金)",
    1: "수(水)", 6: "수(水)",
}

OHANG_SUPPORT_GUIDE = {
    "목(木)": "푸른 청색 계열과 동쪽 방향 기운이 생동하며 새 출발의 기세가 강한 흐름",
    "화(火)": "붉은 적색 계열과 남쪽 방향의 양기가 확장되며 집중력이 상승하는 흐름",
    "토(土)": "황금·황토 계열과 중앙 안정을 바탕으로 균형 잡힌 재물 기운이 모이는 흐름",
    "금(金)": "백색·은빛 계열과 서쪽 방향의 결실 기운이 응축되어 맺어지는 흐름",
    "수(水)": "흑색·남색 계열과 북쪽 방향의 지혜와 순환 기운이 부드럽게 이어지는 흐름",
}


def get_orb_color_style(num: int) -> str:
    """5색 번호대별 시안 B 3D 글래스 오브 그라데이션 반환"""
    if num <= 10:
        return "radial-gradient(circle at 30% 30%, #FFE07D, #D99B16)"
    if num <= 20:
        return "radial-gradient(circle at 30% 30%, #6EC6FF, #1D6AD6)"
    if num <= 30:
        return "radial-gradient(circle at 30% 30%, #FF8A97, #D9384A)"
    if num <= 40:
        return "radial-gradient(circle at 30% 30%, #B4BECC, #5E6878)"
    return "radial-gradient(circle at 30% 30%, #52F7B3, #139E65)"


def calculate_ac_value(numbers: List[int]) -> int:
    """로또 6개 번호의 AC값(산술적 복잡도) 계산"""
    sorted_nums = sorted(numbers)
    diffs = set()
    for i in range(len(sorted_nums)):
        for j in range(i + 1, len(sorted_nums)):
            diffs.add(sorted_nums[j] - sorted_nums[i])
    return len(diffs) - (len(sorted_nums) - 1)


def derive_ohang_theme(numbers: List[int]) -> Tuple[str, str, Dict[str, int]]:
    """당첨번호 6개 끝수 기준 사주 오행 분포와 핵심 테마 자동 산출"""
    counts: Dict[str, int] = {"목(木)": 0, "화(火)": 0, "토(土)": 0, "금(金)": 0, "수(水)": 0}
    for num in numbers:
        ohang = TAIL_TO_OHANG[num % 10]
        counts[ohang] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    primary = ranked[0][0]
    secondary = ranked[1][0] if ranked[1][1] > 0 else primary
    theme = f"{primary}·{secondary} 상생" if primary != secondary else f"{primary} 중심 균형"
    summary_parts = [f"{k} {v}수" for k, v in counts.items() if v > 0]
    breakdown = " · ".join(summary_parts)
    return theme, breakdown, counts


def format_prize_korean(prize_amount: int) -> str:
    """1등 당첨금액을 한국어 읽기 쉬운 단위로 포맷"""
    if prize_amount <= 0:
        return "집계 중"
    if prize_amount >= 100_000_000:
        eok = prize_amount / 100_000_000
        return f"약 {eok:,.1f}억 원 ({prize_amount:,}원)"
    return f"{prize_amount:,}원"


def _summarize_methods(stores: List[dict]) -> Dict[str, int]:
    """자동·수동·반자동 배출 건수 집계-2026.11.27"""
    counts: Dict[str, int] = {"자동": 0, "수동": 0, "반자동": 0}
    for st in stores:
        m = str(st.get("method") or "").strip()
        if m in counts:
            counts[m] += 1
        elif m:
            counts[m] = counts.get(m, 0) + 1
    return counts


def _summarize_regions(stores: List[dict]) -> List[Tuple[str, int]]:
    """시도별 당첨 판매점 분포 내림차순 집계-2026.11.27"""
    counts: Dict[str, int] = {}
    for st in stores:
        reg = str(st.get("region") or "").strip() or "기타"
        counts[reg] = counts.get(reg, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _method_badge_html(method: str) -> str:
    safe_m = html_lib.escape(method or "확인중")
    if method == "자동":
        cls = "method-pill method-auto"
    elif method == "수동":
        cls = "method-pill method-manual"
    else:
        cls = "method-pill method-semi"
    return f'<span class="{cls}">{safe_m}</span>'


def _render_winning_store_rows(stores: List[dict], rank: int) -> str:
    """1·2등 당첨 판매점 HTML 테이블 행 생성-2026.11.27"""
    rows: List[str] = []
    for idx, st in enumerate(stores, start=1):
        name = str(st.get("name") or "").strip()
        addr = str(st.get("address") or "").strip()
        region = str(st.get("region") or "").strip() or "기타"
        method = str(st.get("method") or "").strip() or "확인중"
        search_key = f"{name} {addr} {region} {method}".lower()
        rows.append(
            f'<tr data-rank="{rank}" data-region="{html_lib.escape(region, quote=True)}" '
            f'data-search="{html_lib.escape(search_key, quote=True)}">'
            f'<td style="color:var(--text-muted);font-weight:700;">{idx}</td>'
            f'<td><strong style="color:var(--text-ivory);">{html_lib.escape(name)}</strong></td>'
            f'<td>{_method_badge_html(method)}</td>'
            f'<td style="color:var(--text-muted);">{html_lib.escape(addr)}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def _build_round_winning_stores_card(round_no: int, winning_stores: Optional[dict]) -> Tuple[str, bool]:
    """회차별 분석 페이지 내 [이번 회차 1·2등 당첨 판매점] 카드 생성-2026.11.27"""
    rank1 = list((winning_stores or {}).get("rank1") or [])
    rank2 = list((winning_stores or {}).get("rank2") or [])
    if not rank1 and not rank2:
        waiting_html = f"""
        <div class="card" data-weekly-stores-loaded="0">
            <h2>2. 제{round_no}회 1등·2등 당첨 판매점(배출점) 안내</h2>
            <p style="color: var(--text-muted); margin-bottom: 14px;">
                동행복권 제{round_no}회 당첨 판매점 공식 목록이 집계 중입니다. 추첨 직후 순차적으로 자동 업데이트됩니다.
            </p>
            <div class="cta-row">
                <a class="cta-btn-sub" href="{WEEKLY_STORES_REL_URL}">이번 주 최신 1·2등 당첨 판매점 허브 보기</a>
                <a class="cta-btn-sub" href="/stores/index.html">역대 누적 1등 명당 TOP 34 보기</a>
            </div>
        </div>"""
        return waiting_html, False

    m1 = _summarize_methods(rank1)
    m2 = _summarize_methods(rank2)
    m1_parts = [f"{k} {v}건" for k, v in m1.items() if v > 0]
    m2_parts = [f"{k} {v}건" for k, v in m2.items() if v > 0]
    all_regions = [reg for reg, _ in _summarize_regions(rank1 + rank2)]
    region_chips = "".join(
        f'<button type="button" class="filter-chip{" active" if reg == "전체" else ""}" '
        f'data-round-reg="{html_lib.escape(reg, quote=True)}" '
        f'onclick="filterRoundStores(\'{html_lib.escape(reg, quote=True)}\')">{html_lib.escape(reg)}</button>'
        for reg in (["전체"] + all_regions)
    )
    rank1_rows = _render_winning_store_rows(rank1, 1)
    rank2_rows = _render_winning_store_rows(rank2, 2)
    rank2_block = ""
    if rank2:
        rank2_block = f"""
            <details id="roundRank2Details" class="stores-details">
                <summary>제{round_no}회 2등 당첨 판매점 전체 {len(rank2)}곳 펼치기 ({' · '.join(m2_parts)})</summary>
                <div class="table-wrap" style="margin-top: 12px;">
                    <table class="store-table">
                        <thead><tr><th style="width:46px;">No</th><th>판매점명</th><th style="width:76px;">구분</th><th>소재지</th></tr></thead>
                        <tbody id="roundRank2Body">{rank2_rows}</tbody>
                    </table>
                </div>
            </details>"""

    card_html = f"""
        <div class="card" id="round-winning-stores" data-weekly-stores-loaded="1">
            <h2>2. 제{round_no}회 1등·2등 당첨 판매점(배출점) 총정리</h2>
            <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 14px;">
                동행복권 공식 발표 기준 제{round_no}회 <strong style="color:var(--karma-gold);">1등 배출점 {len(rank1)}곳</strong>({' · '.join(m1_parts) or '집계 완료'})과
                <strong style="color:var(--sonar-jade);">2등 배출점 {len(rank2)}곳</strong> 목록입니다. 지역을 눌러 우리 동네 배출점을 바로 확인하세요.
            </p>
            <div class="filter-bar" role="group" aria-label="시도별 당첨 판매점 필터">
                {region_chips}
            </div>
            <div class="table-wrap">
                <table class="store-table">
                    <thead><tr><th style="width:46px;">No</th><th>1등 당첨 판매점</th><th style="width:76px;">구분</th><th>소재지</th></tr></thead>
                    <tbody id="roundRank1Body">{rank1_rows}</tbody>
                </table>
            </div>
            {rank2_block}
            <div class="cta-row" style="margin-top: 16px;">
                <a class="cta-btn-sub" href="{WEEKLY_STORES_REL_URL}">이번 주 최신 당첨 판매점 · 사주 길방 매칭 바로 가기</a>
                <a class="cta-btn-sub" href="/stores/index.html">전국 누적 1등 명당 순위 TOP 34</a>
            </div>
        </div>"""
    return card_html, True


def render_round_seo_html(
    round_no: int,
    numbers: List[int],
    bonus: int,
    draw_date: str = "",
    first_prize_amount: int = 0,
    element_theme: str = "",
    # ~~coupon_code: str = "kofk261113",~~
    # H-230: 대문자 표준 쿠폰 코드(KOFK261113) 통일-2026.11.22
    coupon_code: str = "KOFK261113",
    has_next_round: bool = False,
    winning_stores: Optional[dict] = None,
) -> str:
    """시안 B 규격 + 1·2등 당첨 판매점 + 1클릭 공유 + 인접 회차 양방향 링크 포함 회차별 사주 오행 SEO HTML 생성-2026.11.27"""
    coupon_code = (coupon_code or "KOFK261113").strip().upper()
    sorted_nums = sorted(int(n) for n in numbers)
    bonus = int(bonus)
    display_date = draw_date or datetime.now().strftime("%Y-%m-%d")
    nums_str = ", ".join(str(n) for n in sorted_nums)

    auto_theme, ohang_breakdown, ohang_counts = derive_ohang_theme(sorted_nums)
    final_theme = element_theme.strip() if element_theme and element_theme.strip() else auto_theme
    dominant_element = sorted(ohang_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    element_comment = OHANG_SUPPORT_GUIDE.get(dominant_element, "")

    odd_cnt = sum(1 for n in sorted_nums if n % 2 == 1)
    even_cnt = 6 - odd_cnt
    low_cnt = sum(1 for n in sorted_nums if n <= 22)
    high_cnt = 6 - low_cnt
    total_sum = sum(sorted_nums)
    ac_value = calculate_ac_value(sorted_nums)
    prize_text = format_prize_korean(first_prize_amount)

    orbs_html = "".join(
        f'<span class="lotto-orb" style="background: {get_orb_color_style(n)};">{n}</span>'
        for n in sorted_nums
    )
    bonus_orb_html = (
        '<span class="plus-txt">+</span>'
        f'<span class="lotto-orb bonus" style="background: {get_orb_color_style(bonus)};">{bonus}</span>'
    )

    prev_round_link = ""
    if round_no > 1248:
        prev_round_link = (
            f'<a class="cta-btn-sub" href="/guides/round-{round_no - 1}-analysis.html">'
            f"직전 제{round_no - 1}회 분석 보기</a>"
        )
    next_round_link = ""
    if has_next_round:
        next_round_link = (
            f'<a class="cta-btn-sub" href="/guides/round-{round_no + 1}-analysis.html">'
            f"다음 제{round_no + 1}회 분석 보기</a>"
        )

    canonical_url = f"{BASE_URL}/guides/round-{round_no}-analysis.html"
    winning_stores_card_html, has_stores_loaded = _build_round_winning_stores_card(round_no, winning_stores)
    rank1_cnt = len((winning_stores or {}).get("rank1") or [])
    rank2_cnt = len((winning_stores or {}).get("rank2") or [])
    stores_title_suffix = f" · 1등 당첨 판매점 {rank1_cnt}곳" if rank1_cnt > 0 else ""
    stores_desc_suffix = (
        f" 1등 당첨 판매점 {rank1_cnt}곳·2등 {rank2_cnt}곳 배출 지역과 자동·수동 현황까지 함께 확인하세요."
        if rank1_cnt > 0
        else f" 내 일주에 맞는 행운 번호와 50,000 공덕 시작 쿠폰({coupon_code}) 혜택을 확인하세요."
    )
    # ~~기존: [로또 N회 당첨번호 분석] ...~~
    # ~~H-224: 롱테일 검색 CTR 및 5만 공덕 쿠폰 소구 Title/Description 표준화-2026.11.18~~
    # 회차별 1·2등 당첨 판매점 배출 정보 통합 반영-2026.11.27
    page_title = (
        f"제{round_no}회 로또 당첨번호{stores_title_suffix} · 사주 오행 분석 "
        f"({nums_str} + {bonus} · {final_theme}) | 공덕왕"
    )
    page_desc = (
        f"제{round_no}회({display_date}) 로또 당첨번호({nums_str} + {bonus})와 "
        f"목·화·토·금·수 오행 분포({final_theme} · 홀짝 {odd_cnt}:{even_cnt} · 총합 {total_sum} · AC {ac_value}) 분석."
        f"{stores_desc_suffix}"
    )

    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": page_title,
            "description": page_desc,
            "datePublished": display_date,
            "dateModified": display_date,
            "mainEntityOfPage": canonical_url,
            "author": {"@type": "Organization", "name": "공덕왕 (King of Karma)"},
            "publisher": {"@type": "Organization", "name": "Taejoon Labs"},
        },
        ensure_ascii=False,
        indent=2,
    )

    prize_stat_html = ""
    if first_prize_amount > 0:
        prize_stat_html = (
            '<div class="stat-box">\n'
            '                    <div class="stat-label">1등 1인당 당첨금</div>\n'
            f'                    <div class="stat-val" style="color: var(--karma-gold);">{prize_text}</div>\n'
            "                </div>"
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="naver-site-verification" content="0796e6b464560edac9370d120a74c9f8a85d225f" />
    <meta name="naver-site-verification" content="9f119f04ba678c0bd33719745297069751709464" />
    <meta name="google-site-verification" content="38CLrsR-Vert1oEBc6ZVuecEKByM-yKScpLHIVtPrdY" />
    <meta name="google-site-verification" content="mUhHkJJcnw3pLYkugLDV9ktjiaMZM67z3SI7XKqhzZ4" />
    <title>{page_title}</title>
    <meta name="description" content="{page_desc}" />
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{page_title}" />
    <meta property="og:description" content="{page_desc}" />
    <meta property="og:url" content="{canonical_url}" />
    <link rel="canonical" href="{canonical_url}" />
    <link rel="alternate" type="application/rss+xml" title="공덕왕 (King of Karma) 로또 명당·사주 RSS" href="{BASE_URL}/rss.xml" />
    <link rel="shortcut icon" href="/favicon.ico" />
    <link rel="icon" type="image/png" href="/assets/app_icon.png" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css" />
    <script type="application/ld+json">
{json_ld}
    </script>
    <style>
        :root {{
            --ink-black: #0B0D13;
            --ink-surface-sub: #171B26;
            --ink-surface-elevated: #1E2330;
            --sonar-jade: #2EF2A0;
            --karma-gold: #FFD666;
            --crimson-fire: #FF6B7A;
            --text-ivory: #F4F6FA;
            --text-muted: #949EB0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--ink-black);
            color: var(--text-ivory);
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.65;
            padding: 36px 20px 80px;
        }}
        .container {{ max-width: 820px; margin: 0 auto; }}
        .badge-top {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--ink-surface-elevated);
            color: var(--sonar-jade);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 14px;
        }}
        .dot-jade {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--sonar-jade);
            box-shadow: 0 0 8px var(--sonar-jade);
            display: inline-block;
        }}
        .dot-gold {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--karma-gold);
            box-shadow: 0 0 8px var(--karma-gold);
            display: inline-block;
        }}
        h1 {{ font-size: 28px; font-weight: 800; margin-bottom: 10px; letter-spacing: -0.02em; }}
        .sub-meta {{ color: var(--text-muted); font-size: 14px; margin-bottom: 28px; }}
        .card {{
            background: var(--ink-surface-sub);
            border-radius: 24px;
            padding: 26px;
            margin-bottom: 22px;
        }}
        .card h2 {{
            font-size: 19px;
            font-weight: 700;
            margin-bottom: 14px;
            color: var(--karma-gold);
        }}
        .orbs-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            margin: 18px 0;
        }}
        .lotto-orb {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 17px;
            color: #0B0D13;
            box-shadow: inset -3px -3px 8px rgba(0,0,0,0.35), 0 6px 14px rgba(0,0,0,0.4);
        }}
        .plus-txt {{ font-size: 22px; font-weight: 700; color: var(--text-muted); }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin-top: 16px;
        }}
        .stat-box {{
            background: var(--ink-surface-elevated);
            border-radius: 16px;
            padding: 16px;
        }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); }}
        .stat-val {{ font-size: 19px; font-weight: 800; color: var(--text-ivory); margin-top: 4px; }}
        .ohang-pill {{
            background: var(--ink-surface-elevated);
            border-radius: 14px;
            padding: 12px 16px;
            margin-top: 14px;
            font-size: 14px;
            color: var(--text-muted);
        }}
        .ohang-pill strong {{ color: var(--sonar-jade); }}
        .coupon-box {{
            background: var(--ink-surface-elevated);
            border-radius: 20px;
            padding: 20px;
            margin-top: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 14px;
        }}
        .coupon-code {{
            font-size: 20px;
            font-weight: 800;
            color: var(--sonar-jade);
            letter-spacing: 0.06em;
        }}
        .cta-row {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .cta-btn {{
            display: inline-block;
            background: var(--sonar-jade);
            color: var(--ink-black);
            font-weight: 800;
            text-decoration: none;
            padding: 14px 22px;
            border-radius: 16px;
            font-size: 15px;
            cursor: pointer;
        }}
        .cta-btn-sub {{
            display: inline-block;
            background: var(--ink-surface-sub);
            color: var(--karma-gold);
            font-weight: 700;
            text-decoration: none;
            padding: 13px 18px;
            border-radius: 16px;
            font-size: 14px;
        }}
        .btn-share {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--ink-surface-sub);
            color: var(--text-ivory);
            font-weight: 700;
            border: none;
            padding: 13px 18px;
            border-radius: 16px;
            font-size: 14px;
            cursor: pointer;
            font-family: inherit;
        }}
        .share-toast {{
            position: fixed;
            left: 50%;
            bottom: 24px;
            transform: translateX(-50%);
            background: var(--ink-surface-elevated);
            color: var(--sonar-jade);
            padding: 12px 20px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 700;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.5);
            display: none;
            align-items: center;
            gap: 8px;
            z-index: 9999;
        }}
        .bridge-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 10px;
            margin-top: 14px;
        }}
        .bridge-step {{
            background: var(--ink-surface-elevated);
            border-radius: 16px;
            padding: 14px 16px;
            font-size: 13.5px;
            color: var(--text-muted);
        }}
        .bridge-step strong {{
            display: block;
            color: var(--text-ivory);
            font-size: 14px;
            margin-bottom: 4px;
        }}
        .bridge-step .step-num {{
            color: var(--sonar-jade);
            font-weight: 800;
            margin-right: 6px;
        }}
        .filter-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 14px;
        }}
        .filter-chip {{
            background: var(--ink-surface-elevated);
            color: var(--text-muted);
            border: none;
            border-radius: 999px;
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            font-family: inherit;
        }}
        .filter-chip.active {{
            background: var(--sonar-jade);
            color: var(--ink-black);
        }}
        .table-wrap {{
            overflow-x: auto;
            border-radius: 16px;
            background: var(--ink-surface-elevated);
        }}
        .store-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }}
        .store-table th, .store-table td {{
            text-align: left;
            padding: 11px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            vertical-align: middle;
        }}
        .store-table th {{
            color: var(--karma-gold);
            font-size: 12.5px;
            font-weight: 700;
        }}
        .method-pill {{
            display: inline-block;
            padding: 3px 9px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 800;
            white-space: nowrap;
        }}
        .method-auto {{ background: rgba(46, 242, 160, 0.14); color: var(--sonar-jade); }}
        .method-manual {{ background: rgba(255, 214, 102, 0.16); color: var(--karma-gold); }}
        .method-semi {{ background: rgba(255, 107, 122, 0.16); color: var(--crimson-fire); }}
        .stores-details {{
            margin-top: 14px;
            background: var(--ink-surface-elevated);
            border-radius: 16px;
            padding: 14px 16px;
        }}
        .stores-details summary {{
            cursor: pointer;
            font-weight: 700;
            font-size: 14px;
            color: var(--sonar-jade);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 16px; font-size: 13px; display: flex; gap: 16px; flex-wrap: wrap;">
            <a href="/" style="color: var(--text-muted); text-decoration: none;">홈으로 돌아가기</a>
            <a href="{WEEKLY_STORES_REL_URL}" style="color: var(--sonar-jade); text-decoration: none; font-weight: 700;">이번 주 1·2등 당첨 판매점</a>
            <a href="/stores/index.html" style="color: var(--text-muted); text-decoration: none;">전국 누적 1등 명당</a>
            <a href="/guides/past-winning-number-check.html" style="color: var(--text-muted); text-decoration: none;">역대 당첨번호 전수 대조기</a>
        </div>
        <div class="badge-top">
            <span class="dot-jade"></span>
            <span>KING OF KARMA WEEKLY SAJU &amp; LOTTO REPORT</span>
        </div>
        <h1>제{round_no}회 로또 당첨번호 및 사주 오행({final_theme}) 정밀 분석</h1>
        <p class="sub-meta">추첨일: {display_date} · 작성: 공덕왕 자동 분석 엔진 · 검수: 시안 B 정적 감사 통과</p>

        <div class="card">
            <h2>1. 제{round_no}회 당첨번호 3D 구체 및 핵심 통계</h2>
            <div class="orbs-row">
                {orbs_html}
                {bonus_orb_html}
            </div>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">홀짝 비율 (Odd : Even)</div>
                    <div class="stat-val">{odd_cnt} : {even_cnt}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">고저 비율 (1~22 : 23~45)</div>
                    <div class="stat-val">{low_cnt} : {high_cnt}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">6개 번호 총합 / AC값</div>
                    <div class="stat-val">{total_sum} (AC {ac_value})</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">핵심 오행 기운</div>
                    <div class="stat-val" style="color: var(--sonar-jade);">{final_theme}</div>
                </div>
                {prize_stat_html}
            </div>
            <div class="ohang-pill">
                끝수 오행 분포: <strong>{ohang_breakdown}</strong> — {element_comment}
            </div>
        </div>
        {winning_stores_card_html}

        <div class="card">
            <h2>3. 제{round_no + 1}회 대비 사주 일간별 공덕 가이드 &amp; 1클릭 공유</h2>
            <p style="color: var(--text-ivory); margin-bottom: 12px;">
                제{round_no}회 추첨에서는 <strong>{final_theme}</strong>의 흐름이 강하게 작용하며 총합 <strong>{total_sum}</strong>, AC값 <strong>{ac_value}</strong> 구간에서 번호가 형성되었습니다.
                다가오는 제{round_no + 1}회차에는 본인의 사주 일간(日干)과 부족한 오행을 보완하는 길방(吉方) 명당 판매점을 확인하고,
                낙첨 복권 스캔(42% 공익기금 기부 환산)과 108 목탁 수행으로 공덕의 그릇을 넓혀 보세요.
            </p>
            <div class="coupon-box" data-ctr-cta-box="1">
                <div>
                    <!-- ~~만료일: 2026-12-31까지~~ -->
                    <!-- H-230: 주간 회차 분석 하단 유형 C 고전환 CTA 카드 및 30초 정착 가이드 반영-2026.11.22 -->
                    <div class="badge-top" style="margin-bottom: 10px;">
                        <span class="dot-gold"></span>
                        <span>꽝 복권 QR 공덕 환전 · 초기 100명 돌파 이벤트</span>
                    </div>
                    <h3 data-ctr-cta-title="1" style="margin: 0 0 8px 0; font-size: 19px; color: var(--text-ivory); line-height: 1.4;">이번 회차 꽝 나온 용지, 버리지 말고 QR 스캔으로 공덕을 쌓아 두세요</h3>
                    <p style="margin: 0 0 12px 0; font-size: 14px; color: var(--text-muted);">
                        꽝 복권 QR을 찍을 때마다 공덕이 누적되며, 다음 회차 당첨 기운을 높이는 오행 분석과 명당 레이더를 함께 쓸 수 있습니다.
                    </p>
                    <div style="font-size: 13px; color: var(--text-muted);">설치 -&gt; 닉네임 등록 -&gt; 쿠폰함 {coupon_code} 입력까지 30초면 50,000P가 즉시 지급됩니다 (2027-12-31까지)</div>
                    <div class="coupon-code" data-kok-coupon-code="1">{coupon_code}</div>
                </div>
                <div class="cta-row">
                    <a class="cta-btn" data-ctr-cta="1" href="{PLAY_STORE_URL}" target="_blank" rel="noopener">공덕왕 무료 설치하고 꽝 복권 적립 시작하기</a>
                    <button type="button" class="btn-share" onclick="copyKokCoupon('{coupon_code}')">
                        <span class="dot-jade"></span>출시 쿠폰 {coupon_code} 복사 (+50,000P)
                    </button>
                    <button type="button" class="btn-share" onclick="shareCalcResult()">
                        <span class="dot-gold"></span>제{round_no}회 분석 결과 카톡·링크 공유
                    </button>
                    {prev_round_link}
                    {next_round_link}
                    <a class="cta-btn-sub" href="/">웹 무료 계산기 모음 보기</a>
                </div>
            </div>
            <div class="bridge-grid" aria-label="30초 정착 3단계 온보딩 가이드">
                <div class="bridge-step">
                    <strong><span class="step-num">01</span>앱 설치</strong>
                    Google Play에서 공덕왕 설치 후 실행하기
                </div>
                <div class="bridge-step">
                    <strong><span class="step-num">02</span>닉네임 1초 등록</strong>
                    닉네임 확정으로 초기 100명 돌파 리더보드 프로필 개설
                </div>
                <div class="bridge-step">
                    <strong><span class="step-num">03</span>쿠폰 입력 및 첫 공덕</strong>
                    쿠폰함 <span style="color: var(--sonar-jade); font-weight: 700;">{coupon_code}</span> 입력 시 50,000P 즉시 지급 및 꽝 복권 적립 시작
                </div>
            </div>
        </div>
    </div>

    <div id="shareToast" class="share-toast" role="status" aria-live="polite">
        <span class="dot-jade"></span>
        <span id="shareToastText">공유 문구가 복사되었습니다.</span>
    </div>

    <script>
        var LAST_SHARE_TITLE = '제{round_no}회 로또 당첨번호 & 사주 오행({final_theme}) 분석';
        var LAST_SHARE_TEXT = '[공덕왕 제{round_no}회 로또 사주 분석]\\n당첨번호: {nums_str} + 보너스 {bonus}\\n핵심 통계: 총합 {total_sum} · AC {ac_value} · 홀짝 {odd_cnt}:{even_cnt} · {final_theme}\\n축원 쿠폰({coupon_code}, +50,000P) & 무료 대조기: {canonical_url}';

        function showShareToast(msg) {{
            var toast = document.getElementById('shareToast');
            var textEl = document.getElementById('shareToastText');
            if (!toast || !textEl) return;
            textEl.textContent = msg;
            toast.style.display = 'inline-flex';
            clearTimeout(window.__shareToastTimer);
            window.__shareToastTimer = setTimeout(function () {{
                toast.style.display = 'none';
            }}, 2800);
        }}

        function fallbackCopyText(text, customMsg) {{
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try {{
                document.execCommand('copy');
                showShareToast(customMsg || '제{round_no}회 분석 결과와 쿠폰 코드가 복사되었습니다. 카카오톡에 붙여넣으세요.');
            }} catch (err) {{
                showShareToast('브라우저에서 복사를 지원하지 않아 주소를 직접 복사해 주세요.');
            }}
            document.body.removeChild(ta);
        }}

        async function copyCouponCode(code) {{
            var target = String(code || '{coupon_code}').trim();
            var toastMsg = '쿠폰 코드 ' + target + ' 복사 완료! 앱 설치 후 설정·보상 탭에 입력하면 50,000P가 즉시 지급됩니다.';
            if (window.KokFunnel && typeof window.KokFunnel.trackEvent === 'function') {{
                window.KokFunnel.trackEvent('coupon_copy');
            }}
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                try {{
                    await navigator.clipboard.writeText(target);
                    showShareToast(toastMsg);
                    return target;
                }} catch (err) {{
                    // 클립보드 API 거부 시 execCommand 폴백
                }}
            }}
            fallbackCopyText(target, toastMsg);
            return target;
        }}
        window.copyKokCoupon = copyCouponCode;

        async function shareCalcResult() {{
            var shareUrl = (window.location && window.location.href) ? window.location.href : '{canonical_url}';
            var payloadText = LAST_SHARE_TEXT;
            if (navigator.share) {{
                try {{
                    await navigator.share({{
                        title: LAST_SHARE_TITLE,
                        text: payloadText,
                        url: shareUrl
                    }});
                    showShareToast('공유창이 열렸습니다.');
                    return payloadText;
                }} catch (err) {{
                    // 사용자 취소 또는 미지원 환경에서는 클립보드 복사로 안전 전환
                }}
            }}
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                try {{
                    await navigator.clipboard.writeText(payloadText);
                    showShareToast('제{round_no}회 분석 결과와 쿠폰 코드가 복사되었습니다.');
                    return payloadText;
                }} catch (err) {{
                    fallbackCopyText(payloadText);
                    return payloadText;
                }}
            }}
            fallbackCopyText(payloadText);
            return payloadText;
        }}

        function filterRoundStores(regionName) {{
            var target = String(regionName || '전체');
            var chips = document.querySelectorAll('[data-round-reg]');
            for (var i = 0; i < chips.length; i++) {{
                var isAct = chips[i].getAttribute('data-round-reg') === target;
                chips[i].classList.toggle('active', isAct);
            }}
            var rows = document.querySelectorAll('#roundRank1Body tr, #roundRank2Body tr');
            for (var j = 0; j < rows.length; j++) {{
                var reg = rows[j].getAttribute('data-region') || '';
                rows[j].style.display = (target === '전체' || reg === target) ? '' : 'none';
            }}
            var det = document.getElementById('roundRank2Details');
            if (det && target !== '전체') det.open = true;
        }}
    </script>
    <script defer src="/assets/kok_funnel_sdk.js"></script>
</body>
</html>
"""


def render_weekly_winning_stores_html(
    round_no: int,
    numbers: List[int],
    bonus: int,
    draw_date: str,
    first_prize_amount: int,
    winning_stores: Optional[dict],
    recent_rounds: List[int],
    coupon_code: str = "KOFK261113",
) -> str:
    """상시 고정 URL(/stores/weekly-winning-stores.html) 이번 주 최신 로또 1·2등 당첨 판매점 허브 생성-2026.11.27"""
    coupon_code = (coupon_code or "KOFK261113").strip().upper()
    sorted_nums = sorted(int(n) for n in numbers)
    bonus = int(bonus)
    display_date = draw_date or datetime.now(KST).strftime("%Y-%m-%d")
    nums_str = ", ".join(str(n) for n in sorted_nums)
    prize_text = format_prize_korean(first_prize_amount)

    rank1 = list((winning_stores or {}).get("rank1") or [])
    rank2 = list((winning_stores or {}).get("rank2") or [])
    m1 = _summarize_methods(rank1)
    m2 = _summarize_methods(rank2)
    m1_str = " · ".join(f"{k} {v}" for k, v in m1.items() if v > 0) or "집계 중"
    m2_str = " · ".join(f"{k} {v}" for k, v in m2.items() if v > 0) or "집계 중"
    reg_summary = _summarize_regions(rank1 + rank2)
    top_reg_str = " · ".join(f"{r} {c}곳" for r, c in reg_summary[:5]) or "전국 집계 중"

    canonical_url = f"{BASE_URL}{WEEKLY_STORES_REL_URL}"
    if rank1:
        page_title = (
            f"제{round_no}회 이번 주 로또 1등 당첨 판매점 {len(rank1)}곳 · 2등 {len(rank2)}곳 총정리 "
            f"({display_date} · {m1_str}) | 공덕왕"
        )
        page_desc = (
            f"제{round_no}회({display_date}) 로또 1등 당첨 판매점 {len(rank1)}곳({m1_str})과 2등 배출점 {len(rank2)}곳 "
            f"전체 지역·상호명·주소를 시도별 필터와 검색으로 바로 조회하고, 오늘 내 사주 길방과 맞는 1등 배출점을 매칭해 보세요."
        )
    else:
        page_title = f"제{round_no}회 이번 주 로또 1등·2등 당첨 판매점(배출점) 실시간 안내 | 공덕왕"
        page_desc = (
            f"제{round_no}회({display_date}) 동행복권 로또 1등·2등 당첨 판매점 배출 지역·자동/수동 현황 및 "
            f"오늘 내 사주 길방 명당 매칭 안내입니다."
        )

    orbs_html = "".join(
        f'<span class="lotto-orb" style="background: {get_orb_color_style(n)};">{n}</span>'
        for n in sorted_nums
    )
    bonus_orb_html = (
        '<span class="plus-txt">+</span>'
        f'<span class="lotto-orb" style="background: {get_orb_color_style(bonus)};">{bonus}</span>'
    )

    all_regions = [reg for reg, _ in reg_summary]
    region_chips = "".join(
        f'<button type="button" class="filter-chip{" active" if reg == "전체" else ""}" '
        f'data-weekly-reg="{html_lib.escape(reg, quote=True)}" '
        f'onclick="setWeeklyRegion(\'{html_lib.escape(reg, quote=True)}\')">{html_lib.escape(reg)}</button>'
        for reg in (["전체"] + all_regions)
    )

    if rank1 or rank2:
        rank1_rows = _render_winning_store_rows(rank1, 1)
        rank2_rows = _render_winning_store_rows(rank2, 2)
        stores_loaded_flag = "1"
        stores_section_html = f"""
        <div class="card" id="weekly-stores-directory" data-weekly-stores-loaded="1">
            <h2>2. 제{round_no}회 1등·2등 당첨 판매점 전체 목록 (지역 필터 · 상호 검색)</h2>
            <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 14px;">
                동행복권 공식 발표 데이터 기준입니다. 시도 칩을 누르거나 동네명·판매점명을 입력하면 1등·2등 배출점이 즉시 필터링됩니다.
            </p>
            <div class="search-row">
                <input type="text" id="weeklyStoreSearch" class="text-input" placeholder="동네명 또는 판매점명 검색 (예: 서울, 강남, 용인, 복권방)" oninput="filterWeeklyStores()" />
                <span id="weeklyVisibleCount" class="count-pill">1등 {len(rank1)}곳 · 2등 {len(rank2)}곳 표시 중</span>
            </div>
            <div class="filter-bar" role="group" aria-label="시도별 당첨 판매점 필터">
                {region_chips}
            </div>
            <div class="table-wrap">
                <table class="store-table">
                    <thead><tr><th style="width:46px;">No</th><th>1등 당첨 판매점 ({len(rank1)}곳)</th><th style="width:76px;">구분</th><th>소재지</th></tr></thead>
                    <tbody id="weeklyRank1Body">{rank1_rows}</tbody>
                </table>
            </div>
            <details id="weeklyRank2Details" class="stores-details">
                <summary>제{round_no}회 2등 당첨 판매점 전체 {len(rank2)}곳 펼치기 ({m2_str})</summary>
                <div class="table-wrap" style="margin-top: 12px;">
                    <table class="store-table">
                        <thead><tr><th style="width:46px;">No</th><th>2등 당첨 판매점 ({len(rank2)}곳)</th><th style="width:76px;">구분</th><th>소재지</th></tr></thead>
                        <tbody id="weeklyRank2Body">{rank2_rows}</tbody>
                    </table>
                </div>
            </details>
        </div>"""
    else:
        stores_loaded_flag = "0"
        stores_section_html = f"""
        <div class="card" id="weekly-stores-directory" data-weekly-stores-loaded="0">
            <h2>2. 제{round_no}회 1등·2등 당첨 판매점 공식 집계 대기 중</h2>
            <p style="color: var(--text-muted); font-size: 14.5px;">
                동행복권 제{round_no}회 1·2등 당첨 판매점 공식 목록이 아직 공개되지 않았습니다.
                토요일 밤 21:15~21:45 및 일요일 오전 자동 수집 주기에 따라 공개 즉시 이 페이지에 반영됩니다.
            </p>
        </div>"""

    rank1_json = json.dumps(
        [
            {
                "name": str(s.get("name") or ""),
                "address": str(s.get("address") or ""),
                "region": str(s.get("region") or ""),
                "method": str(s.get("method") or ""),
            }
            for s in rank1
        ],
        ensure_ascii=False,
    )

    archive_links = "".join(
        f'<a class="cta-btn-sub" href="/guides/round-{r}-analysis.html">제{r}회 당첨번호·판매점 보기</a>'
        for r in recent_rounds[:6]
    )

    item_list_elements = [
        {
            "@type": "ListItem",
            "position": idx,
            "name": f"{s.get('name', '')} ({s.get('method', '')})",
            "description": s.get("address", ""),
        }
        for idx, s in enumerate(rank1[:20], start=1)
    ]
    json_ld_itemlist = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"제{round_no}회 로또 1등 당첨 판매점 목록",
            "numberOfItems": len(rank1),
            "itemListElement": item_list_elements,
        },
        ensure_ascii=False,
        indent=2,
    )
    json_ld_faq = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f"제{round_no}회 로또 1등 당첨 판매점은 몇 곳이고 자동·수동 비율은 어떻게 되나요?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": f"제{round_no}회({display_date}) 동행복권 공식 발표 기준 1등 배출점은 총 {len(rank1)}곳({m1_str}), 2등 배출점은 총 {len(rank2)}곳({m2_str})입니다.",
                    },
                },
                {
                    "@type": "Question",
                    "name": "이번 주 1등 당첨 판매점은 매주 언제 업데이트되나요?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "매주 토요일 오후 8시 45분 추첨 방송 후 동행복권 공식 당첨 판매점 공개 시점(21:10~21:45 KST)에 맞춰 자동으로 최신 회차로 갱신됩니다.",
                    },
                },
            ],
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="naver-site-verification" content="0796e6b464560edac9370d120a74c9f8a85d225f" />
    <meta name="naver-site-verification" content="9f119f04ba678c0bd33719745297069751709464" />
    <meta name="google-site-verification" content="38CLrsR-Vert1oEBc6ZVuecEKByM-yKScpLHIVtPrdY" />
    <meta name="google-site-verification" content="mUhHkJJcnw3pLYkugLDV9ktjiaMZM67z3SI7XKqhzZ4" />
    <title>{html_lib.escape(page_title)}</title>
    <meta name="description" content="{html_lib.escape(page_desc, quote=True)}" />
    <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="공덕왕 (King of Karma)" />
    <meta property="og:title" content="{html_lib.escape(page_title, quote=True)}" />
    <meta property="og:description" content="{html_lib.escape(page_desc, quote=True)}" />
    <meta property="og:url" content="{canonical_url}" />
    <meta property="og:image" content="{BASE_URL}/assets/feature_graphic.png" />
    <link rel="canonical" href="{canonical_url}" />
    <link rel="alternate" type="application/rss+xml" title="공덕왕 (King of Karma) 로또 명당·사주 RSS" href="{BASE_URL}/rss.xml" />
    <link rel="shortcut icon" href="/favicon.ico" />
    <link rel="icon" type="image/png" href="/assets/app_icon.png" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css" />
    <script type="application/ld+json">
{json_ld_itemlist}
    </script>
    <script type="application/ld+json">
{json_ld_faq}
    </script>
    <style>
        :root {{
            --ink-black: #0B0D13;
            --ink-surface-sub: #171B26;
            --ink-surface-elevated: #1E2330;
            --sonar-jade: #2EF2A0;
            --karma-gold: #FFD666;
            --crimson-fire: #FF6B7A;
            --text-ivory: #F4F6FA;
            --text-muted: #949EB0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--ink-black);
            color: var(--text-ivory);
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.65;
            padding: 32px 20px 88px;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .top-nav {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            margin-bottom: 18px;
            font-size: 13.5px;
            font-weight: 600;
        }}
        .top-nav a {{ color: var(--text-muted); text-decoration: none; }}
        .top-nav a:hover {{ color: var(--sonar-jade); }}
        .badge-top {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--ink-surface-elevated);
            color: var(--sonar-jade);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 12px;
        }}
        .dot-jade {{
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--sonar-jade); box-shadow: 0 0 8px var(--sonar-jade); display: inline-block;
        }}
        .dot-gold {{
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--karma-gold); box-shadow: 0 0 8px var(--karma-gold); display: inline-block;
        }}
        h1 {{ font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px; }}
        .sub-meta {{ color: var(--text-muted); font-size: 14px; margin-bottom: 24px; }}
        .card {{
            background: var(--ink-surface-sub);
            border-radius: 24px;
            padding: 26px;
            margin-bottom: 20px;
        }}
        .card h2 {{
            font-size: 19px;
            font-weight: 700;
            color: var(--karma-gold);
            margin-bottom: 12px;
        }}
        .orbs-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 14px 0 18px; }}
        .lotto-orb {{
            width: 44px; height: 44px; border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 16px; color: #0B0D13;
            box-shadow: inset -3px -3px 8px rgba(0,0,0,0.35), 0 6px 14px rgba(0,0,0,0.4);
        }}
        .plus-txt {{ font-size: 20px; font-weight: 700; color: var(--text-muted); }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
            gap: 12px;
        }}
        .stat-box {{
            background: var(--ink-surface-elevated);
            border-radius: 16px;
            padding: 15px 16px;
        }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); }}
        .stat-val {{ font-size: 18px; font-weight: 800; color: var(--text-ivory); margin-top: 4px; }}
        .widget-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            margin-top: 12px;
        }}
        .text-input {{
            background: var(--ink-surface-elevated);
            color: var(--text-ivory);
            border: none;
            border-radius: 14px;
            padding: 12px 15px;
            font-size: 14px;
            font-family: inherit;
            flex: 1 1 220px;
        }}
        .cta-btn {{
            display: inline-block;
            background: var(--sonar-jade);
            color: var(--ink-black);
            font-weight: 800;
            text-decoration: none;
            border: none;
            padding: 12px 20px;
            border-radius: 14px;
            font-size: 14.5px;
            cursor: pointer;
            font-family: inherit;
        }}
        .cta-btn-sub {{
            display: inline-block;
            background: var(--ink-surface-elevated);
            color: var(--karma-gold);
            font-weight: 700;
            text-decoration: none;
            padding: 11px 16px;
            border-radius: 14px;
            font-size: 13.5px;
        }}
        .cta-row {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
        .result-panel {{
            display: none;
            margin-top: 14px;
            background: var(--ink-surface-elevated);
            border-radius: 18px;
            padding: 18px;
        }}
        .search-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            margin-bottom: 12px;
        }}
        .count-pill {{
            background: var(--ink-surface-elevated);
            color: var(--sonar-jade);
            font-size: 13px;
            font-weight: 700;
            padding: 10px 14px;
            border-radius: 14px;
            white-space: nowrap;
        }}
        .filter-bar {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
        .filter-chip {{
            background: var(--ink-surface-elevated);
            color: var(--text-muted);
            border: none;
            border-radius: 999px;
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            font-family: inherit;
        }}
        .filter-chip.active {{ background: var(--sonar-jade); color: var(--ink-black); }}
        .table-wrap {{
            overflow-x: auto;
            border-radius: 16px;
            background: var(--ink-surface-elevated);
        }}
        .store-table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
        .store-table th, .store-table td {{
            text-align: left;
            padding: 11px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            vertical-align: middle;
        }}
        .store-table th {{ color: var(--karma-gold); font-size: 12.5px; font-weight: 700; }}
        .method-pill {{
            display: inline-block;
            padding: 3px 9px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 800;
            white-space: nowrap;
        }}
        .method-auto {{ background: rgba(46, 242, 160, 0.14); color: var(--sonar-jade); }}
        .method-manual {{ background: rgba(255, 214, 102, 0.16); color: var(--karma-gold); }}
        .method-semi {{ background: rgba(255, 107, 122, 0.16); color: var(--crimson-fire); }}
        .stores-details {{
            margin-top: 14px;
            background: var(--ink-surface-elevated);
            border-radius: 16px;
            padding: 14px 16px;
        }}
        .stores-details summary {{
            cursor: pointer;
            font-weight: 700;
            font-size: 14px;
            color: var(--sonar-jade);
        }}
    </style>
</head>
<body data-weekly-stores-loaded="{stores_loaded_flag}">
    <div class="container">
        <nav class="top-nav" aria-label="주요 메뉴">
            <a href="/">홈</a>
            <a href="/guides/round-{round_no}-analysis.html" style="color: var(--karma-gold);">제{round_no}회 오행 분석</a>
            <a href="/stores/index.html">역대 누적 1등 명당 TOP 34</a>
            <a href="/guides/past-winning-number-check.html">역대 당첨번호 대조기</a>
            <a href="/guides/lotto-first-prize-tax-real-payout-calculator.html">1등 세금 실수령액</a>
        </nav>

        <div class="badge-top">
            <span class="dot-jade"></span>
            <span>WEEKLY LOTTO WINNING STORES · 제{round_no}회 최신 자동 갱신</span>
        </div>
        <h1>이번 주 제{round_no}회 로또 1등·2등 당첨 판매점(배출점) 총정리</h1>
        <p class="sub-meta">추첨일: {display_date} · 당첨번호: {nums_str} + 보너스 {bonus} · 출처: 동행복권 공식 발표</p>

        <div class="card">
            <h2>1. 제{round_no}회 당첨 핵심 요약 &amp; 1·2등 배출 현황</h2>
            <div class="orbs-row">
                {orbs_html}
                {bonus_orb_html}
            </div>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-label">1등 배출 판매점</div>
                    <div class="stat-val" style="color: var(--karma-gold);">{len(rank1)}곳 ({m1_str})</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">2등 배출 판매점</div>
                    <div class="stat-val" style="color: var(--sonar-jade);">{len(rank2)}곳 ({m2_str})</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">1등 1인당 당첨금</div>
                    <div class="stat-val">{prize_text}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">주요 배출 지역 분포</div>
                    <div class="stat-val" style="font-size: 14.5px; line-height: 1.4;">{html_lib.escape(top_reg_str)}</div>
                </div>
            </div>
        </div>

        <div class="card" id="weekly-saju-matcher">
            <div class="badge-top" style="margin-bottom: 10px;">
                <span class="dot-gold"></span>
                <span>1초 사주 길방 매칭 · 제{round_no}회 1등 배출점 궁합</span>
            </div>
            <h2>이번 주 1등 배출점 중 오늘 내 사주 길방과 맞는 곳은?</h2>
            <p style="color: var(--text-muted); font-size: 14px;">
                생년월일을 입력하면 오늘 부족한 오행 방위와 제{round_no}회 1등 배출 판매점 중 궁합 1순위 매장을 1초 만에 찾아드립니다.
            </p>
            <div class="widget-row">
                <input type="date" id="weeklyBirthDate" class="text-input" value="1990-05-15" aria-label="생년월일" style="max-width: 240px;" />
                <button type="button" class="cta-btn" onclick="matchWeeklyWinnerBySaju(true)">내 사주 맞춤 1등 판매점 찾기</button>
            </div>
            <div id="weeklySajuResult" class="result-panel"></div>
        </div>

        {stores_section_html}

        <div class="card">
            <h2>3. 최근 회차별 당첨번호·배출점 아카이브 &amp; 전국 누적 명당</h2>
            <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 14px;">
                지난 회차의 1·2등 배출점과 사주 오행 분석, 그리고 대한민국 역대 최다 1등 배출 명당 순위까지 함께 확인해 보세요.
            </p>
            <div class="cta-row">
                {archive_links}
                <a class="cta-btn-sub" href="/stores/index.html">역대 누적 1등 명당 TOP 34</a>
                <a class="cta-btn" data-ctr-cta="1" href="{PLAY_STORE_URL}" target="_blank" rel="noopener">공덕왕 앱에서 내 주변 명당 GPS 레이더 + {coupon_code}(50,000P) 받기</a>
            </div>
        </div>
    </div>

    <script>
        var WEEKLY_RANK1_STORES = {rank1_json};
        var WEEKLY_OHANG_GUIDES = [
            {{ elem: '목(木) 보강', dir: '동쪽 · 동남쪽 길방', nums: '3, 8, 13, 18, 28, 33' }},
            {{ elem: '화(火) 보강', dir: '남쪽 · 남동쪽 길방', nums: '2, 7, 12, 17, 27, 32' }},
            {{ elem: '토(土) 보강', dir: '중앙 · 남서쪽 길방', nums: '5, 10, 15, 20, 30, 35' }},
            {{ elem: '금(金) 보강', dir: '서쪽 · 북서쪽 길방', nums: '4, 9, 14, 19, 29, 39' }},
            {{ elem: '수(水) 보강', dir: '북쪽 · 북동쪽 길방', nums: '1, 6, 11, 16, 26, 36' }}
        ];
        var ACTIVE_WEEKLY_REGION = '전체';

        function setWeeklyRegion(regionName) {{
            ACTIVE_WEEKLY_REGION = String(regionName || '전체');
            var chips = document.querySelectorAll('[data-weekly-reg]');
            for (var i = 0; i < chips.length; i++) {{
                chips[i].classList.toggle('active', chips[i].getAttribute('data-weekly-reg') === ACTIVE_WEEKLY_REGION);
            }}
            filterWeeklyStores();
        }}

        function filterWeeklyStores(regionOverride, queryOverride) {{
            if (typeof regionOverride === 'string') {{
                ACTIVE_WEEKLY_REGION = regionOverride || '전체';
            }}
            var qInput = document.getElementById('weeklyStoreSearch');
            var q = (typeof queryOverride === 'string' ? queryOverride : (qInput && qInput.value ? qInput.value : '')).trim().toLowerCase();
            var r1Visible = 0;
            var r2Visible = 0;
            var r1Rows = document.querySelectorAll('#weeklyRank1Body tr');
            for (var i = 0; i < r1Rows.length; i++) {{
                var reg1 = r1Rows[i].getAttribute('data-region') || '';
                var txt1 = r1Rows[i].getAttribute('data-search') || '';
                var ok1 = (ACTIVE_WEEKLY_REGION === '전체' || reg1 === ACTIVE_WEEKLY_REGION) && (!q || txt1.indexOf(q) !== -1);
                r1Rows[i].style.display = ok1 ? '' : 'none';
                if (ok1) r1Visible++;
            }}
            var r2Rows = document.querySelectorAll('#weeklyRank2Body tr');
            for (var j = 0; j < r2Rows.length; j++) {{
                var reg2 = r2Rows[j].getAttribute('data-region') || '';
                var txt2 = r2Rows[j].getAttribute('data-search') || '';
                var ok2 = (ACTIVE_WEEKLY_REGION === '전체' || reg2 === ACTIVE_WEEKLY_REGION) && (!q || txt2.indexOf(q) !== -1);
                r2Rows[j].style.display = ok2 ? '' : 'none';
                if (ok2) r2Visible++;
            }}
            var cntEl = document.getElementById('weeklyVisibleCount');
            if (cntEl) {{
                cntEl.textContent = '1등 ' + r1Visible + '곳 · 2등 ' + r2Visible + '곳 표시 중';
            }}
            var det = document.getElementById('weeklyRank2Details');
            if (det && (q.length > 0 || ACTIVE_WEEKLY_REGION !== '전체')) {{
                det.open = true;
            }}
            return {{ rank1: r1Visible, rank2: r2Visible }};
        }}

        function matchWeeklyWinnerBySaju(isUserAction) {{
            var inp = document.getElementById('weeklyBirthDate');
            var val = (inp && inp.value) ? inp.value : '1990-05-15';
            var digits = val.replace(/[^0-9]/g, '');
            var sum = 0;
            for (var i = 0; i < digits.length; i++) sum += parseInt(digits.charAt(i), 10) || 0;
            var daySeed = new Date().getDate();
            var ohang = WEEKLY_OHANG_GUIDES[(sum + daySeed) % WEEKLY_OHANG_GUIDES.length];
            var picked = WEEKLY_RANK1_STORES.length > 0
                ? WEEKLY_RANK1_STORES[(sum + daySeed) % WEEKLY_RANK1_STORES.length]
                : {{ name: '전국 1등 명당 레이더', address: '공덕왕 앱에서 내 위치 기준 실시간 조회', region: '전국', method: '실시간' }};
            var score = 90 + ((sum * 5 + daySeed) % 9);
            var panel = document.getElementById('weeklySajuResult');
            if (!panel) return null;
            if (isUserAction && window.KokFunnel && typeof window.KokFunnel.trackToolUse === 'function') {{
                window.KokFunnel.trackToolUse('{WEEKLY_STORES_REL_URL}');
            }}
            panel.style.display = 'block';
            panel.innerHTML =
                '<div class="badge-top" style="margin-bottom:8px;"><span class="dot-jade"></span>오늘 제{round_no}회 1등 배출점 사주 궁합 ' + score + '점</div>' +
                '<h3 style="margin:0 0 6px 0; color:var(--karma-gold); font-size:19px;">추천 1등 배출점: ' + picked.name + ' (' + picked.method + ')</h3>' +
                '<p style="margin:0 0 8px 0; font-size:14px; color:var(--text-ivory);">소재지: <strong>' + picked.address + '</strong><br/>' +
                '오늘 내 용신 방위: <strong style="color:var(--sonar-jade);">' + ohang.elem + ' · ' + ohang.dir + '</strong> (행운수 후보: ' + ohang.nums + ')</p>' +
                '<p style="margin:0 0 12px 0; font-size:13px; color:var(--karma-gold); font-weight:700;">' +
                '앱 전용 기능: 내 현재 위치 기준 가까운 1등 명당 GPS 나침반 + 반경 50m 도착 공덕 스탬프 + 축원 쿠폰 {coupon_code} (+50,000P) 자동 귀속</p>' +
                '<div class="cta-row">' +
                '<a class="cta-btn" href="{PLAY_STORE_URL}" target="_blank" rel="noopener">공덕왕 앱에서 내 주변 명당 GPS 레이더 + 50,000P 바로 받기</a>' +
                '</div>';
            if (window.KokFunnel && typeof window.KokFunnel.applyAttributionToLinksAndCta === 'function') {{
                window.KokFunnel.applyAttributionToLinksAndCta();
            }}
            return picked;
        }}
        window.addEventListener('DOMContentLoaded', function() {{ matchWeeklyWinnerBySaju(false); }});
    </script>
    <script defer src="/assets/kok_funnel_sdk.js"></script>
</body>
</html>
"""


def render_weekly_rounds_hub_html(by_round: Dict[int, list], max_cards: int = 4) -> str:
    """홈 index.html에 삽입되는 최신 회차 분석 링크 허브 섹션(시안 B 규격, 고아 페이지 제거용) 생성"""
    target_rounds = [r for r in sorted(by_round.keys(), reverse=True) if r >= 1248][:max_cards]
    if not target_rounds and by_round:
        target_rounds = sorted(by_round.keys(), reverse=True)[:1]

    cards_html: List[str] = []
    for idx, rno in enumerate(target_rounds):
        row = by_round[rno]
        draw_date = str(row[1])
        nums = sorted(int(n) for n in row[2])
        bonus = int(row[3])
        prize_amount = int(row[4]) if len(row) > 4 else 0
        theme, _, _ = derive_ohang_theme(nums)
        ac_val = calculate_ac_value(nums)
        prize_short = format_prize_korean(prize_amount).split(" (")[0]
        orbs_mini = "".join(
            f'<span class="lotto-orb" style="width:28px;height:28px;font-size:12px;margin-right:4px;background:{get_orb_color_style(n)};">{n}</span>'
            for n in nums
        )
        bonus_mini = (
            '<span style="color:var(--muted);font-weight:700;margin:0 4px;">+</span>'
            f'<span class="lotto-orb" style="width:28px;height:28px;font-size:12px;margin-right:0;background:{get_orb_color_style(bonus)};">{bonus}</span>'
        )
        badge_cls = "badge badge-gold" if idx == 0 else "badge"
        dot_cls = "orb-dot-gold" if idx == 0 else "orb-dot"
        badge_label = f"최신 제{rno}회 · {draw_date}" if idx == 0 else f"제{rno}회 · {draw_date}"
        cards_html.append(
            f"""        <a class="card-elevated" style="text-decoration:none; display:block;" href="/guides/round-{rno}-analysis.html">
          <span class="{badge_cls}" style="margin-bottom:8px;"><span class="{dot_cls}"></span>{badge_label}</span>
          <h3 style="margin-top:0; color:var(--text);">제{rno}회 당첨번호 &amp; {theme} 오행 분석</h3>
          <div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin:10px 0 12px 0;">{orbs_mini}{bonus_mini}</div>
          <p style="margin:0; font-size:13.5px;">AC {ac_val} · 합계 {sum(nums)} · 1등 {prize_short} · 사주 오행 &amp; {rno + 1}회 전략 보기 →</p>
        </a>"""
        )

    latest_rno = target_rounds[0] if target_rounds else 0
    weekly_stores_banner = ""
    if latest_rno > 0:
        weekly_stores_banner = (
            f'      <a class="card-elevated" style="text-decoration:none; display:flex; justify-content:space-between; '
            f'align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:14px;" href="{WEEKLY_STORES_REL_URL}">\n'
            f'        <div>\n'
            f'          <span class="badge badge-gold" style="margin-bottom:6px;"><span class="orb-dot-gold"></span>매주 토요일 자동 갱신 · 최신 제{latest_rno}회</span>\n'
            f'          <div style="font-size:17px; font-weight:800; color:var(--text);">이번 주 제{latest_rno}회 로또 1등·2등 당첨 판매점(배출점) 전체 목록 보기</div>\n'
            f'          <div style="font-size:13px; color:var(--muted); margin-top:2px;">시도별 필터 · 동네/상호명 검색 · 자동/수동 비율 · 오늘 내 사주 길방 1등 배출점 매칭</div>\n'
            f'        </div>\n'
            f'        <span class="btn-primary" style="padding:10px 16px; font-size:13.5px;">이번 주 1등 판매점 보기 →</span>\n'
            f'      </a>\n'
        )
    cards_joined = "\n".join(cards_html)
    return (
        "<!-- WEEKLY_ROUNDS_SECTION_START -->\n"
        '    <section class="card" id="weekly-rounds-hub">\n'
        '      <span class="badge"><span class="orb-dot"></span>주간 로또 당첨번호 · 1·2등 배출점 &amp; 사주 오행 자동 발행 아카이브</span>\n'
        "      <h2>최신 회차별 당첨번호 · 1등 당첨 판매점 &amp; 다음 회차 길방 전략</h2>\n"
        "      <p>매주 토요일 동행복권 추첨 직후 자동 업데이트되는 회차별 1·2등 당첨 판매점, 당첨번호 분포, AC값 및 사주 오행 해설입니다.</p>\n"
        f"{weekly_stores_banner}"
        '      <div class="grid-2">\n'
        f"{cards_joined}\n"
        "      </div>\n"
        "    </section>\n"
        "    <!-- WEEKLY_ROUNDS_SECTION_END -->"
    )


def refresh_weekly_rounds_in_index_html(index_path: Path, by_round: Dict[int, list]) -> bool:
    """홈 index.html의 최신 회차 링크 허브와 1~N회 표기를 멱등 동기화"""
    if not index_path.exists() or not by_round:
        return False

    raw = index_path.read_text(encoding="utf-8")
    updated = raw
    latest_round = max(by_round.keys())
    updated = re.sub(r"1~\d+회", f"1~{latest_round}회", updated)

    section_html = render_weekly_rounds_hub_html(by_round)
    pattern = re.compile(
        r"<!-- WEEKLY_ROUNDS_SECTION_START -->.*?<!-- WEEKLY_ROUNDS_SECTION_END -->",
        re.DOTALL,
    )
    if pattern.search(updated):
        updated = pattern.sub(lambda _: section_html, updated, count=1)

    if updated != raw:
        index_path.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def collect_sorted_round_paths(guides_dir: Path) -> List[str]:
    """guides 디렉터리 내 round-*-analysis.html 경로를 회차 내림차순으로 반환"""
    rounds: List[Tuple[int, str]] = []
    if not guides_dir.exists():
        return []
    for path in guides_dir.glob("round-*-analysis.html"):
        m = re.match(r"round-(\d+)-analysis\.html$", path.name)
        if m:
            rounds.append((int(m.group(1)), f"/guides/{path.name}"))
    rounds.sort(key=lambda item: item[0], reverse=True)
    return [rel for _, rel in rounds]


def refresh_round_urls_in_sitemap(
    sitemap_path: Path,
    sitemap_index_path: Optional[Path],
    guides_dir: Path,
) -> bool:
    """순수 <loc> 표준 규격으로 sitemap.xml 및 sitemap_index.xml을 멱등 갱신"""
    round_paths = collect_sorted_round_paths(guides_dir)
    if not round_paths:
        return False

    existing_urls: List[str] = []
    if sitemap_path.exists():
        raw = sitemap_path.read_text(encoding="utf-8")
        existing_urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", raw)

    # 기존 정적 URL 목록에서 round-*-analysis.html 및 홈 제거 후 표준 순서 재조합
    static_non_round: List[str] = []
    seen = set()
    home_url = f"{BASE_URL}/"
    for url in existing_urls:
        normalized = url.strip().replace("https://tj-park8176.github.io", BASE_URL)
        if not normalized or normalized == home_url:
            continue
        if re.search(r"/guides/round-\d+-analysis\.html$", normalized):
            continue
        if normalized not in seen:
            seen.add(normalized)
            static_non_round.append(normalized)

    # ~~기존 주석~~ -> 고의도 롱테일(guides/lt-*.html) + 60갑자 일주·시군구 명당 드립 페이지 동적 수록-2026.11.23
    drip_longtail_urls: List[str] = [
        f"{BASE_URL}/guides/{p.name}"
        for p in sorted(guides_dir.glob("lt-*.html"))
    ]
    drip_ilju_urls: List[str] = []
    if (guides_dir / "ilju-index.html").exists():
        drip_ilju_urls.append(f"{BASE_URL}/guides/ilju-index.html")
    for p in sorted(guides_dir.glob("ilju-*.html")):
        if p.name != "ilju-index.html":
            drip_ilju_urls.append(f"{BASE_URL}/guides/{p.name}")

    stores_dir = guides_dir.parent / "stores"
    drip_region_urls: List[str] = []
    if stores_dir.exists():
        for p in sorted(stores_dir.glob("region-*.html")):
            drip_region_urls.append(f"{BASE_URL}/stores/{p.name}")

    weekly_stores_url = f"{BASE_URL}{WEEKLY_STORES_REL_URL}"
    filtered_static = [
        u for u in static_non_round
        if "/guides/lt-" not in u
        and "/guides/ilju-" not in u
        and "/stores/region-" not in u
        and u != weekly_stores_url
    ]
    ordered_urls = (
        [home_url, weekly_stores_url]
        + [f"{BASE_URL}{rel}" for rel in round_paths]
        + drip_longtail_urls
        + filtered_static
        + drip_ilju_urls
        + drip_region_urls
    )
    lastmod_date = datetime.now(KST).strftime("%Y-%m-%d")
    url_entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lastmod_date}</lastmod>\n  </url>" for u in ordered_urls
    )
    new_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_entries}\n"
        "</urlset>\n"
    )
    new_index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <sitemap>\n"
        f"    <loc>{BASE_URL}/sitemap.xml</loc>\n"
        f"    <lastmod>{lastmod_date}</lastmod>\n"
        "  </sitemap>\n"
        "</sitemapindex>\n"
    )

    changed = False
    old_sitemap = sitemap_path.read_text(encoding="utf-8") if sitemap_path.exists() else ""
    if old_sitemap != new_xml:
        sitemap_path.write_text(new_xml, encoding="utf-8", newline="\n")
        changed = True
    if sitemap_index_path is not None:
        old_index = sitemap_index_path.read_text(encoding="utf-8") if sitemap_index_path.exists() else ""
        if old_index != new_index_xml:
            sitemap_index_path.write_text(new_index_xml, encoding="utf-8", newline="\n")
            changed = True
    rss_changed = refresh_rss_feed_standalone(sitemap_path.parent, ordered_urls)
    return changed or rss_changed


def refresh_rss_feed_standalone(site_root: Path, ordered_urls: List[str]) -> bool:
    """GitHub Actions 단독 실행 시에도 rss.xml(최신 당첨 판매점·회차 우선 30건)을 멱등 갱신-2026.11.27"""
    now_kst = datetime.now(KST)
    candidates: List[Tuple[int, float, int, str, str, str, datetime]] = []
    for idx, full_url in enumerate(ordered_urls):
        if not full_url.startswith(BASE_URL):
            continue
        rel_path = full_url[len(BASE_URL):] or "/"
        if rel_path in ("/privacy-policy.html", "/delete-account.html"):
            continue
        fp = site_root / "index.html" if rel_path in ("/", "/index.html") else site_root / rel_path.lstrip("/")
        if not fp.exists() or not fp.is_file():
            continue
        raw_html = fp.read_text(encoding="utf-8", errors="ignore")
        title_m = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', raw_html, re.IGNORECASE)
        raw_title = html_lib.unescape(re.sub(r"\s+", " ", title_m.group(1)).strip()) if title_m else f"공덕왕 ({rel_path})"
        raw_desc = html_lib.unescape(re.sub(r"\s+", " ", desc_m.group(1)).strip()) if desc_m else raw_title
        try:
            pub_dt = min(datetime.fromtimestamp(fp.stat().st_mtime, tz=KST), now_kst)
        except OSError:
            pub_dt = now_kst
        is_boosted = (
            rel_path == WEEKLY_STORES_REL_URL
            or rel_path.startswith("/guides/round-")
            or rel_path.startswith("/guides/lt-")
            or rel_path in (
                "/",
                "/guides/lottery-public-fund-42-percent-donation.html",
                "/stores/seoul-gangnam-seocho-songpa.html",
                "/stores/gyeonggi-suwon-seongnam-yongin.html",
                "/stores/seoul-nowon-jongno-yeongdeungpo.html",
            )
        )
        candidates.append((1 if is_boosted else 0, pub_dt.timestamp(), -idx, rel_path, raw_title, raw_desc, pub_dt))

    if not candidates:
        return False

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    selected = candidates[:30]
    item_xml_parts: List[str] = []
    for _boost, _ts, _ord, rel_path, title_txt, desc_txt, pub_dt in selected:
        full_url = f"{BASE_URL}{rel_path}"
        item_xml_parts.append(
            f"""    <item>
      <title>{html_lib.escape(title_txt, quote=False)}</title>
      <link>{html_lib.escape(full_url, quote=False)}</link>
      <guid isPermaLink="true">{html_lib.escape(full_url, quote=False)}</guid>
      <pubDate>{format_datetime(pub_dt)}</pubDate>
      <description>{html_lib.escape(desc_txt, quote=False)}</description>
    </item>"""
        )

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>공덕왕 (King of Karma) — 로또 당첨 판매점 · 명당 · 사주 길방 가이드</title>
    <link>{BASE_URL}/</link>
    <description>매주 토요일 로또 1·2등 당첨 판매점(배출점), 전국 1등 명당 영업시간·위치, 42% 복권기금 계산기 및 회차별 오행 분석을 제공합니다.</description>
    <language>ko</language>
    <lastBuildDate>{format_datetime(now_kst)}</lastBuildDate>
    <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml" />
{chr(10).join(item_xml_parts)}
  </channel>
</rss>
"""
    rss_path = site_root / "rss.xml"
    old_rss = rss_path.read_text(encoding="utf-8") if rss_path.exists() else ""
    if old_rss != rss_xml:
        rss_path.write_text(rss_xml, encoding="utf-8", newline="\n")
        return True
    return False


def _http_get_json(url: str, timeout: int = 12, extra_headers: Optional[Dict[str, str]] = None) -> Optional[object]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.dhlottery.co.kr/",
        "Accept": "application/json, text/plain, */*",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            if not raw or not (raw.startswith("{") or raw.startswith("[")):
                return None
            return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def fetch_winning_stores_from_dhlottery(round_no: int) -> Optional[dict]:
    """동행복권 공식 selectLtWnShp.do JSON 엔드포인트에서 회차별 1·2등 당첨 판매점 전수 조회-2026.11.27"""
    extra = {
        "Referer": "https://www.dhlottery.co.kr/wnprchsplcsrch/home",
        "X-Requested-With": "XMLHttpRequest",
    }
    result_by_rank: Dict[int, List[dict]] = {1: [], 2: []}
    for rank in (1, 2):
        collected: List[dict] = []
        page = 1
        while page <= 5:
            url = DHLOTTERY_WINNING_STORE_API.format(round_no=round_no, rank=rank, page=page)
            data = _http_get_json(url, timeout=14, extra_headers=extra)
            if not isinstance(data, dict):
                break
            body = data.get("data") or {}
            rows = body.get("list") or []
            total = int(body.get("total") or 0)
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("shpNm") or item.get("tradNm") or "").strip()
                addr = str(item.get("shpAddr") or item.get("rdnm") or "").strip()
                if not name and not addr:
                    continue
                collected.append(
                    {
                        "name": name,
                        "address": addr,
                        "region": str(item.get("region") or "").strip() or "기타",
                        "method": str(item.get("atmtPsvYnTxt") or "").strip() or "확인중",
                        "lat": float(item.get("shpLat") or 0.0),
                        "lng": float(item.get("shpLot") or 0.0),
                        "rank": rank,
                    }
                )
            if total <= 0 or len(collected) >= total:
                break
            page += 1
        result_by_rank[rank] = collected

    if not result_by_rank[1] and not result_by_rank[2]:
        return None
    return {
        "round": round_no,
        "rank1": result_by_rank[1],
        "rank2": result_by_rank[2],
        "fetchedAt": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
    }


def load_weekly_winning_stores(cache_path: Path) -> Dict[int, dict]:
    if not cache_path.exists():
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {int(k): v for k, v in raw.items() if isinstance(v, dict)}
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def save_weekly_winning_stores(cache_path: Path, store_map: Dict[int, dict]) -> None:
    ordered = {str(k): store_map[k] for k in sorted(store_map.keys(), reverse=True)}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def fetch_round_from_dhlottery(round_no: int) -> Optional[dict]:
    """동행복권 공식 lt645 JSON 엔드포인트에서 단일 회차 조회"""
    data = _http_get_json(DHLOTTERY_LT645_API.format(round_no=round_no))
    if not isinstance(data, dict):
        return None
    rows = (data.get("data") or {}).get("list") or []
    if not rows:
        return None
    row = rows[0]
    ymd = str(row.get("ltRflYmd") or "")
    draw_date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}" if len(ymd) == 8 else ymd
    nums = sorted([int(row[f"tm{i}WnNo"]) for i in range(1, 7)])
    return {
        "round": int(row["ltEpsd"]),
        "drawDate": draw_date,
        "numbers": nums,
        "bonus": int(row["bnsWnNo"]),
        "firstPrizeAmount": int(row.get("rnk1WnAmt") or 0),
    }


def fetch_draws_from_smok95_since(min_round_exclusive: int) -> List[dict]:
    """해외 Runner 차단 대비 보조 소스(smok95 all.json)에서 신규 회차 일괄 조회"""
    data = _http_get_json(SMOK95_ALL_URL, timeout=18)
    if not isinstance(data, list):
        return []
    out: List[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rno = int(item.get("draw_no") or 0)
        if rno <= min_round_exclusive:
            continue
        nums = sorted([int(x) for x in item.get("numbers", [])])
        if len(nums) != 6:
            continue
        date_str = str(item.get("date") or "")[:10]
        first_prize = int(((item.get("divisions") or [{}])[0]).get("prize") or 0)
        out.append(
            {
                "round": rno,
                "drawDate": date_str,
                "numbers": nums,
                "bonus": int(item.get("bonus_no") or 0),
                "firstPrizeAmount": first_prize,
            }
        )
    out.sort(key=lambda d: d["round"])
    return out


def sync_latest_lotto(
    site_root: Path,
    seed_file: Optional[Path] = None,
    # ~~coupon_code: str = "kofk261113",~~
    # H-230: 대문자 표준 쿠폰 코드(KOFK261113) 통일-2026.11.22
    coupon_code: str = "KOFK261113",
    ensure_from_round: int = 1248,
    force_regenerate: bool = False,
) -> Dict[str, object]:
    """최신 회차를 수집하여 JSON, 회차별 SEO HTML, Sitemap을 멱등 동기화"""
    compact_path = site_root / "assets" / "lotto_draws_compact.json"
    guides_dir = site_root / "guides"
    sitemap_path = site_root / "sitemap.xml"
    sitemap_index_path = site_root / "sitemap_index.xml"

    if not compact_path.exists():
        raise FileNotFoundError(f"compact JSON 파일이 없습니다: {compact_path}")

    compact_draws = json.loads(compact_path.read_text(encoding="utf-8"))
    by_round: Dict[int, list] = {int(row[0]): row for row in compact_draws}
    max_existing_round = max(by_round.keys()) if by_round else 0

    new_rounds_fetched: List[dict] = []
    probe = max_existing_round + 1
    while probe <= max_existing_round + 6:
        item = fetch_round_from_dhlottery(probe)
        if not item:
            break
        new_rounds_fetched.append(item)
        probe += 1

    # 1차 동행복권이 비어있거나 실패한 경우(예: 해외 Runner 차단 또는 누락) 2차 폴백 조회
    current_top = max([max_existing_round] + [d["round"] for d in new_rounds_fetched])
    fallback_items = fetch_draws_from_smok95_since(current_top)
    if fallback_items:
        new_rounds_fetched.extend(fallback_items)

    compact_updated = False
    for item in new_rounds_fetched:
        rno = item["round"]
        if rno not in by_round:
            by_round[rno] = [
                rno,
                item["drawDate"],
                item["numbers"],
                item["bonus"],
                item["firstPrizeAmount"],
            ]
            compact_updated = True

    sorted_rows = [by_round[r] for r in sorted(by_round.keys(), reverse=True)]
    if compact_updated:
        compact_path.write_text(
            json.dumps(sorted_rows, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )

    # 로컬 앱 에셋(lotto_draws_seed.json)이 함께 존재하는 워크스페이스인 경우 동기화
    seed_updated = False
    if seed_file is None:
        candidate = site_root.parent / "app" / "src" / "main" / "assets" / "lotto_draws_seed.json"
        if candidate.exists():
            seed_file = candidate
    if seed_file is not None and seed_file.exists() and new_rounds_fetched:
        seed_rows = json.loads(seed_file.read_text(encoding="utf-8"))
        seed_by_round = {int(row["round"]): row for row in seed_rows}
        for item in new_rounds_fetched:
            rno = item["round"]
            if rno not in seed_by_round:
                n = item["numbers"]
                seed_by_round[rno] = {
                    "round": rno,
                    "drawDate": item["drawDate"],
                    "n1": n[0], "n2": n[1], "n3": n[2],
                    "n4": n[3], "n5": n[4], "n6": n[5],
                    "bonus": item["bonus"],
                    "firstPrizeAmount": item["firstPrizeAmount"],
                }
                seed_updated = True
        if seed_updated:
            merged_seed = [seed_by_round[r] for r in sorted(seed_by_round.keys(), reverse=True)]
            seed_file.write_text(
                json.dumps(merged_seed, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )

    # ensure_from_round 이상 중 HTML이 없거나 새로 추가된 회차(직전 회차 포함) 또는 판매점 미반영/force_regenerate 시 HTML 생성-2026.11.27
    guides_dir.mkdir(parents=True, exist_ok=True)
    stores_dir = site_root / "stores"
    stores_dir.mkdir(parents=True, exist_ok=True)
    stores_cache_path = site_root / "assets" / "weekly_winning_stores.json"
    winning_stores_map = load_weekly_winning_stores(stores_cache_path)
    stores_cache_updated = False

    generated_files: List[str] = []
    newly_added_rounds = {int(d["round"]) for d in new_rounds_fetched}
    target_rounds = [r for r in sorted(by_round.keys()) if r >= ensure_from_round]

    for rno in target_rounds:
        cached = winning_stores_map.get(rno)
        has_cached_data = bool(cached and (cached.get("rank1") or cached.get("rank2")))
        if not has_cached_data:
            fetched_stores = fetch_winning_stores_from_dhlottery(rno)
            if fetched_stores is not None:
                winning_stores_map[rno] = fetched_stores
                stores_cache_updated = True

    if stores_cache_updated:
        save_weekly_winning_stores(stores_cache_path, winning_stores_map)

    for rno in target_rounds:
        row = by_round[rno]
        out_html = guides_dir / f"round-{rno}-analysis.html"
        existing_raw = out_html.read_text(encoding="utf-8") if out_html.exists() else ""
        round_stores = winning_stores_map.get(rno)
        has_round_stores = bool(round_stores and (round_stores.get("rank1") or round_stores.get("rank2")))
        # ~~기존 조건: force_regenerate or not out_html.exists() or rno in newly_added_rounds or (rno + 1) in newly_added_rounds~~
        # ~~1st-Party 무쿠키 퍼널 SDK(kok_funnel_sdk.js) 누락 파일 자동 재생성 조건 추가-2026.11.15~~
        # ~~H-230: 하단 고전환 CTA(data-ctr-cta-box) 및 대문자 쿠폰(KOFK261113) 미반영 파일 자동 재생성 조건 추가-2026.11.22~~
        # 회차별 1·2등 당첨 판매점 데이터 확보 시 미반영 페이지 자동 자가 치유 조건 추가-2026.11.27
        if (
            force_regenerate
            or not out_html.exists()
            or rno in newly_added_rounds
            or (rno + 1) in newly_added_rounds
            or "/assets/kok_funnel_sdk.js" not in existing_raw
            or 'data-ctr-cta-box="1"' not in existing_raw
            or (has_round_stores and 'data-weekly-stores-loaded="1"' not in existing_raw)
        ):
            html = render_round_seo_html(
                round_no=int(row[0]),
                numbers=list(row[2]),
                bonus=int(row[3]),
                draw_date=str(row[1]),
                first_prize_amount=int(row[4]),
                coupon_code=coupon_code,
                has_next_round=(rno + 1) in by_round,
                winning_stores=round_stores,
            )
            if existing_raw != html:
                out_html.write_text(html, encoding="utf-8", newline="\n")
                generated_files.append(str(out_html))

    # 상시 고정 URL(/stores/weekly-winning-stores.html) 최신 회차 당첨 판매점 허브 갱신-2026.11.27
    weekly_hub_updated = False
    latest_round = max(by_round.keys()) if by_round else 0
    if latest_round > 0:
        latest_row = by_round[latest_round]
        weekly_hub_path = stores_dir / "weekly-winning-stores.html"
        recent_desc = sorted(target_rounds, reverse=True)
        weekly_hub_html = render_weekly_winning_stores_html(
            round_no=int(latest_row[0]),
            numbers=list(latest_row[2]),
            bonus=int(latest_row[3]),
            draw_date=str(latest_row[1]),
            first_prize_amount=int(latest_row[4]),
            winning_stores=winning_stores_map.get(latest_round),
            recent_rounds=recent_desc,
            coupon_code=coupon_code,
        )
        old_weekly_hub = weekly_hub_path.read_text(encoding="utf-8") if weekly_hub_path.exists() else ""
        if old_weekly_hub != weekly_hub_html:
            weekly_hub_path.write_text(weekly_hub_html, encoding="utf-8", newline="\n")
            generated_files.append(str(weekly_hub_path))
            weekly_hub_updated = True

    index_updated = refresh_weekly_rounds_in_index_html(site_root / "index.html", by_round)
    sitemap_updated = refresh_round_urls_in_sitemap(sitemap_path, sitemap_index_path, guides_dir)
    return {
        "latest_round": latest_round,
        "new_rounds": [d["round"] for d in new_rounds_fetched],
        "compact_updated": compact_updated,
        "seed_updated": seed_updated,
        "stores_cache_updated": stores_cache_updated,
        "weekly_hub_updated": weekly_hub_updated,
        "stores_cached_rounds": sorted(winning_stores_map.keys(), reverse=True),
        "generated_files": generated_files,
        "index_updated": index_updated,
        "sitemap_updated": sitemap_updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="무인 주간 로또 당첨번호 수집 및 SEO 자동 발행기")
    parser.add_argument(
        "--site-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs",
        help="정적 웹사이트 루트 경로 (로컬 docs 또는 GitHub Pages .)",
    )
    # ~~parser.add_argument("--coupon", type=str, default="kofk261113", help="삽입할 복덕 쿠폰 코드")~~
    # H-230: 기본 쿠폰 코드 대문자 통일-2026.11.22
    parser.add_argument("--coupon", type=str, default="KOFK261113", help="삽입할 복덕 쿠폰 코드")
    parser.add_argument("--ensure-from", type=int, default=1248, help="해당 회차 이상 누락 HTML 보완")
    parser.add_argument("--force", action="store_true", help="1248회 이후 분석 페이지 강제 재생성")
    args = parser.parse_args()

    result = sync_latest_lotto(
        site_root=args.site_root.resolve(),
        coupon_code=args.coupon,
        ensure_from_round=args.ensure_from,
        force_regenerate=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
