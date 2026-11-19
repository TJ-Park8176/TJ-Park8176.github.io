# ************************************************************************
# ** Code Description: 동행복권 최신 로또 당첨번호 무인 수집, 오행 분석 **
# **                   HTML(시안 B) 자동 발행 및 Sitemap 갱신 스크립트    **
# **                                                                    **
# ** Creator: Origincs / Park.TJ                                        **
# ** Creation Date: 2026.11.14                                          **
# ************************************************************************

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://tj-park8176.github.io"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.taejoonlabs.kingofkarma"
DHLOTTERY_LT645_API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={round_no}"
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


def render_round_seo_html(
    round_no: int,
    numbers: List[int],
    bonus: int,
    draw_date: str = "",
    first_prize_amount: int = 0,
    element_theme: str = "",
    coupon_code: str = "kofk261113",
    has_next_round: bool = False,
) -> str:
    """시안 B 규격 + 1클릭 공유 버튼 + 인접 회차 양방향 링크 포함 회차별 사주 오행 SEO HTML 생성"""
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
    # ~~기존: [로또 N회 당첨번호 분석] ...~~
    # H-224: 롱테일 검색 CTR 및 5만 공덕 쿠폰 소구 Title/Description 표준화-2026.11.18
    page_title = (
        f"제{round_no}회 로또 당첨번호 사주 오행 상생 분석 및 다음 회차 행운 수 "
        f"({nums_str} + {bonus} · {final_theme}) | 공덕왕"
    )
    page_desc = (
        f"제{round_no}회({display_date}) 로또 당첨번호({nums_str} + {bonus})와 "
        f"목·화·토·금·수 오행 분포({final_theme} · 홀짝 {odd_cnt}:{even_cnt} · 총합 {total_sum} · AC {ac_value})를 분석하고, "
        f"내 일주에 맞는 행운 번호와 50,000 공덕 시작 쿠폰({coupon_code}) 혜택을 확인하세요."
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
    <meta name="naver-site-verification" content="9f119f04ba678c0bd33719745297069751709464" />
    <meta name="google-site-verification" content="mUhHkJJcnw3pLYkugLDV9ktjiaMZM67z3SI7XKqhzZ4" />
    <title>{page_title}</title>
    <meta name="description" content="{page_desc}" />
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{page_title}" />
    <meta property="og:description" content="{page_desc}" />
    <meta property="og:url" content="{canonical_url}" />
    <link rel="canonical" href="{canonical_url}" />
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
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 16px; font-size: 13px; display: flex; gap: 16px; flex-wrap: wrap;">
            <a href="/" style="color: var(--text-muted); text-decoration: none;">홈으로 돌아가기</a>
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

        <div class="card">
            <h2>2. 제{round_no + 1}회 대비 사주 일간별 공덕 가이드 &amp; 1클릭 공유</h2>
            <p style="color: var(--text-ivory); margin-bottom: 12px;">
                제{round_no}회 추첨에서는 <strong>{final_theme}</strong>의 흐름이 강하게 작용하며 총합 <strong>{total_sum}</strong>, AC값 <strong>{ac_value}</strong> 구간에서 번호가 형성되었습니다.
                다가오는 제{round_no + 1}회차에는 본인의 사주 일간(日干)과 부족한 오행을 보완하는 길방(吉方) 명당 판매점을 확인하고,
                낙첨 복권 스캔(42% 공익기금 기부 환산)과 108 목탁 수행으로 공덕의 그릇을 넓혀 보세요.
            </p>
            <div class="coupon-box">
                <div>
                    <!-- ~~만료일: 2026-12-31까지~~ -->
                    <div style="font-size: 13px; color: var(--text-muted);">신규 도반 전용 50,000P 쿠폰 [{coupon_code}] 복사 후 30초 만에 기명 랭킹 등록 (2027-12-31까지)</div>
                    <div class="coupon-code" data-kok-coupon-code="1">{coupon_code}</div>
                </div>
                <div class="cta-row">
                    <button type="button" class="btn-share" onclick="copyCouponCode('{coupon_code}')">
                        <span class="dot-jade"></span>5만 공덕 쿠폰 복사
                    </button>
                    <button type="button" class="btn-share" onclick="shareCalcResult()">
                        <span class="dot-gold"></span>제{round_no}회 분석 결과 카톡·링크 공유
                    </button>
                    <a class="cta-btn" href="{PLAY_STORE_URL}" target="_blank" rel="noopener">제{round_no}회 오행 흐름 반영 완료 · 앱 설치 후 쿠폰({coupon_code})으로 5만 공덕 즉시 수령</a>
                    {prev_round_link}
                    {next_round_link}
                    <a class="cta-btn-sub" href="/">웹 무료 계산기 모음 보기</a>
                </div>
            </div>
            <div class="bridge-grid" aria-label="미전환 기기 3단계 온보딩 가이드">
                <div class="bridge-step">
                    <strong><span class="step-num">01</span>앱 설치</strong>
                    Google Play에서 '공덕왕' 설치 후 실행하기
                </div>
                <div class="bridge-step">
                    <strong><span class="step-num">02</span>5만 공덕 즉시 지급</strong>
                    설정·보상 탭에서 쿠폰 코드 <span style="color: var(--sonar-jade); font-weight: 700;">{coupon_code}</span> 입력 (50,000P 즉시 적립)
                </div>
                <div class="bridge-step">
                    <strong><span class="step-num">03</span>기명 도반 정착</strong>
                    법명(닉네임) 설정 및 1회 번호 추출·QR 스캔 완료 시 전국 리더보드 즉시 등재
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

    cards_joined = "\n".join(cards_html)
    return (
        "<!-- WEEKLY_ROUNDS_SECTION_START -->\n"
        '    <section class="card" id="weekly-rounds-hub">\n'
        '      <span class="badge"><span class="orb-dot"></span>주간 로또 당첨번호 &amp; 사주 오행 자동 발행 아카이브</span>\n'
        "      <h2>최신 회차별 당첨번호 오행 통계 &amp; 다음 회차 길방 전략</h2>\n"
        "      <p>매주 토요일 동행복권 추첨 직후 자동 업데이트되는 회차별 당첨번호 분포, AC값 및 사주 오행 해설입니다.</p>\n"
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
        normalized = url.strip()
        if not normalized or normalized == home_url:
            continue
        if re.search(r"/guides/round-\d+-analysis\.html$", normalized):
            continue
        if normalized not in seen:
            seen.add(normalized)
            static_non_round.append(normalized)

    # ~~기존 주석~~ -> 순수 <loc> 표준 규격으로 sitemap.xml 갱신 및 60갑자 일주·시군구 명당 드립 페이지 동적 수록-2026.11.15
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

    filtered_static = [
        u for u in static_non_round
        if "/guides/ilju-" not in u and "/stores/region-" not in u
    ]
    ordered_urls = (
        [home_url]
        + [f"{BASE_URL}{rel}" for rel in round_paths]
        + filtered_static
        + drip_ilju_urls
        + drip_region_urls
    )
    lastmod_date = datetime.now().strftime("%Y-%m-%d")
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
    return changed


def _http_get_json(url: str, timeout: int = 12) -> Optional[object]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.dhlottery.co.kr/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            if not raw or not (raw.startswith("{") or raw.startswith("[")):
                return None
            return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


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
    coupon_code: str = "kofk261113",
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

    # ensure_from_round 이상 중 HTML이 없거나 새로 추가된 회차(직전 회차 포함) 또는 force_regenerate 시 HTML 생성
    guides_dir.mkdir(parents=True, exist_ok=True)
    generated_files: List[str] = []
    newly_added_rounds = {int(d["round"]) for d in new_rounds_fetched}
    target_rounds = [r for r in sorted(by_round.keys()) if r >= ensure_from_round]
    for rno in target_rounds:
        row = by_round[rno]
        out_html = guides_dir / f"round-{rno}-analysis.html"
        existing_raw = out_html.read_text(encoding="utf-8") if out_html.exists() else ""
        # ~~기존 조건: force_regenerate or not out_html.exists() or rno in newly_added_rounds or (rno + 1) in newly_added_rounds~~
        # 1st-Party 무쿠키 퍼널 SDK(kok_funnel_sdk.js) 누락 파일 자동 재생성 조건 추가-2026.11.15
        if (
            force_regenerate
            or not out_html.exists()
            or rno in newly_added_rounds
            or (rno + 1) in newly_added_rounds
            or "/assets/kok_funnel_sdk.js" not in existing_raw
        ):
            html = render_round_seo_html(
                round_no=int(row[0]),
                numbers=list(row[2]),
                bonus=int(row[3]),
                draw_date=str(row[1]),
                first_prize_amount=int(row[4]),
                coupon_code=coupon_code,
                has_next_round=(rno + 1) in by_round,
            )
            if existing_raw != html:
                out_html.write_text(html, encoding="utf-8", newline="\n")
                generated_files.append(str(out_html))

    index_updated = refresh_weekly_rounds_in_index_html(site_root / "index.html", by_round)
    sitemap_updated = refresh_round_urls_in_sitemap(sitemap_path, sitemap_index_path, guides_dir)
    latest_round = max(by_round.keys()) if by_round else 0
    return {
        "latest_round": latest_round,
        "new_rounds": [d["round"] for d in new_rounds_fetched],
        "compact_updated": compact_updated,
        "seed_updated": seed_updated,
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
    parser.add_argument("--coupon", type=str, default="kofk261113", help="삽입할 복덕 쿠폰 코드")
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
