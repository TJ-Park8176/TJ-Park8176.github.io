/*
 * ************************************************************************
 * ** Code Description: 공덕왕 웹->앱 1st-Party 무쿠키 퍼널 텔레메트리 SDK **
 * **                   동적 DOM 전역 귀속, Android intent:// 직행 딥링크, **
 * **                   PC 방문자용 오프라인 SVG QR 코드 모달 브릿지       **
 * **                                                                    **
 * ** Creator: Origincs / Park.TJ                                        **
 * ** Creation Date: 2026.11.15 (개편: 2026.11.23)                       **
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
  var APP_PACKAGE_ID = 'com.taejoonlabs.kingofkarma';
  var PLAY_STORE_BASE = 'https://play.google.com/store/apps/details?id=' + APP_PACKAGE_ID;
  var MEMORY_DEDUP = Object.create(null);

  // ========================================================================
  // 1. 순수 오프라인 ISO/IEC 18004 QR 코드 SVG 인코더 (Version 1~12, ECC L)
  //    외부 API 의존 0%, PC 방문자 스마트폰 3초 스캔 설치용-2026.11.23
  // ========================================================================
  var QR_GF_EXP = new Array(512);
  var QR_GF_LOG = new Array(256);
  (function initQrGf() {
    var x = 1;
    for (var i = 0; i < 255; i++) {
      QR_GF_EXP[i] = x;
      QR_GF_LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;
    }
    for (var j = 255; j < 512; j++) {
      QR_GF_EXP[j] = QR_GF_EXP[j - 255];
    }
  })();

  function qrGfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return QR_GF_EXP[QR_GF_LOG[a] + QR_GF_LOG[b]];
  }

  function qrRsGenPoly(ecLen) {
    var poly = [1];
    for (var i = 0; i < ecLen; i++) {
      var next = new Array(poly.length + 1);
      for (var k = 0; k < next.length; k++) next[k] = 0;
      var rootVal = QR_GF_EXP[i];
      for (var j = 0; j < poly.length; j++) {
        next[j] ^= poly[j];
        next[j + 1] ^= qrGfMul(poly[j], rootVal);
      }
      poly = next;
    }
    return poly;
  }

  function qrRsCompute(data, ecLen) {
    var gen = qrRsGenPoly(ecLen);
    var res = new Array(ecLen);
    for (var i = 0; i < ecLen; i++) res[i] = 0;
    for (var d = 0; d < data.length; d++) {
      var factor = data[d] ^ res[0];
      res.shift();
      res.push(0);
      if (factor !== 0) {
        for (var j = 0; j < ecLen; j++) {
          res[j] ^= qrGfMul(gen[j + 1], factor);
        }
      }
    }
    return res;
  }

  // [totalDataCodewords, ecPerBlock, g1Blocks, g1Data, g2Blocks, g2Data, alignCenters]
  var QR_VERSIONS_L = [
    null,
    [19, 7, 1, 19, 0, 0, []],
    [34, 10, 1, 34, 0, 0, [6, 18]],
    [55, 15, 1, 55, 0, 0, [6, 22]],
    [80, 20, 1, 80, 0, 0, [6, 26]],
    [108, 26, 1, 108, 0, 0, [6, 30]],
    [136, 18, 2, 68, 0, 0, [6, 34]],
    [156, 20, 2, 78, 0, 0, [6, 22, 38]],
    [194, 24, 2, 97, 0, 0, [6, 24, 42]],
    [232, 30, 2, 116, 0, 0, [6, 26, 46]],
    [274, 18, 2, 68, 2, 69, [6, 28, 50]],
    [324, 20, 4, 81, 0, 0, [6, 30, 54]],
    [370, 24, 2, 92, 2, 93, [6, 32, 58]]
  ];

  function utf8Bytes(str) {
    var s = String(str || '');
    var out = [];
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c < 0x80) {
        out.push(c);
      } else if (c < 0x800) {
        out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
      } else if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
        var c2 = s.charCodeAt(++i);
        var cp = 0x10000 + (((c & 0x3ff) << 10) | (c2 & 0x3ff));
        out.push(
          0xf0 | (cp >> 18),
          0x80 | ((cp >> 12) & 0x3f),
          0x80 | ((cp >> 6) & 0x3f),
          0x80 | (cp & 0x3f)
        );
      } else {
        out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
      }
    }
    return out;
  }

  function qrBchFormat(ecBits2, mask3) {
    var data = (ecBits2 << 3) | mask3;
    var rem = data << 10;
    for (var bit = 14; bit >= 10; bit--) {
      if ((rem >> bit) & 1) rem ^= 0x537 << (bit - 10);
    }
    return ((data << 10) | rem) ^ 0x5412;
  }

  function qrBchVersion(ver) {
    var rem = ver << 12;
    for (var bit = 17; bit >= 12; bit--) {
      if ((rem >> bit) & 1) rem ^= 0x1f25 << (bit - 12);
    }
    return (ver << 12) | rem;
  }

  function encodeQrMatrix(text) {
    var bytes = utf8Bytes(text);
    var ver = 1;
    while (ver < QR_VERSIONS_L.length) {
      var countBits = ver < 10 ? 8 : 16;
      var neededBytes = Math.ceil((4 + countBits + bytes.length * 8) / 8);
      if (neededBytes <= QR_VERSIONS_L[ver][0]) break;
      ver++;
    }
    if (ver >= QR_VERSIONS_L.length) {
      ver = QR_VERSIONS_L.length - 1;
      bytes = bytes.slice(0, QR_VERSIONS_L[ver][0] - 3);
    }

    var spec = QR_VERSIONS_L[ver];
    var totalDataCw = spec[0];
    var ecPerBlock = spec[1];
    var g1Blocks = spec[2];
    var g1Data = spec[3];
    var g2Blocks = spec[4];
    var g2Data = spec[5];
    var aligns = spec[6];

    var bits = [];
    function pushBits(val, len) {
      for (var b = len - 1; b >= 0; b--) bits.push((val >> b) & 1);
    }
    pushBits(4, 4); // Byte mode
    pushBits(bytes.length, ver < 10 ? 8 : 16);
    for (var i = 0; i < bytes.length; i++) pushBits(bytes[i], 8);
    var maxBits = totalDataCw * 8;
    var term = Math.min(4, maxBits - bits.length);
    for (var t = 0; t < term; t++) bits.push(0);
    while (bits.length % 8 !== 0) bits.push(0);

    var dataCw = [];
    for (var p = 0; p < bits.length; p += 8) {
      var byteVal = 0;
      for (var q = 0; q < 8; q++) byteVal = (byteVal << 1) | bits[p + q];
      dataCw.push(byteVal);
    }
    var padToggle = 0;
    while (dataCw.length < totalDataCw) {
      dataCw.push(padToggle === 0 ? 0xec : 0x11);
      padToggle ^= 1;
    }

    var dataBlocks = [];
    var ecBlocks = [];
    var offset = 0;
    for (var b1 = 0; b1 < g1Blocks; b1++) {
      var slice1 = dataCw.slice(offset, offset + g1Data);
      offset += g1Data;
      dataBlocks.push(slice1);
      ecBlocks.push(qrRsCompute(slice1, ecPerBlock));
    }
    for (var b2 = 0; b2 < g2Blocks; b2++) {
      var slice2 = dataCw.slice(offset, offset + g2Data);
      offset += g2Data;
      dataBlocks.push(slice2);
      ecBlocks.push(qrRsCompute(slice2, ecPerBlock));
    }

    var interleaved = [];
    var maxDataLen = Math.max(g1Data, g2Data);
    for (var cIdx = 0; cIdx < maxDataLen; cIdx++) {
      for (var bl = 0; bl < dataBlocks.length; bl++) {
        if (cIdx < dataBlocks[bl].length) interleaved.push(dataBlocks[bl][cIdx]);
      }
    }
    for (var eIdx = 0; eIdx < ecPerBlock; eIdx++) {
      for (var eb = 0; eb < ecBlocks.length; eb++) {
        interleaved.push(ecBlocks[eb][eIdx]);
      }
    }

    var size = 17 + 4 * ver;
    var mat = new Array(size);
    var isFunc = new Array(size);
    for (var r = 0; r < size; r++) {
      mat[r] = new Array(size);
      isFunc[r] = new Array(size);
      for (var c = 0; c < size; c++) {
        mat[r][c] = 0;
        isFunc[r][c] = false;
      }
    }

    function setFn(row, col, dark) {
      if (row < 0 || row >= size || col < 0 || col >= size) return;
      mat[row][col] = dark ? 1 : 0;
      isFunc[row][col] = true;
    }

    function drawFinder(tr, tc) {
      for (var dr = -1; dr <= 7; dr++) {
        for (var dc = -1; dc <= 7; dc++) {
          var inBox = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6;
          var dark =
            inBox &&
            (dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4));
          setFn(tr + dr, tc + dc, dark);
        }
      }
    }
    drawFinder(0, 0);
    drawFinder(0, size - 7);
    drawFinder(size - 7, 0);

    for (var a1 = 0; a1 < aligns.length; a1++) {
      for (var a2 = 0; a2 < aligns.length; a2++) {
        var ar = aligns[a1];
        var ac = aligns[a2];
        if (isFunc[ar][ac]) continue;
        for (var dr2 = -2; dr2 <= 2; dr2++) {
          for (var dc2 = -2; dc2 <= 2; dc2++) {
            var adark = Math.max(Math.abs(dr2), Math.abs(dc2)) !== 1;
            setFn(ar + dr2, ac + dc2, adark);
          }
        }
      }
    }

    for (var ti = 8; ti < size - 8; ti++) {
      if (!isFunc[6][ti]) setFn(6, ti, ti % 2 === 0);
      if (!isFunc[ti][6]) setFn(ti, 6, ti % 2 === 0);
    }

    // Reserve format areas + dark module
    for (var f = 0; f < 9; f++) {
      if (f !== 6) {
        setFn(8, f, false);
        setFn(f, 8, false);
      }
    }
    for (var f2 = 0; f2 < 8; f2++) {
      setFn(8, size - 1 - f2, false);
      setFn(size - 1 - f2, 8, false);
    }
    setFn(size - 8, 8, true);

    if (ver >= 7) {
      var vBits = qrBchVersion(ver);
      for (var vi = 0; vi < 18; vi++) {
        var vDark = ((vBits >> vi) & 1) === 1;
        var vr = Math.floor(vi / 3);
        var vc = size - 11 + (vi % 3);
        setFn(vr, vc, vDark);
        setFn(vc, vr, vDark);
      }
    }

    // Zigzag data bit placement + Mask 0 ((row + col) % 2 === 0)
    var totalBits = interleaved.length * 8;
    var bitIdx = 0;
    var upward = true;
    for (var col = size - 1; col >= 1; col -= 2) {
      if (col === 6) col = 5;
      for (var step = 0; step < size; step++) {
        var row = upward ? size - 1 - step : step;
        for (var dx = 0; dx < 2; dx++) {
          var cc = col - dx;
          if (isFunc[row][cc]) continue;
          var bitVal = 0;
          if (bitIdx < totalBits) {
            bitVal = (interleaved[bitIdx >> 3] >> (7 - (bitIdx & 7))) & 1;
          }
          bitIdx++;
          if ((row + cc) % 2 === 0) bitVal ^= 1;
          mat[row][cc] = bitVal;
        }
      }
      upward = !upward;
    }

    // Write format info (EC Level L = 01, Mask = 000 -> 0x77C4)
    var fmt = qrBchFormat(1, 0);
    for (var fi = 0; fi <= 5; fi++) setFn(8, fi, ((fmt >> (14 - fi)) & 1) === 1);
    setFn(8, 7, ((fmt >> 8) & 1) === 1);
    setFn(8, 8, ((fmt >> 7) & 1) === 1);
    setFn(7, 8, ((fmt >> 6) & 1) === 1);
    for (var fj = 0; fj <= 5; fj++) setFn(5 - fj, 8, ((fmt >> (5 - fj)) & 1) === 1);

    for (var fk = 0; fk < 7; fk++) setFn(size - 1 - fk, 8, ((fmt >> (14 - fk)) & 1) === 1);
    for (var fm = 0; fm < 8; fm++) setFn(8, size - 8 + fm, ((fmt >> (7 - fm)) & 1) === 1);

    return { version: ver, size: size, matrix: mat };
  }

  function buildQrSvg(text, pxSize) {
    var qr = encodeQrMatrix(text);
    var quiet = 4;
    var full = qr.size + quiet * 2;
    var dispSize = pxSize || 196;
    var parts = [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + full + ' ' + full + '" width="' + dispSize + '" height="' + dispSize + '" role="img" aria-label="Google Play 앱 설치 QR 코드" style="display:block;border-radius:14px;background:#FFFFFF;">',
      '<rect width="' + full + '" height="' + full + '" fill="#FFFFFF"/>'
    ];
    for (var r = 0; r < qr.size; r++) {
      var row = qr.matrix[r];
      var runStart = -1;
      for (var c = 0; c <= qr.size; c++) {
        var dark = c < qr.size && row[c] === 1;
        if (dark && runStart === -1) {
          runStart = c;
        } else if (!dark && runStart !== -1) {
          parts.push(
            '<rect x="' + (runStart + quiet) + '" y="' + (r + quiet) + '" width="' + (c - runStart) + '" height="1" fill="#0B0D13"/>'
          );
          runStart = -1;
        }
      }
    }
    parts.push('</svg>');
    return parts.join('');
  }

  // ========================================================================
  // 2. 세션·경로·채널·쿠폰 식별 및 귀속 URL / Android Intent 빌더
  // ========================================================================
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
    else if (ref.indexOf('youtube.com') !== -1 || ref.indexOf('youtu.be') !== -1) detected = 'youtube';
    else if (ref.indexOf('threads.net') !== -1) detected = 'threads';
    else if (
      ref &&
      ref.indexOf('karma.taejoonlabs.com') === -1 &&
      ref.indexOf('tj-park8176.github.io') === -1
    ) {
      detected = 'referral_web';
    }

    if (detected !== 'direct') {
      safeStorageSet('kok_active_ch_v1', detected);
    }
    return detected;
  }

  function getUserAgent() {
    try {
      return (root.navigator && root.navigator.userAgent) ? String(root.navigator.userAgent) : '';
    } catch (e) {
      return '';
    }
  }

  function isAndroidMobile() {
    return /Android/i.test(getUserAgent());
  }

  function isMobileDevice() {
    return /Android|iPhone|iPad|iPod|Mobile/i.test(getUserAgent());
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

  function buildReferrerParam(pagePath, couponCode, channel) {
    var src = normalizePagePath(pagePath || resolvePagePath());
    var cp = couponCode || resolveCouponCode();
    var ch = channel || resolveSourceChannel();
    return 'src=' + src + '&cp=' + cp + '&ch=' + ch;
  }

  function buildAttributedPlayUrl(pagePath, couponCode, channel) {
    var referrerRaw = buildReferrerParam(pagePath, couponCode, channel);
    return PLAY_STORE_BASE + '&referrer=' + encodeURIComponent(referrerRaw);
  }

  // Android 네이버/카카오 인앱 브라우저 웹 로그인 벽 우회용 Play 스토어 앱 직행 Intent 딥링크-2026.11.23
  function buildAndroidIntentUrl(pagePath, couponCode, channel) {
    var referrerRaw = buildReferrerParam(pagePath, couponCode, channel);
    var httpsFallback = buildAttributedPlayUrl(pagePath, couponCode, channel);
    return (
      'intent://details?id=' +
      APP_PACKAGE_ID +
      '&referrer=' +
      encodeURIComponent(referrerRaw) +
      '#Intent;scheme=market;package=com.android.vending;S.browser_fallback_url=' +
      encodeURIComponent(httpsFallback) +
      ';end'
    );
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

  // ========================================================================
  // 3. PC 방문자용 시안 B 무테두리 다크 QR 코드 설치 모달-2026.11.23
  // ========================================================================
  function closeQrInstallModal() {
    var doc = root.document;
    if (!doc || !doc.getElementById) return;
    var modal = doc.getElementById('kok-qr-install-modal');
    if (modal && modal.style) {
      modal.style.display = 'none';
    }
  }

  function openQrInstallModal(playUrl, couponCode) {
    var doc = root.document;
    if (!doc || !doc.createElement || !doc.body) return false;
    var url = playUrl || buildAttributedPlayUrl();
    var cp = couponCode || resolveCouponCode();
    var modal = doc.getElementById ? doc.getElementById('kok-qr-install-modal') : null;
    if (!modal) {
      modal = doc.createElement('div');
      modal.id = 'kok-qr-install-modal';
      modal.style.cssText =
        'position:fixed;inset:0;z-index:9999;background:rgba(5,7,11,0.84);backdrop-filter:blur(10px);' +
        'display:flex;align-items:center;justify-content:center;padding:20px;';
      if (modal.addEventListener) {
        modal.addEventListener('click', function (ev) {
          if (ev && ev.target === modal) closeQrInstallModal();
        });
      }
      doc.body.appendChild(modal);
    }

    var qrSvg = buildQrSvg(url, 196);
    modal.innerHTML =
      '<div style="background:#171B26;border-radius:26px;padding:28px 24px;max-width:420px;width:100%;' +
      'text-align:center;color:#F4F6FA;box-shadow:0 24px 64px rgba(0,0,0,0.68);font-family:Pretendard,sans-serif;">' +
      '<div style="display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;' +
      'background:rgba(46,242,160,0.14);color:#2EF2A0;font-size:12.5px;font-weight:800;margin-bottom:14px;">' +
      '<span style="width:8px;height:8px;border-radius:50%;background:#2EF2A0;display:inline-block;"></span>' +
      '스마트폰 카메라 3초 스캔 설치</div>' +
      '<h3 style="margin:0 0 8px 0;font-size:20px;font-weight:800;color:#F4F6FA;line-height:1.35;">' +
      '휴대폰 카메라로 QR을 비추면<br/>+50,000P 쿠폰과 함께 바로 열립니다</h3>' +
      '<p style="margin:0 0 18px 0;font-size:13.5px;color:#949EB0;line-height:1.55;">' +
      '설치 직후 축원 쿠폰 <strong style="color:#FFD666;">' + cp + '</strong> 이 자동 귀속됩니다 (클립보드 복사 완료)</p>' +
      '<div id="kok-qr-svg-holder" style="display:inline-flex;padding:12px;background:#FFFFFF;border-radius:18px;margin-bottom:18px;">' +
      qrSvg +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:10px;">' +
      '<a href="' + url + '" target="_blank" rel="noopener" data-kok-direct-web="1" ' +
      'style="display:block;background:#2EF2A0;color:#0B0D13;font-weight:800;font-size:14.5px;padding:13px 18px;border-radius:14px;text-decoration:none;">' +
      'PC 웹 브라우저에서 Google Play 열기</a>' +
      '<button type="button" id="kok-qr-close-btn" ' +
      'style="background:#1E2330;color:#949EB0;border:none;font-weight:700;font-size:13.5px;padding:11px 16px;border-radius:14px;cursor:pointer;">닫기</button>' +
      '</div></div>';
    modal.style.display = 'flex';
    var closeBtn = doc.getElementById ? doc.getElementById('kok-qr-close-btn') : null;
    if (closeBtn && closeBtn.addEventListener) {
      closeBtn.addEventListener('click', closeQrInstallModal);
    }
    return true;
  }

  // ========================================================================
  // 4. 전역 클릭 위임 + 동적 DOM 감시로 계산기 결과창 버튼까지 100% 귀속
  // ========================================================================
  function isPlayStoreAnchor(el) {
    if (!el || !el.getAttribute) return false;
    var href = String(el.getAttribute('href') || '');
    return (
      href.indexOf('play.google.com/store/apps/details') !== -1 ||
      href.indexOf('intent://details?id=' + APP_PACKAGE_ID) !== -1
    );
  }

  function findClosestPlayAnchor(target) {
    var cur = target;
    var depth = 0;
    while (cur && depth < 8) {
      if (isPlayStoreAnchor(cur)) return cur;
      cur = cur.parentNode || cur.parentElement || null;
      depth++;
    }
    return null;
  }

  function applyAttributionToLinksAndCta() {
    var doc = root.document;
    if (!doc || !doc.querySelectorAll) return 0;

    var couponCode = resolveCouponCode();
    var channel = resolveSourceChannel();
    var pagePath = resolvePagePath();
    var attributedUrl = buildAttributedPlayUrl(pagePath, couponCode, channel);
    var androidMode = isAndroidMobile();
    var targetHref = androidMode ? buildAndroidIntentUrl(pagePath, couponCode, channel) : attributedUrl;

    var updatedCount = 0;
    var anchors = doc.querySelectorAll('a[href*="play.google.com/store/apps/details"], a[href*="intent://details"]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      if (!a || !a.setAttribute) continue;
      if (a.getAttribute && a.getAttribute('data-kok-direct-web') === '1') continue;
      if (a.getAttribute('href') !== targetHref) {
        a.setAttribute('href', targetHref);
      }
      a.setAttribute('data-kok-attributed', '1');
      a.setAttribute('data-kok-https-url', attributedUrl);
      if (androidMode) {
        a.removeAttribute && a.removeAttribute('target');
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

  function bindGlobalDelegatedClick() {
    var doc = root.document;
    if (!doc || !doc.addEventListener || doc.__kokGlobalClickBound) return;
    doc.__kokGlobalClickBound = true;

    doc.addEventListener(
      'click',
      function (ev) {
        var anchor = findClosestPlayAnchor(ev && ev.target);
        if (!anchor) return;

        var couponCode = resolveCouponCode();
        var channel = resolveSourceChannel();
        var pagePath = resolvePagePath();
        var attributedUrl = buildAttributedPlayUrl(pagePath, couponCode, channel);
        var isDirectWebInsideModal = anchor.getAttribute && anchor.getAttribute('data-kok-direct-web') === '1';

        // 동적 생성된 링크 포함 모든 Play 스토어 버튼의 href를 클릭 직전 최신 귀속 URL로 보정-2026.11.23
        if (!isDirectWebInsideModal) {
          copyCouponSilently(couponCode);
          sendFunnelEvent('store_click', pagePath);
          sendFunnelEvent('coupon_copy', pagePath);
        }

        if (isAndroidMobile()) {
          var intentHref = buildAndroidIntentUrl(pagePath, couponCode, channel);
          if (anchor.setAttribute) anchor.setAttribute('href', intentHref);
          if (anchor.removeAttribute) anchor.removeAttribute('target');
          return;
        }

        if (anchor.setAttribute) anchor.setAttribute('href', attributedUrl);

        // PC 데스크톱 방문자는 3초 스캔 QR 모달 제공 (모달 내부 직행 버튼 클릭은 그대로 웹 이동)
        if (!isMobileDevice() && !isDirectWebInsideModal) {
          if (ev && typeof ev.preventDefault === 'function') {
            ev.preventDefault();
          }
          openQrInstallModal(attributedUrl, couponCode);
        }
      },
      true
    );
  }

  function observeDynamicCtaMutations() {
    var doc = root.document;
    if (!doc || !doc.body || typeof root.MutationObserver !== 'function' || doc.__kokObserverBound) return;
    doc.__kokObserverBound = true;
    var scheduled = false;
    var obs = new root.MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      var run = function () {
        scheduled = false;
        applyAttributionToLinksAndCta();
      };
      if (typeof root.setTimeout === 'function') {
        root.setTimeout(run, 30);
      } else {
        run();
      }
    });
    try {
      obs.observe(doc.body, { childList: true, subtree: true });
    } catch (e) {}
  }

  function wrapCalculatorHooks() {
    if (typeof root.setLastSharePayload === 'function' && !root.setLastSharePayload.__kokWrapped) {
      var origSetPayload = root.setLastSharePayload;
      var wrappedSet = function (calcTitle, resultSummary, pagePath) {
        sendFunnelEvent('tool_use', pagePath || resolvePagePath());
        var ret = origSetPayload.apply(this, arguments);
        if (typeof root.setTimeout === 'function') {
          root.setTimeout(applyAttributionToLinksAndCta, 10);
        } else {
          applyAttributionToLinksAndCta();
        }
        return ret;
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
    bindGlobalDelegatedClick();
    applyAttributionToLinksAndCta();
    observeDynamicCtaMutations();
    wrapCalculatorHooks();
    sendFunnelEvent('page_view', resolvePagePath());
  }

  root.KokFunnel = {
    init: init,
    applyAttributionToLinksAndCta: applyAttributionToLinksAndCta,
    buildAttributedPlayUrl: buildAttributedPlayUrl,
    buildAndroidIntentUrl: buildAndroidIntentUrl,
    buildQrSvg: buildQrSvg,
    encodeQrMatrix: encodeQrMatrix,
    openQrInstallModal: openQrInstallModal,
    closeQrInstallModal: closeQrInstallModal,
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
