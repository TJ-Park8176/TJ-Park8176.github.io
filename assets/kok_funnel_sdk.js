/*
 * ************************************************************************
 * ** Code Description: 공덕왕 웹->앱 1st-Party 무쿠키 퍼널 텔레메트리 SDK **
 * **                   및 Google Play Install Referrer 링크 자동 주입기  **
 * **                                                                    **
 * ** Creator: Origincs / Park.TJ                                        **
 * ** Creation Date: 2026.11.15                                          **
 * ************************************************************************
 */
(function (root) {
  'use strict';

  var SUPABASE_URL = 'https://mjdavtstfsljnnerswvk.supabase.co';
  var SUPABASE_ANON_KEY =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
    'eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1qZGF2dHN0ZnNsam5uZXJzd3ZrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1NDY3OTgsImV4cCI6MjEwODEyMjc5OH0.' +
    'BHKu1bbzJUsFq16_MECjTsepE1T6_blkGhjRZKSBJOE';
  var DEFAULT_COUPON = 'kofk261113';
  var PLAY_STORE_BASE = 'https://play.google.com/store/apps/details?id=com.taejoonlabs.kingofkarma';
  var MEMORY_DEDUP = Object.create(null);

  function safeStorageGet(key) {
    try {
      if (root.sessionStorage && root.sessionStorage.getItem) {
        return root.sessionStorage.getItem(key) || '';
      }
    } catch (e) {}
    return '';
  }

  function safeStorageSet(key, value) {
    try {
      if (root.sessionStorage && root.sessionStorage.setItem) {
        root.sessionStorage.setItem(key, value);
      }
    } catch (e) {}
  }

  function getOrCreateSessionId() {
    if (root.__kokAnonSid) return root.__kokAnonSid;
    var existing = safeStorageGet('kok_anon_sid_v1');
    if (existing && existing.length >= 8) {
      root.__kokAnonSid = existing;
      return existing;
    }
    var randPart = Math.random().toString(36).slice(2, 10);
    var tsPart = Date.now().toString(36);
    var generated = 'kok_w_' + tsPart + '_' + randPart;
    safeStorageSet('kok_anon_sid_v1', generated);
    root.__kokAnonSid = generated;
    return generated;
  }

  function getSearchString() {
    try {
      return (root.location && root.location.search) ? String(root.location.search) : '';
    } catch (e) {
      return '';
    }
  }

  function parseQueryMap(searchStr) {
    var out = Object.create(null);
    if (!searchStr) return out;
    var raw = searchStr.charAt(0) === '?' ? searchStr.slice(1) : searchStr;
    if (!raw) return out;
    var pairs = raw.split('&');
    for (var i = 0; i < pairs.length; i++) {
      var kv = pairs[i].split('=');
      var k = decodeURIComponent((kv[0] || '').replace(/\+/g, ' ')).trim().toLowerCase();
      if (!k) continue;
      var v = kv.length > 1 ? decodeURIComponent(kv.slice(1).join('=').replace(/\+/g, ' ')).trim() : '';
      out[k] = v;
    }
    return out;
  }

  function normalizePagePath(rawPath) {
    var path = String(rawPath || '/').split('?')[0].split('#')[0].trim();
    if (!path || path === '/index.html') return '/';
    if (path.charAt(0) !== '/') path = '/' + path;
    return path.slice(0, 160);
  }

  function resolvePagePath() {
    try {
      if (root.location && root.location.pathname) {
        return normalizePagePath(root.location.pathname);
      }
    } catch (e) {}
    return '/';
  }

  function resolveCouponCode() {
    var q = parseQueryMap(getSearchString());
    var candidate = q.cp || q.coupon || safeStorageGet('kok_active_cp_v1') || '';
    if (candidate && /^[A-Za-z0-9_-]{3,24}$/.test(candidate)) {
      safeStorageSet('kok_active_cp_v1', candidate);
      return candidate;
    }
    return DEFAULT_COUPON;
  }

  function resolveSourceChannel() {
    var q = parseQueryMap(getSearchString());
    var explicit = q.ch || q.utm_source || safeStorageGet('kok_active_ch_v1') || '';
    if (explicit && /^[A-Za-z0-9_-]{2,32}$/.test(explicit)) {
      var normExplicit = explicit.toLowerCase();
      safeStorageSet('kok_active_ch_v1', normExplicit);
      return normExplicit;
    }
    var ref = '';
    try {
      ref = (root.document && root.document.referrer) ? String(root.document.referrer).toLowerCase() : '';
    } catch (e) {}
    var detected = 'direct';
    if (ref.indexOf('naver.') !== -1) detected = 'naver';
    else if (ref.indexOf('google.') !== -1) detected = 'google';
    else if (ref.indexOf('daum.') !== -1 || ref.indexOf('kakao.') !== -1) detected = 'daum_kakao';
    else if (ref.indexOf('clien.net') !== -1) detected = 'clien';
    else if (ref.indexOf('teamblind.com') !== -1) detected = 'blind';
    else if (ref.indexOf('ppomppu.co.kr') !== -1) detected = 'ppomppu';
    else if (ref.indexOf('disquiet.io') !== -1) detected = 'disquiet';
    else if (ref.indexOf('youtube.com') !== -1 || ref.indexOf('youtu.be') !== -1) detected = 'youtube';
    else if (ref.indexOf('threads.net') !== -1) detected = 'threads';
    else if (ref && ref.indexOf('tj-park8176.github.io') === -1) detected = 'referral_web';

    if (detected !== 'direct') {
      safeStorageSet('kok_active_ch_v1', detected);
    }
    return detected;
  }

  function isAutomationOrLocalEnv() {
    try {
      if (root.navigator && root.navigator.webdriver) return true;
      var proto = (root.location && root.location.protocol) ? String(root.location.protocol) : '';
      var host = (root.location && root.location.hostname) ? String(root.location.hostname) : '';
      if (proto === 'file:' || host === 'localhost' || host === '127.0.0.1') return true;
    } catch (e) {}
    return false;
  }

  function buildAttributedPlayUrl(pagePath, couponCode, channel) {
    var src = normalizePagePath(pagePath || resolvePagePath());
    var cp = couponCode || resolveCouponCode();
    var ch = channel || resolveSourceChannel();
    var referrerRaw = 'src=' + src + '&cp=' + cp + '&ch=' + ch;
    return PLAY_STORE_BASE + '&referrer=' + encodeURIComponent(referrerRaw);
  }

  function copyCouponSilently(couponCode) {
    if (!couponCode) return;
    try {
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        root.navigator.clipboard.writeText(couponCode).catch(function () {});
        return;
      }
      if (root.document && root.document.createElement && root.document.body) {
        var ta = root.document.createElement('textarea');
        ta.value = couponCode;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        root.document.body.appendChild(ta);
        if (ta.select) ta.select();
        if (root.document.execCommand) root.document.execCommand('copy');
        if (root.document.body.removeChild) root.document.body.removeChild(ta);
      }
    } catch (e) {}
  }

  function sendFunnelEvent(eventType, customPath, extraMeta) {
    var pagePath = normalizePagePath(customPath || resolvePagePath());
    var couponCode = resolveCouponCode();
    var channel = resolveSourceChannel();
    var dedupKey = eventType + '|' + pagePath;
    if (MEMORY_DEDUP[dedupKey] && eventType === 'page_view') {
      return Promise.resolve({ ok: true, deduped: true });
    }
    MEMORY_DEDUP[dedupKey] = Date.now();

    if (isAutomationOrLocalEnv()) {
      return Promise.resolve({ ok: true, skipped: 'local_or_webdriver' });
    }
    if (typeof root.fetch !== 'function') {
      return Promise.resolve({ ok: false, skipped: 'no_fetch' });
    }

    var payload = {
      p_event_type: eventType,
      p_page_path: pagePath,
      p_source_channel: extraMeta && extraMeta.channel ? String(extraMeta.channel) : channel,
      p_coupon_code: extraMeta && extraMeta.coupon ? String(extraMeta.coupon) : couponCode,
      p_anon_session_id: getOrCreateSessionId()
    };

    try {
      return root
        .fetch(SUPABASE_URL + '/rest/v1/rpc/log_web_funnel_event', {
          method: 'POST',
          headers: {
            apikey: SUPABASE_ANON_KEY,
            Authorization: 'Bearer ' + SUPABASE_ANON_KEY,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload),
          keepalive: true
        })
        .then(function (resp) {
          return { ok: resp && resp.ok };
        })
        .catch(function () {
          return { ok: false };
        });
    } catch (e) {
      return Promise.resolve({ ok: false });
    }
  }

  function applyAttributionToLinksAndCta() {
    var doc = root.document;
    if (!doc || !doc.querySelectorAll) return 0;

    var couponCode = resolveCouponCode();
    var channel = resolveSourceChannel();
    var pagePath = resolvePagePath();
    var attributedUrl = buildAttributedPlayUrl(pagePath, couponCode, channel);

    var updatedCount = 0;
    var anchors = doc.querySelectorAll('a[href*="play.google.com/store/apps/details"]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      if (!a || !a.setAttribute) continue;
      a.setAttribute('href', attributedUrl);
      a.setAttribute('data-kok-attributed', '1');
      if (!a.__kokStoreClickBound && a.addEventListener) {
        a.__kokStoreClickBound = true;
        a.addEventListener('click', function () {
          copyCouponSilently(couponCode);
          sendFunnelEvent('store_click', pagePath);
          sendFunnelEvent('coupon_copy', pagePath);
        });
      }
      updatedCount++;
    }

    var stickySub = doc.querySelector ? doc.querySelector('.sticky-sub') : null;
    if (stickySub && stickySub.textContent) {
      stickySub.textContent =
        'Google Play 설치 시 축원 쿠폰 [ ' +
        couponCode +
        ' ] +50,000P 자동 귀속 (클립보드 동시 복사)';
    }
    var codeBadges = doc.querySelectorAll ? doc.querySelectorAll('[data-kok-coupon-code], .coupon-code') : [];
    for (var j = 0; j < codeBadges.length; j++) {
      if (codeBadges[j]) codeBadges[j].textContent = couponCode;
    }

    return updatedCount;
  }

  function wrapCalculatorHooks() {
    if (typeof root.setLastSharePayload === 'function' && !root.setLastSharePayload.__kokWrapped) {
      var origSetPayload = root.setLastSharePayload;
      var wrappedSet = function (calcTitle, resultSummary, pagePath) {
        sendFunnelEvent('tool_use', pagePath || resolvePagePath());
        return origSetPayload.apply(this, arguments);
      };
      wrappedSet.__kokWrapped = true;
      root.setLastSharePayload = wrappedSet;
    }

    if (typeof root.shareCalcResult === 'function' && !root.shareCalcResult.__kokWrapped) {
      var origShare = root.shareCalcResult;
      var wrappedShare = function () {
        sendFunnelEvent('share_click', resolvePagePath());
        return origShare.apply(this, arguments);
      };
      wrappedShare.__kokWrapped = true;
      root.shareCalcResult = wrappedShare;
    }
  }

  function init() {
    applyAttributionToLinksAndCta();
    wrapCalculatorHooks();
    sendFunnelEvent('page_view', resolvePagePath());
  }

  root.KokFunnel = {
    init: init,
    applyAttributionToLinksAndCta: applyAttributionToLinksAndCta,
    buildAttributedPlayUrl: buildAttributedPlayUrl,
    resolveCouponCode: resolveCouponCode,
    resolveSourceChannel: resolveSourceChannel,
    resolvePagePath: resolvePagePath,
    trackToolUse: function (customPath) {
      return sendFunnelEvent('tool_use', customPath || resolvePagePath());
    },
    trackShare: function (customPath) {
      return sendFunnelEvent('share_click', customPath || resolvePagePath());
    },
    trackStoreClick: function (customPath) {
      copyCouponSilently(resolveCouponCode());
      return sendFunnelEvent('store_click', customPath || resolvePagePath());
    },
    trackEvent: sendFunnelEvent
  };

  if (root.document && root.document.addEventListener) {
    if (root.document.readyState === 'loading') {
      root.document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
