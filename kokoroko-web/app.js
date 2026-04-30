(function () {
  const K = window.KokorokoApi;
  if (!K) {
    console.error("KokorokoApi missing — include api.js before app.js");
  }
  const TAB_IDS = ["home", "promotion", "wallet", "profile"];
  const ALL_SCREENS = [...TAB_IDS, "cockfight", "gundu", "login", "register", "transactions", "referral"];
  const NAV_HASHES = ALL_SCREENS;
  let lastWalletData = null;
  let cockfightLiveBound = false;
  let cockfightMaxTime = 0;
  let cockfightDialogOpen = false;
  let cfCountdownInterval = null;
  let cfVideoUrls = null;
  let cfCurrentQuality = -1;      // -1 = auto ABR; 0,1,2... = specific hls.js level index
  let cfPreloadUrl = null;
  let cfPreloadPollTimer = null;
  let cfHlsInstance = null;       // hls.js instance for main #cockfight-video
  let cfHlsFsInstance = null;     // hls.js instance for #cockfight-video-fs (fullscreen)
  let lastBankWithdraw = { upi: "", bankAcc: "", bankIfsc: "" };

  function balanceNumOnly(s) {
    if (!K) return s == null ? "—" : String(s);
    return K.formatRupeeBalanceForDisplay(s).replace(/^₹\s?/, "");
  }
  function setBalanceDisplays(mainBal, wdrBal) {
    const hb = document.getElementById("header-balance");
    const wWithdraw = document.getElementById("wallet-withdrawable-balance");
    const cfbal = document.getElementById("cockfight-balance");
    const gbal = document.getElementById("gundu-balance");
    if (mainBal !== undefined && hb) {
      if (mainBal === "—") hb.textContent = "—";
      else hb.textContent = balanceNumOnly(mainBal);
    }
    if (wdrBal !== undefined && wWithdraw) wWithdraw.textContent = wdrBal === "—" ? "—" : K ? K.formatRupeeBalanceForDisplay(wdrBal) : wdrBal;
    if (mainBal !== undefined && cfbal) cfbal.textContent = mainBal === "—" ? "—" : K ? K.formatRupeeBalanceForDisplay(mainBal) : mainBal;
    if (mainBal !== undefined && gbal) gbal.textContent = mainBal === "—" ? "—" : K ? K.formatRupeeBalanceForDisplay(mainBal) : mainBal;
  }
  function refreshHeaderAuth() {
    const authPills = document.getElementById("header-auth-pills");
    const wall = document.getElementById("header-wallet-pill");
    const bottomNavWallet = document.getElementById("bottom-nav-wallet");
    const authed = !!(K && K.isAuthed());
    /* Header + bottom nav wallet only for a real server session, not unauthenticated or local demo (svs/svs). */
    const showWalletPill = authed && K && !K.isLocalDemo();
    if (authPills) authPills.hidden = showWalletPill;
    if (wall) wall.hidden = !showWalletPill;
    if (bottomNavWallet) bottomNavWallet.hidden = !showWalletPill;
    document.documentElement.dataset.auth = authed ? "1" : "0";
    document.documentElement.dataset.headerWallet = showWalletPill ? "1" : "0";
  }
  async function refreshAllBalances() {
    refreshHeaderAuth();
    if (!K) return;
    if (!K.isAuthed() || K.isLocalDemo()) {
      if (K.isAuthed() && K.isLocalDemo()) setBalanceDisplays("0", "0");
      else {
        setBalanceDisplays("—", "—");
        refreshHeaderAuth();
      }
      return;
    }
    const { data, error } = await K.fetchWallet();
    if (error) {
      setBalanceDisplays("—", "—");
      return;
    }
    lastWalletData = data;
    const b = (data && data.balance) || "0";
    const w = (data && (data.withdrawableBalance || data.balance)) || b;
    setBalanceDisplays(b, w);
  }
  async function loadWalletFromApi() {
    if (!K || !K.isAuthed() || K.isLocalDemo()) {
      if (K && K.isAuthed() && K.isLocalDemo()) {
        const wEl = document.getElementById("wallet-withdrawable-balance");
        if (wEl) wEl.textContent = "₹0.00";
      }
      return;
    }
    let { data } = await K.fetchWallet();
    if (!data) {
      const r2 = await K.fetchPaymentMethodsOnly();
      if (r2.data) data = r2.data;
    }
    if (data) {
      lastWalletData = data;
      const w = data.withdrawableBalance || data.balance || "0";
      const b = data.balance || "0";
      setBalanceDisplays(b, w);
    }
    const bdet = await K.fetchBankDetails();
    if (bdet && bdet.data) {
      const u = bdet.data.upiId || "";
      const b = bdet.data.bank;
      lastBankWithdraw.upi = u;
      if (b) {
        lastBankWithdraw.bankAcc = b.accountNumber || "";
        lastBankWithdraw.bankIfsc = b.ifsc || "";
        const t = document.getElementById("wallet-saved-bank");
        if (t) t.textContent = b.accountNumber ? b.bankName + " · · · " + b.accountNumber.slice(-4) : t.textContent;
      }
      const uEl = document.getElementById("wallet-saved-upi");
      if (uEl && u) uEl.textContent = u;
    }
  }
  function pickPaymentMethodId() {
    const m = lastWalletData && lastWalletData.paymentMethods;
    if (!m || !m.length) return 1;
    for (const x of m) {
      if (x.id > 0) return x.id;
    }
    return m[0].id || 1;
  }
  /** #cockfight only: local MP4 (assets/cockfight_live_stream.mp4) — no HLS, no controls, no forward seek, no pause. */
  /**
   * Silently buffer `url` using the REAL #cockfight-video element.
   * Mobile browsers ignore preload on hidden/off-screen elements;
   * they only buffer the visible video. The countdown overlay sits on
   * top so the user never sees the unstarted video frame underneath.
   */
  /** Destroy a hls.js instance safely. */
  function destroyCfHls(instance) {
    if (instance) { try { instance.destroy(); } catch {} }
  }

  /**
   * Attach an HLS stream to a video element.
   * iOS/macOS Safari support HLS natively; all other browsers need hls.js.
   * Returns the new Hls instance (or null for native).
   */
  function attachHls(video, url, { maxBuffer = 120, onReady, onError } = {}) {
    // Native HLS (Safari)
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
      video.setAttribute("data-cf-src", url);
      if (onReady) video.addEventListener("loadedmetadata", onReady, { once: true });
      return null;
    }
    // hls.js for Chrome / Firefox / Android
    if (!window.Hls || !Hls.isSupported()) {
      // Fallback: try setting src directly (may not work, but better than nothing)
      video.src = url;
      video.setAttribute("data-cf-src", url);
      if (onReady) video.addEventListener("loadedmetadata", onReady, { once: true });
      return null;
    }
    const hls = new Hls({
      maxBufferLength: maxBuffer,
      maxMaxBufferLength: maxBuffer * 2,
      autoStartLoad: true,
      startFragPrefetch: true,
      lowLatencyMode: false,
    });
    hls.loadSource(url);
    hls.attachMedia(video);
    video.setAttribute("data-cf-src", url);
    if (onReady) {
      // Use video's loadedmetadata (not MANIFEST_PARSED) so that video.duration
      // is guaranteed to be set before startSynced tries to seek.
      // hls.js triggers all standard HTML5 video events on the attached element.
      video.addEventListener("loadedmetadata", onReady, { once: true });
    }
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (!data.fatal) return;
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        hls.startLoad();
      } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        hls.recoverMediaError();
      } else {
        if (onError) onError(data);
      }
    });
    return hls;
  }

  /** Canonical sides COCK1, COCK2, DRAW (+ COMPLETED overlays). Normalize MERON/WALA/aliases at JSON boundary. */
  function canonicalCockfightSide(raw) {
    const u = String(raw ?? "").trim().toUpperCase();
    if (!u) return "";
    if (["COCK1", "MERON", "RED", "M"].includes(u)) return "COCK1";
    if (["COCK2", "WALA", "BLUE", "W"].includes(u)) return "COCK2";
    if (u === "DRAW" || u === "D") return "DRAW";
    if (u === "COMPLETED") return "COMPLETED";
    return String(raw).trim();
  }

  function displayCockfightSide(canonical) {
    switch (canonical) {
      case "COCK1": return "Cock 1";
      case "COCK2": return "Cock 2";
      case "DRAW": return "Draw";
      default: return String(canonical);
    }
  }

  /** Merged COCK1/COCK2 display names from `/info` (`side_labels`; video overrides root).
   *  Legacy API strings "Meron"/"Wala" are normalized to Cock 1 / Cock 2 for UI. */
  let cfMergedSideLabels = { COCK1: "Cock 1", COCK2: "Cock 2" };

  function sanitizeCfSideLabels(merged) {
    const norm = (s) =>
      String(s ?? "")
        .normalize("NFKC")
        .replace(/[\u200B-\u200D\uFEFF]/g, "")
        .replace(/\s+/g, " ")
        .trim();
    let c1 = norm(merged.COCK1);
    let c2 = norm(merged.COCK2);
    if (!c1) c1 = "Cock 1";
    if (!c2) c2 = "Cock 2";
    if (/^meron$/i.test(c1)) c1 = "Cock 1";
    if (/^wala$/i.test(c2)) c2 = "Cock 2";
    return { COCK1: c1, COCK2: c2 };
  }

  function mergeCockfightSideLabels(info) {
    const def = { COCK1: "Cock 1", COCK2: "Cock 2" };
    if (!info || typeof info !== "object") return sanitizeCfSideLabels(cfMergedSideLabels);
    const vid = info.latest_round_video && info.latest_round_video.side_labels;
    const root = info.side_labels;
    return sanitizeCfSideLabels({
      COCK1:
        (vid && vid.COCK1) ??
        (root && root.COCK1) ??
        def.COCK1,
      COCK2:
        (vid && vid.COCK2) ??
        (root && root.COCK2) ??
        def.COCK2,
    });
  }

  /** Merge root `odds` with optional `latest_round_video.odds` (per-field). */
  function effectiveCockfightOdds(info) {
    const dash = "\u2014";
    const root = (info && info.odds) || {};
    const lv = info && info.latest_round_video && info.latest_round_video.odds;
    function norm(v) {
      const s = v != null ? String(v).trim() : "";
      return s !== "" && s !== dash ? s : "";
    }
    function cell(rv, dv) {
      const a = norm(rv);
      const b = norm(dv);
      return a || b || dash;
    }
    if (lv && typeof lv === "object") {
      return {
        COCK1: cell(lv.COCK1, root.COCK1),
        COCK2: cell(lv.COCK2, root.COCK2),
        DRAW: cell(lv.DRAW, root.DRAW),
      };
    }
    return {
      COCK1: norm(root.COCK1) || dash,
      COCK2: norm(root.COCK2) || dash,
      DRAW: norm(root.DRAW) || dash,
    };
  }

  /** VS strip + bet cards: same merged `side_labels` from `/info` (custom names e.g. Red / Black). */
  function applyCockfightSideLabels(info) {
    cfMergedSideLabels = mergeCockfightSideLabels(info);
    const c1 = cfMergedSideLabels.COCK1;
    const c2 = cfMergedSideLabels.COCK2;
    document.querySelectorAll("[data-cf-vs]").forEach((el) => {
      const k = el.getAttribute("data-cf-vs");
      if (k === "COCK1") el.textContent = c1;
      if (k === "COCK2") el.textContent = c2;
    });
    const odds = effectiveCockfightOdds(info || {});
    ["cockfight-side-bar", "cockfight-fs-side-bar"].forEach((barId) => {
      const bar = document.getElementById(barId);
      if (!bar) return;
      bar.querySelectorAll("[data-cf-side]").forEach((btn) => {
        const key = btn.getAttribute("data-cf-side");
        if (key === "COCK1" || key === "Meron") {
          btn.setAttribute("data-cf-display", c1);
          const lab = btn.querySelector(".cockfight-side-btn__lab");
          if (lab) lab.textContent = c1;
          btn.setAttribute("data-cf-odd", odds.COCK1);
          const oddEl = btn.querySelector(".cockfight-side-btn__odd");
          if (oddEl) oddEl.textContent = odds.COCK1 + "\u00d7";
        } else if (key === "COCK2" || key === "Wala") {
          btn.setAttribute("data-cf-display", c2);
          const lab = btn.querySelector(".cockfight-side-btn__lab");
          if (lab) lab.textContent = c2;
          btn.setAttribute("data-cf-odd", odds.COCK2);
          const oddEl = btn.querySelector(".cockfight-side-btn__odd");
          if (oddEl) oddEl.textContent = odds.COCK2 + "\u00d7";
        } else if (key === "DRAW" || key === "Draw") {
          btn.setAttribute("data-cf-odd", odds.DRAW);
          const oddEl = btn.querySelector(".cockfight-side-btn__odd");
          if (oddEl) oddEl.textContent = odds.DRAW + "\u00d7";
        }
      });
    });
  }

  /** Prefer API `side_label`; legacy Meron/Wala → Cock 1/Cock 2; else merged names. */
  function cockfightBetSideDisplay(row) {
    const raw = row && typeof row.side_label === "string" && row.side_label.trim();
    if (raw) {
      if (/^meron$/i.test(raw)) return "Cock 1";
      if (/^wala$/i.test(raw)) return "Cock 2";
      return raw;
    }
    const c = canonicalCockfightSide(row && row.side);
    if (c === "COCK1") return cfMergedSideLabels.COCK1 || "Cock 1";
    if (c === "COCK2") return cfMergedSideLabels.COCK2 || "Cock 2";
    return displayCockfightSide(c);
  }

  function startCockfightPreload(url) {
    if (cfPreloadUrl === url) return;
    cfPreloadUrl = url;
    const video = document.getElementById("cockfight-video");
    if (!video) return;
    video.muted = true;
    video.preload = "auto";
    // Create HLS player in buffering mode — play() silently to trigger downloading.
    // Countdown overlay sits on top; user sees nothing. Audio is muted.
    destroyCfHls(cfHlsInstance);
    cfHlsInstance = attachHls(video, url, {
      maxBuffer: 120,
      onReady: () => { video.play().catch(() => {}); },
    });
  }

  /** Cancel the preload poll timer (video element stays buffered — don't touch it). */
  function stopCockfightPreload() {
    if (cfPreloadPollTimer) { clearInterval(cfPreloadPollTimer); cfPreloadPollTimer = null; }
    // cfPreloadUrl stays set so countdown callback knows what URL was buffered
  }

  /**
   * Wait until `targetSecs` seconds are buffered ahead of currentTime,
   * then call `callback`. Falls back after `timeoutMs` so playback
   * never gets stuck if the network is too slow.
   */
  function waitForBuffer(video, targetSecs, timeoutMs, callback) {
    const getAhead = () => {
      const ct = video.currentTime;
      for (let i = 0; i < video.buffered.length; i++) {
        if (video.buffered.start(i) <= ct + 0.5 && video.buffered.end(i) > ct) {
          return video.buffered.end(i) - ct;
        }
      }
      return 0;
    };
    const dur = video.duration;
    const remaining = isFinite(dur) ? Math.max(0, dur - video.currentTime) : Infinity;
    const need = Math.min(targetSecs, remaining);

    if (getAhead() >= need || need <= 0) { callback(); return; }

    let fired = false;
    const fire = () => {
      if (fired) return;
      fired = true;
      video.removeEventListener("progress", onProgress);
      callback();
    };
    const onProgress = () => { if (getAhead() >= need) fire(); };
    video.addEventListener("progress", onProgress);
    setTimeout(fire, timeoutMs); // Fallback — play regardless after timeout
  }

  async function setupCockfightLiveStream() {
    const video = document.getElementById("cockfight-video");
    if (!video) return;

    const info = await K.fetchMeronWalaInfo();
    if (info) applyCockfightSideLabels(info);
    const lv = info?.latest_round_video;

    // Use server_time for all time calculations to correct device clock skew.
    // clockSkew = how much the device clock is ahead of the server clock.
    const fetchedAt = Date.now();
    const serverMs = lv?.server_time ? new Date(lv.server_time).getTime() : fetchedAt;
    const clockSkew = serverMs - fetchedAt; // e.g. +5000 = device is 5s behind server
    // serverNow() returns the current time in server's reference frame
    const serverNow = () => Date.now() + clockSkew;

    const startMs = lv?.start ? new Date(lv.start).getTime() : null;
    const nowMs = serverNow();

    // ── Step 1: If start time is in the future, show countdown and preload video ──
    if (startMs && startMs > nowMs) {
      hideCockfightVideoOverlay();

      if (lv.hls_url) {
        startCockfightPreload(lv.hls_url);
      } else if (!lv.requires_authentication) {
        // URL not yet available — poll API every 20 s until server releases it
        cfPreloadPollTimer = setInterval(async () => {
          try {
            const fresh = await K.fetchMeronWalaInfo();
            if (fresh) applyCockfightSideLabels(fresh);
            const freshLv = fresh?.latest_round_video;
            if (freshLv?.hls_url) {
              clearInterval(cfPreloadPollTimer);
              cfPreloadPollTimer = null;
              startCockfightPreload(freshLv.hls_url);
            }
          } catch {}
        }, 20_000);
      }

      // Pass clockSkew so countdown uses server time, not device time
      startCockfightCountdown(startMs, clockSkew, async () => {
        hideCockfightCountdown();
        const playUrl = cfPreloadUrl;
        stopCockfightPreload();
        if (playUrl) {
          loadAndPlayCockfightVideo(video, playUrl, 0, 60);
        } else {
          pollForCockfightUrl(video, 0);
        }
      });
      return;
    }

    // ── Step 2: Start time already past or no start time — check URL now ──
    if (!info.open && info.last_result?.winner) {
      showWinnerOverlay(info.last_result.winner);
      return;
    }
    if (!lv) {
      showCockfightVideoOverlay("unavailable");
      return;
    }
    if (lv.requires_authentication && !lv.hls_url) {
      showCockfightVideoOverlay("login");
      return;
    }
    if (!lv.hls_url) {
      if (startMs) {
        pollForCockfightUrl(video, Math.floor((nowMs - startMs) / 1000));
      } else {
        showCockfightVideoOverlay("unavailable");
      }
      return;
    }

    hideCockfightVideoOverlay();

    // elapsed = seconds since match started, corrected for clock skew
    if (startMs) {
      const elapsed = Math.floor((nowMs - startMs) / 1000);
      hideCockfightCountdown();
      loadAndPlayCockfightVideo(video, lv.hls_url, elapsed);
    } else {
      hideCockfightCountdown();
      loadAndPlayCockfightVideo(video, lv.hls_url, 0);
    }
  }

  /** Populate quality picker from hls.js levels. Called after MANIFEST_PARSED. */
  function setupQualityPickerFromHls(levels) {
    if (!levels || levels.length < 2) {
      ["cf-quality-wrap", "cf-quality-wrap-fs"].forEach(id => {
        const w = document.getElementById(id);
        if (w) w.hidden = true;
      });
      return;
    }

    ["cf-quality-wrap", "cf-quality-wrap-fs"].forEach(id => {
      const wrap = document.getElementById(id);
      if (wrap) wrap.hidden = false;
    });

    const labelFor = (idx) => {
      if (idx === -1) return "Auto";
      const l = levels[idx];
      return l ? (l.height ? l.height + "p" : "Level " + idx) : "Auto";
    };

    [
      { menuId: "cf-quality-menu",    btnId: "cf-quality-btn",    labelId: "cf-quality-label"    },
      { menuId: "cf-quality-menu-fs", btnId: "cf-quality-btn-fs", labelId: "cf-quality-label-fs" }
    ].forEach(({ menuId, btnId, labelId }) => {
      const menu  = document.getElementById(menuId);
      const btn   = document.getElementById(btnId);
      const label = document.getElementById(labelId);
      if (!menu || !btn) return;

      menu.innerHTML = "";
      // Auto option
      const autoOpt = document.createElement("button");
      autoOpt.className = "cf-quality__opt" + (cfCurrentQuality === -1 ? " is-active" : "");
      autoOpt.dataset.q = "-1";
      autoOpt.role = "menuitem";
      autoOpt.textContent = "Auto";
      menu.appendChild(autoOpt);
      // Per-level options (highest quality first)
      [...levels].reverse().forEach((lvl, ri) => {
        const idx = levels.length - 1 - ri;
        const opt = document.createElement("button");
        opt.className = "cf-quality__opt" + (cfCurrentQuality === idx ? " is-active" : "");
        opt.dataset.q = String(idx);
        opt.role = "menuitem";
        opt.textContent = lvl.height ? lvl.height + "p" : "Level " + idx;
        menu.appendChild(opt);
      });

      if (label) label.textContent = labelFor(cfCurrentQuality);

      btn.onclick = (e) => {
        e.stopPropagation();
        const open = !menu.hidden;
        menu.hidden = open;
        btn.setAttribute("aria-expanded", String(!open));
      };
      menu.onclick = (e) => {
        const opt = e.target.closest(".cf-quality__opt");
        if (!opt) return;
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
        switchQuality(Number(opt.dataset.q));
      };
    });

    document.addEventListener("click", () => {
      document.querySelectorAll(".cf-quality__menu").forEach(m => { m.hidden = true; });
      document.querySelectorAll(".cf-quality__btn").forEach(b => b.setAttribute("aria-expanded", "false"));
    }, { capture: true, passive: true });
  }

  function switchQuality(levelIndex) {
    cfCurrentQuality = levelIndex;

    // Update labels and active state
    const labelFor = (idx) => {
      if (!cfHlsInstance || idx === -1) return idx === -1 ? "Auto" : String(idx);
      const l = cfHlsInstance.levels[idx];
      return l?.height ? l.height + "p" : "Level " + idx;
    };
    document.querySelectorAll(".cf-quality__opt").forEach(opt => {
      opt.classList.toggle("is-active", Number(opt.dataset.q) === levelIndex);
    });
    document.querySelectorAll("[id^='cf-quality-label']").forEach(el => {
      el.textContent = labelFor(levelIndex);
    });

    // Apply to main player via hls.js — no reload needed
    if (cfHlsInstance) {
      cfHlsInstance.currentLevel = levelIndex; // -1 = auto ABR
    }
    // Apply to fullscreen player
    if (cfHlsFsInstance) {
      cfHlsFsInstance.currentLevel = levelIndex;
    }
  }

  // minBufferSecs: wait for this many seconds to be buffered before playing.
  // 60 for countdown/preload start, 0 for mid-match joins (already synced, play fast).
  function loadAndPlayCockfightVideo(video, src, seekSeconds, minBufferSecs = 0) {
    video.loop = false;
    video.muted = true;
    video.preload = "auto";
    video.poster = "assets/cockfight_banner.png";

    let syncDone = false;
    const startSynced = () => {
      if (syncDone) return;
      syncDone = true;
      const dur = video.duration;
      if (isFinite(dur) && seekSeconds >= dur) {
        showWinnerOverlay("COMPLETED", 60);
        return;
      }
      if (isFinite(dur)) {
        cockfightMaxTime = seekSeconds;
        video.currentTime = seekSeconds;
      }
      waitForBuffer(video, minBufferSecs, 10_000, () => {
        video.play().catch(() => {});
      });
    };

    const srcChanged = video.getAttribute("data-cf-src") !== src;

    if (srcChanged) {
      // Destroy old HLS instance; attach new one
      destroyCfHls(cfHlsInstance);
      cfHlsInstance = attachHls(video, src, {
        maxBuffer: 120,
        onReady: startSynced,
      });
      // Apply stored quality level preference
      if (cfHlsInstance && cfCurrentQuality !== -1) {
        cfHlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
          cfHlsInstance.currentLevel = cfCurrentQuality;
        });
      }
      // Populate quality picker once levels are known
      if (cfHlsInstance) {
        cfHlsInstance.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
          setupQualityPickerFromHls(data.levels);
        });
      }
    } else if (video.readyState >= 1) {
      startSynced();
    } else {
      // HLS is still loading — wait for metadata
      video.addEventListener("loadedmetadata", function onMeta() {
        video.removeEventListener("loadedmetadata", onMeta);
        startSynced();
      });
    }

    if (!cockfightLiveBound) {
      cockfightLiveBound = true;

      video.addEventListener("timeupdate", () => {
        if (location.hash !== "#cockfight") return;
        if (video.currentTime + 0.3 < cockfightMaxTime) cockfightMaxTime = 0;
        cockfightMaxTime = Math.max(cockfightMaxTime, video.currentTime);
      });

      // Anti-scrub: only block large deliberate forward seeks (> 3 s ahead),
      // not tiny internal browser adjustments that happen during buffering/decode
      video.addEventListener("seeking", () => {
        if (location.hash !== "#cockfight") return;
        if (video.currentTime > cockfightMaxTime + 3) {
          try { video.currentTime = cockfightMaxTime; } catch {}
        }
      });

      // Don't resume immediately on pause — mobile browsers internally pause
      // during buffering. Resuming instantly fights the buffer fetch and causes
      // the stuck loop. Wait 800 ms and only resume if still paused.
      video.addEventListener("pause", () => {
        if (location.hash !== "#cockfight") return;
        if (cockfightDialogOpen) return;
        if (video.ended) return;
        if (!document.getElementById("cockfight-panel") || document.getElementById("cockfight-panel").hidden) return;
        setTimeout(() => {
          if (video.paused && !video.ended && location.hash === "#cockfight") {
            video.play().catch(() => {});
          }
        }, 800);
      });

      video.addEventListener("ended", () => {
        if (location.hash !== "#cockfight") return;
        showWinnerOverlay("COMPLETED", 60);
      });

      // Remove the stalled→play() — it interrupts the browser's buffer fetch
      // and causes an infinite stall loop on mobile.
      // The watchdog below handles genuine hangs instead.
      video.addEventListener("contextmenu", (e) => e.preventDefault());

      // Watchdog: every 4 s check if video is supposed to be playing but isn't.
      // This catches genuine hangs without fighting normal buffering pauses.
      let watchdogLastTime = -1;
      setInterval(() => {
        if (location.hash !== "#cockfight") return;
        if (video.ended || cockfightDialogOpen) return;
        const panel = document.getElementById("cockfight-panel");
        if (!panel || panel.hidden) return;
        if (video.paused && !video.ended) {
          video.play().catch(() => {});
          return;
        }
        // Detect freeze: currentTime hasn't advanced for 4 s while video is "playing"
        if (!video.paused && video.currentTime === watchdogLastTime && watchdogLastTime >= 0) {
          // For HLS use recoverMediaError(); for native fall back to play()
          if (cfHlsInstance) {
            cfHlsInstance.recoverMediaError();
          } else {
            video.play().catch(() => {});
          }
        }
        watchdogLastTime = video.currentTime;
      }, 4000);
    }

    // Start polling for match result while video plays
    startResultPoll();
  }

  function startCockfightCountdown(startMs, clockSkew, onDone) {
    const overlay = document.getElementById("cf-countdown");
    const timerEl = document.getElementById("cf-countdown-timer");
    const subEl = document.querySelector(".cf-countdown__sub");
    const labelEl = document.querySelector(".cf-countdown__label");
    if (!overlay || !timerEl) { onDone(); return; }

    // serverNow corrects for device clock skew using server_time from the API
    const serverNow = () => Date.now() + clockSkew;

    if (cfCountdownInterval) clearInterval(cfCountdownInterval);
    overlay.hidden = false;

    const alreadyStarted = startMs <= serverNow();
    if (alreadyStarted) {
      timerEl.textContent = "00:00";
      if (labelEl) labelEl.textContent = "Match is live now!";
      if (subEl) subEl.textContent = "Loading match...";
      setTimeout(() => { overlay.hidden = true; onDone(); }, 1200);
      return;
    }

    if (labelEl) labelEl.textContent = "Next match starts in";
    if (subEl) subEl.textContent = "Get ready to place your bets!";

    const tick = () => {
      const remaining = Math.max(0, Math.floor((startMs - serverNow()) / 1000));
      const h = Math.floor(remaining / 3600);
      const m = Math.floor((remaining % 3600) / 60);
      const s = remaining % 60;
      if (h > 0) {
        timerEl.textContent = `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
      } else {
        timerEl.textContent = `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
      }
      if (remaining <= 0) {
        clearInterval(cfCountdownInterval);
        cfCountdownInterval = null;
        overlay.hidden = true;
        onDone();
      }
    };
    tick();
    cfCountdownInterval = setInterval(tick, 1000);
  }

  function hideCockfightCountdown() {
    if (cfCountdownInterval) { clearInterval(cfCountdownInterval); cfCountdownInterval = null; }
    const overlay = document.getElementById("cf-countdown");
    if (overlay) overlay.hidden = true;
  }

  let cfPollInterval = null;
  let cfResultPollInterval = null;
  let cfWinnerDismissTimeout = null;

  function startResultPoll() {
    if (cfResultPollInterval) return; // already polling
    cfResultPollInterval = setInterval(async () => {
      if (location.hash !== "#cockfight") {
        clearInterval(cfResultPollInterval); cfResultPollInterval = null; return;
      }
      const info = await K.fetchMeronWalaInfo();
      if (!info) return;
      applyCockfightSideLabels(info);
      // Session just settled — last_result will have the winner
      if (!info.open && info.last_result?.winner) {
        clearInterval(cfResultPollInterval); cfResultPollInterval = null;
        showWinnerOverlay(info.last_result.winner);
      }
    }, 3000); // poll every 3 seconds during playback
  }

  function stopResultPoll() {
    if (cfResultPollInterval) { clearInterval(cfResultPollInterval); cfResultPollInterval = null; }
  }

  function showWinnerOverlay(winner, durationSecs) {
    const overlay = document.getElementById("cf-winner");
    const nameEl  = document.getElementById("cf-winner-name");
    const badgeEl = document.getElementById("cf-winner-badge");
    const countEl = document.getElementById("cf-winner-countdown");
    if (!overlay || !nameEl) return;

    // Pause and hide the video so the frozen frame is not visible
    const _vid = document.getElementById("cockfight-video");
    const _vidFs = document.getElementById("cockfight-video-fs");
    if (_vid) { _vid.pause(); _vid.style.visibility = "hidden"; }
    if (_vidFs) { _vidFs.pause(); _vidFs.style.visibility = "hidden"; }

    // Set winner name / match-complete message
    const w = canonicalCockfightSide(winner);
    const l1 = cfMergedSideLabels.COCK1 || "Cock 1";
    const l2 = cfMergedSideLabels.COCK2 || "Cock 2";
    const titles = {
      COCK1: `${l1} Wins! 🐓`,
      COCK2: `${l2} Wins! 🐓`,
      DRAW: "It's a Draw! 🤝",
      COMPLETED: "Match Completed 🏆",
    };
    nameEl.textContent =
      titles[w] || (winner && String(winner).trim() ? String(winner).trim() + " Wins!" : "Winner!");

    // Sub-title tweak for generic completion
    const subEl = overlay.querySelector(".cf-winner__sub");
    if (w === "COMPLETED") {
      if (subEl) subEl.textContent = "Results will be announced shortly.";
    } else {
      if (subEl) subEl.textContent = "Congratulations to all winners!";
    }

    // Check user's own last bet result (only when winner is known)
    badgeEl.textContent = "";
    badgeEl.className = "cf-winner__badge";
    if (w !== "COMPLETED") {
      K.fetchMeronWalaBetsMine && K.fetchMeronWalaBetsMine().then(res => {
        const bets = res?.data || [];
        const last = bets[0];
        if (last) {
          if (last.status === "WON") {
            badgeEl.textContent = "🎉 You Won ₹" + (last.payout_amount || "");
            badgeEl.classList.add("cf-winner__badge--won");
          } else if (last.status === "LOST") {
            badgeEl.textContent = "😔 Better luck next time";
            badgeEl.classList.add("cf-winner__badge--lost");
          }
        }
      }).catch(() => {});
    }

    overlay.hidden = false;
    startConfetti();

    // Countdown — default 5 min, 1 min when called from video-ended
    let secs = durationSecs ?? 5 * 60;
    const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (countEl) countEl.textContent = fmt(secs);
    const ticker = setInterval(() => {
      secs--;
      if (countEl) countEl.textContent = fmt(secs);
      if (secs <= 0) { clearInterval(ticker); location.reload(); }
    }, 1000);
    cfWinnerDismissTimeout = ticker;
  }

  function hideWinnerOverlay() {
    if (cfWinnerDismissTimeout) { clearInterval(cfWinnerDismissTimeout); cfWinnerDismissTimeout = null; }
    stopConfetti();
    const overlay = document.getElementById("cf-winner");
    if (overlay) overlay.hidden = true;
    // Restore video visibility in case we're navigating away without a reload
    const _vid = document.getElementById("cockfight-video");
    const _vidFs = document.getElementById("cockfight-video-fs");
    if (_vid) _vid.style.visibility = "";
    if (_vidFs) _vidFs.style.visibility = "";
  }

  // ── Simple canvas confetti ────────────────────────────────
  let confettiAnimId = null;
  function startConfetti() {
    const canvas = document.getElementById("cf-confetti");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    const pieces = Array.from({length: 60}, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height - canvas.height,
      w: 6 + Math.random() * 8,
      h: 4 + Math.random() * 6,
      color: ["#FFD700","#FF6B6B","#4FC3F7","#81C784","#CE93D8","#FF8A65"][Math.floor(Math.random()*6)],
      speed: 1.5 + Math.random() * 2.5,
      angle: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.15,
    }));
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pieces.forEach(p => {
        p.y += p.speed; p.angle += p.spin;
        if (p.y > canvas.height) { p.y = -p.h; p.x = Math.random() * canvas.width; }
        ctx.save();
        ctx.translate(p.x + p.w/2, p.y + p.h/2);
        ctx.rotate(p.angle);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w/2, -p.h/2, p.w, p.h);
        ctx.restore();
      });
      confettiAnimId = requestAnimationFrame(draw);
    }
    if (confettiAnimId) cancelAnimationFrame(confettiAnimId);
    draw();
  }
  function stopConfetti() {
    if (confettiAnimId) { cancelAnimationFrame(confettiAnimId); confettiAnimId = null; }
    const canvas = document.getElementById("cf-confetti");
    if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  }
  function pollForCockfightUrl(video, seekSeconds) {
    // Show a "waiting for stream" state on the countdown overlay
    const overlay = document.getElementById("cf-countdown");
    const timerEl = document.getElementById("cf-countdown-timer");
    const labelEl = document.querySelector(".cf-countdown__label");
    const subEl = document.querySelector(".cf-countdown__sub");
    if (overlay) {
      overlay.hidden = false;
      if (timerEl) timerEl.textContent = "●●●";
      if (labelEl) labelEl.textContent = "Match is starting...";
      if (subEl) subEl.textContent = "Waiting for live stream...";
    }

    if (cfPollInterval) { clearInterval(cfPollInterval); cfPollInterval = null; }

    cfPollInterval = setInterval(async () => {
      // Stop polling if user navigated away
      if (location.hash !== "#cockfight") {
        clearInterval(cfPollInterval); cfPollInterval = null;
        return;
      }
      const fresh = await K.fetchMeronWalaInfo();
      if (fresh) applyCockfightSideLabels(fresh);
      const flv = fresh?.latest_round_video;
      if (flv?.hls_url) {
        clearInterval(cfPollInterval); cfPollInterval = null;
        if (overlay) overlay.hidden = true;
        loadAndPlayCockfightVideo(video, flv.hls_url, seekSeconds);
      } else if (flv?.requires_authentication) {
        clearInterval(cfPollInterval); cfPollInterval = null;
        if (overlay) overlay.hidden = true;
        showCockfightVideoOverlay("login");
      }
      // else: no url yet — keep polling every second
    }, 1000);
  }

  function showCockfightVideoOverlay(type) {
    let overlay = document.getElementById("cf-video-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "cf-video-overlay";
      overlay.style.cssText = "position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(0,0,0,0.72);z-index:10;border-radius:12px;gap:8px;";
      const wrap = document.querySelector(".cockfight-stream__box");
      if (wrap) wrap.style.position = "relative", wrap.appendChild(overlay);
    }
    if (type === "login") {
      overlay.innerHTML = `<svg width="36" height="36" viewBox="0 0 24 24" fill="none"><path d="M12 12c2.7 0 4-1.3 4-4S14.7 4 12 4 8 5.3 8 8s1.3 4 4 4zm0 2c-4 0-6 2-6 3v1h12v-1c0-1-2-3-6-3z" fill="#fff"/></svg><span style="color:#fff;font-size:13px;font-weight:600;text-align:center;padding:0 16px;">Login to watch the live match</span><button onclick="location.hash='login'" style="background:#e53935;color:#fff;border:none;padding:8px 22px;border-radius:20px;font-size:13px;font-weight:700;cursor:pointer;">Login</button>`;
    } else {
      overlay.innerHTML = `<svg width="36" height="36" viewBox="0 0 24 24" fill="none"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="#aaa"/></svg><span style="color:#bbb;font-size:13px;font-weight:600;text-align:center;padding:0 16px;">No live video available right now</span>`;
    }
    overlay.hidden = false;
  }

  function hideCockfightVideoOverlay() {
    const overlay = document.getElementById("cf-video-overlay");
    if (overlay) overlay.hidden = true;
  }
  function goTab(name) {
    const key = NAV_HASHES.includes(name) ? name : "home";
    location.hash = key;
  }

  function formatReferralCommissionPct(p) {
    const x = Number(p);
    if (!Number.isFinite(x)) return "—";
    if (Math.abs(x - Math.round(x)) < 1e-6) return String(Math.round(x));
    const t = Math.round(x * 10) / 10;
    return String(t).replace(/\.0$/, "");
  }

  /** Human-readable slab range: “1–10 members” / “251+ members”. */
  function formatReferralTierRange(min, max) {
    const mn = min != null && min !== "" ? Number(min) : NaN;
    if (!Number.isFinite(mn) || mn < 0) return "—";
    if (max == null || max === "") return `${Math.round(mn)}+ members`;
    const mx = Number(max);
    if (!Number.isFinite(mx)) return `${Math.round(mn)}+ members`;
    if (mx < mn) return `${Math.round(mn)}+ members`;
    return `${Math.round(mn)}–${Math.round(mx)} members`;
  }

  function formatReferralDateJoin(iso) {
    if (iso == null || iso === "") return "";
    const s = String(iso).trim();
    const d = s.includes("T") ? s.slice(0, 10) : s.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}/.test(d)) return s.slice(0, 16).replace("T", " ");
    try {
      const [y, m, day] = d.split("-").map(Number);
      const dt = new Date(Date.UTC(y, m - 1, day));
      const mon = dt.toLocaleString("en-IN", { month: "short", timeZone: "UTC" });
      return `${day} ${mon} ${y}`;
    } catch {
      return d;
    }
  }

  const REFERRAL_HEADLINE_FIXED = "Receive up to 8% commission";

  function setReferralDisclosureOpen(btn, panel, open) {
    if (!btn || !panel) return;
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.classList.toggle("referral-disclosure-btn--open", open);
  }

  function resetReferralDisclosures() {
    setReferralDisclosureOpen(
      document.getElementById("referral-disclosure-slabs"),
      document.getElementById("referral-slabs-panel"),
      false
    );
    setReferralDisclosureOpen(
      document.getElementById("referral-disclosure-rules"),
      document.getElementById("referral-rules-panel"),
      false
    );
  }

  function initReferralDisclosureTogglesOnce() {
    const pairs = [
      ["referral-disclosure-slabs", "referral-slabs-panel"],
      ["referral-disclosure-rules", "referral-rules-panel"]
    ];
    pairs.forEach(([bid, pid]) => {
      const btn = document.getElementById(bid);
      const panel = document.getElementById(pid);
      if (!btn || !panel || btn.dataset.refDisclosure === "1") return;
      btn.dataset.refDisclosure = "1";
      btn.addEventListener("click", () => setReferralDisclosureOpen(btn, panel, panel.hidden));
    });
  }

  async function refreshReferralSubview() {
    initReferralDisclosureTogglesOnce();
    const heroH = document.getElementById("referral-hero-h");
    const heroErr = document.getElementById("referral-hero-err");
    const statsEl = document.getElementById("referral-stats");
    const statsMoreEl = document.getElementById("referral-stats-more");
    const istLine = document.getElementById("referral-commission-ist-line");
    const slabsPanel = document.getElementById("referral-slabs-panel");
    const slabsBody = document.getElementById("referral-slabs-tbody");
    const dailySec = document.getElementById("referral-daily-section");
    const dailyBody = document.getElementById("referral-daily-tbody");
    const listEl = document.getElementById("referral-list");
    const listHeading = document.getElementById("referral-list-heading");
    const disp = document.getElementById("referral-code-display");
    const cb = document.getElementById("referral-copy-btn");
    if (
      !heroH ||
      !K ||
      typeof K.fetchReferralData !== "function"
    )
      return;
    if (heroErr) {
      heroErr.hidden = true;
      heroErr.textContent = "";
    }
    const hideExtra = () => {
      if (statsMoreEl) statsMoreEl.hidden = true;
      if (istLine) istLine.hidden = true;
      if (dailySec) dailySec.hidden = true;
      if (slabsBody) slabsBody.textContent = "";
      if (dailyBody) dailyBody.textContent = "";
      resetReferralDisclosures();
    };
    const slabsFetch =
      typeof K.fetchCommissionSlabs === "function"
        ? K.fetchCommissionSlabs()
        : Promise.resolve({ data: null, error: null });
    const [refResult, slabsOut] = await Promise.all([
      K.fetchReferralData(),
      slabsFetch,
    ]);
    let { data, error } = refResult;

    /** Merge tiers from `/api/referral/commission-slabs/` when present (authoritative slab table). */
    if (!error && data && slabsOut && slabsOut.data) {
      const sd = slabsOut.data;
      const slabList = Array.isArray(sd.commission_slabs) ? sd.commission_slabs : [];
      let merged = { ...data };
      if (slabList.length > 0) merged.commission_slabs = slabList;
      const curIb = Number(merged.instant_referral_bonus_per_referee);
      const slabIb = sd.instant_referral_bonus_per_referee;
      if (!(Number.isFinite(curIb) && curIb > 0) && slabIb != null && slabIb !== "" && Number(slabIb) > 0) {
        merged.instant_referral_bonus_per_referee = Number(slabIb);
      }
      data = merged;
    }

    if (error || !data) {
      hideExtra();
      if (heroErr) {
        heroErr.textContent = error || "Could not load referral data.";
        heroErr.hidden = false;
      }
      heroH.textContent = REFERRAL_HEADLINE_FIXED;
      if (statsEl) statsEl.hidden = true;
      if (listEl) {
        listEl.hidden = true;
        listEl.textContent = "";
      }
      if (listHeading) listHeading.hidden = true;
      if (disp) disp.textContent = "— — —";
      if (cb) {
        cb.setAttribute("data-copy", "");
        cb.disabled = true;
      }
      return;
    }
    heroH.textContent = REFERRAL_HEADLINE_FIXED;
    const raw = String(data.referral_code || "").trim();
    if (disp) disp.textContent = raw ? [...raw].join(" ") : "—";
    if (cb) {
      cb.setAttribute("data-copy", raw);
      cb.disabled = !raw;
    }
    const fmtMoney = (v) => {
      if (v == null || v === "") return "₹0";
      if (typeof v === "number" && Number.isFinite(v)) return v % 1 === 0 ? "₹" + v : "₹" + v.toFixed(2).replace(/\.?0+$/, "");
      const t = String(v).trim();
      return t ? (t.startsWith("₹") ? t : "₹" + t) : "₹0";
    };
    const st = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = v != null ? String(v) : "—";
    };
    st("referral-stat-total", data.total_referrals);
    st("referral-stat-active", data.active_referrals);
    const earningsEl = document.getElementById("referral-stat-earnings");
    const todayEl = document.getElementById("referral-stat-today");
    if (earningsEl) earningsEl.textContent = fmtMoney(data.total_earnings);
    if (todayEl) todayEl.textContent = fmtMoney(data.commission_earned_today);
    if (statsEl) statsEl.hidden = false;

    const bonusN = Number(data.instant_referral_bonus_per_referee);
    st("referral-stat-bonus-ref", Number.isFinite(bonusN) ? fmtMoney(bonusN) : "—");
    st("referral-stat-total-comm", fmtMoney(data.total_commission_earnings));
    st("referral-stat-daily-comm", fmtMoney(data.total_daily_commission_earnings));
    st("referral-stat-legacy", fmtMoney(data.total_legacy_referral_bonus_earnings));
    if (statsMoreEl) statsMoreEl.hidden = false;

    const ist = data.commission_today_ist != null && String(data.commission_today_ist).trim() !== "";
    if (istLine) {
      if (ist) {
        istLine.hidden = false;
        istLine.textContent = `Today’s commission date (IST): ${String(data.commission_today_ist).trim()}`;
      } else {
        istLine.hidden = true;
        istLine.textContent = "";
      }
    }

    if (slabsBody && slabsPanel) {
      slabsBody.textContent = "";
      const slabsTableWrap = slabsPanel.querySelector(".referral-table-wrap");
      const slabsEmpty = document.getElementById("referral-slabs-empty");
      const slabs = Array.isArray(data.commission_slabs) ? data.commission_slabs : [];
      if (slabs.length) {
        if (slabsTableWrap) slabsTableWrap.hidden = false;
        if (slabsEmpty) slabsEmpty.hidden = true;
        slabs.forEach((s) => {
          const tr = document.createElement("tr");
          const tier = formatReferralTierRange(s.min_referrals, s.max_referrals);
          const pctS = formatReferralCommissionPct(s.commission_percent);
          const rateText = pctS === "—" ? "—" : `${pctS}% commission`;
          const tierTd = document.createElement("td");
          tierTd.className = "referral-table__tier";
          tierTd.textContent = tier;
          const rateTd = document.createElement("td");
          rateTd.textContent = rateText;
          tr.appendChild(tierTd);
          tr.appendChild(rateTd);
          slabsBody.appendChild(tr);
        });
      } else {
        if (slabsTableWrap) slabsTableWrap.hidden = true;
        if (slabsEmpty) slabsEmpty.hidden = false;
      }
    }

    if (dailyBody && dailySec) {
      dailyBody.textContent = "";
      const daily = Array.isArray(data.recent_daily_commissions) ? data.recent_daily_commissions : [];
      if (daily.length) {
        dailySec.hidden = false;
        daily.slice(0, 50).forEach((row) => {
          const tr = document.createElement("tr");
          const d = String(row.commission_date || "").trim() || "—";
          const pl = String(row.referee_username || "").trim() || "—";
          const loss = row.loss_amount != null ? fmtMoney(row.loss_amount) : "—";
          const p = formatReferralCommissionPct(row.commission_percent);
          const comm = row.commission_amount != null ? fmtMoney(row.commission_amount) : "—";
          [d, pl, loss, p === "—" ? "—" : `${p}%`, comm].forEach((cell) => {
            const td = document.createElement("td");
            td.textContent = cell;
            tr.appendChild(td);
          });
          dailyBody.appendChild(tr);
        });
      } else {
        dailySec.hidden = true;
      }
    }

    const refs = Array.isArray(data.referrals) ? data.referrals : [];
    if (listEl && listHeading) {
      if (!refs.length) {
        listEl.hidden = true;
        listHeading.hidden = true;
        listEl.textContent = "";
      } else {
        listHeading.hidden = false;
        listEl.hidden = false;
        listEl.textContent = "";
        refs.slice(0, 50).forEach((r) => {
          const li = document.createElement("li");
          const wrap = document.createElement("div");
          wrap.style.cssText = "display:flex;align-items:flex-start;justify-content:space-between;gap:8px;width:100%;";
          const left = document.createElement("div");
          const name = document.createElement("span");
          name.className = "referral-list__name";
          name.textContent = String(r.username || "").trim() || "—";
          left.appendChild(name);
          const joined = formatReferralDateJoin(r.date_joined);
          if (joined) {
            const j = document.createElement("span");
            j.className = "referral-list__joined";
            j.textContent = `Joined ${joined}`;
            left.appendChild(j);
          }
          wrap.appendChild(left);
          if (r.has_deposit) {
            const tag = document.createElement("span");
            tag.className = "referral-list__tag";
            tag.textContent = "Deposited";
            wrap.appendChild(tag);
          }
          li.appendChild(wrap);
          listEl.appendChild(li);
        });
      }
    }
  }

  function showProfileView(name) {
    const root = document.getElementById("profile-panel");
    if (!root) return;
    root.querySelectorAll(".profile-subview").forEach((el) => {
      const sub = el.getAttribute("data-profile-sub");
      el.hidden = sub !== name;
    });
    if (name === "referral") void refreshReferralSubview();
  }

  function onHash() {
    let h = (location.hash || "#home").replace("#", "").toLowerCase();
    if (h === "promotion") {
      location.replace("#referral");
      return;
    }
    if (h === "auth") {
      location.replace("#login");
      return;
    }
    /* Wallet needs auth for real money; Profile & Settings UI matches APK and is viewable for layout (API actions still need sign-in). */
    if (K && h === "wallet" && !K.isAuthed()) {
      location.replace("#login");
      return;
    }
    const key = ALL_SCREENS.includes(h) ? h : "home";
    if (h !== key && !ALL_SCREENS.includes(h)) {
      location.replace("#" + key);
      return;
    }
    /* transactions & referral are profile subviews */
    const panelKey =
      key === "transactions" || key === "referral" ? "profile" : key;
    document.documentElement.dataset.tab = panelKey;
    if (panelKey !== "home") {
      closeLiveVideoFullscreen();
    }
    if (panelKey !== "cockfight") {
      closeCockfightFullscreen();
    }
    if (panelKey === "profile") {
      if (key === "transactions") {
        showProfileView("transactions");
        loadTransactions("deposits");
      } else if (key === "referral") {
        showProfileView("referral");
      } else {
        showProfileView("main");
      }
    }
    if (panelKey === "wallet" && K) {
      loadWalletFromApi();
    }
    document.querySelectorAll(".panel").forEach((p) => {
      const isMatch = p.getAttribute("data-panel") === panelKey;
      p.hidden = !isMatch;
      p.classList.toggle("panel--active", isMatch);
    });
    document.querySelectorAll(".bottom-nav [data-nav]").forEach((a) => {
      const n = a.getAttribute("data-nav");
      const on = key === "referral" ? n === "referral" : n === panelKey;
      a.classList.toggle("bottom-nav__item--on", on);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    document.getElementById("main-scroll")?.scrollTo(0, 0);
    document.getElementById("gundu-scroll")?.scrollTo(0, 0);

    const v = document.getElementById("live-video");
    const liveChk = document.getElementById("live-on");
    if (v) {
      if (key === "home" && liveChk?.checked) {
        v.play().catch(() => {});
      } else {
        v.pause();
      }
    }
    const vCf = document.getElementById("cockfight-video");
    if (vCf) {
      if (key !== "cockfight") {
        vCf.pause();
        vCf.removeAttribute("data-cf-src");
        hideCockfightCountdown();
        if (cfPollInterval) { clearInterval(cfPollInterval); cfPollInterval = null; }
        stopResultPoll();
        hideWinnerOverlay();
        destroyCfHls(cfHlsInstance); cfHlsInstance = null;
        destroyCfHls(cfHlsFsInstance); cfHlsFsInstance = null;
        cockfightLiveBound = false;
        cockfightMaxTime = 0;
      }
    }
    const vGu = document.getElementById("gundu-video");
    if (vGu) {
      if (key === "gundu") {
        vGu.play().catch(() => {});
      } else {
        vGu.pause();
      }
    }
    if (key === "cockfight") {
      setTimeout(setupCockfightLiveStream, 0);
    }
    refreshHeaderAuth();
    refreshAllBalances();
  }

  document.querySelectorAll(".bottom-nav [data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const t = el.getAttribute("data-nav");
      if (t) {
        if (location.hash === "#" + t) onHash();
        else location.hash = t;
      }
    });
  });

  document
    .querySelectorAll(
      ".wallet-pill[data-nav], .game-tile[data-nav], a.brand--home[data-nav], a.cockfight-tap-home[data-nav]"
    )
    .forEach((el) => {
    const n = el.getAttribute("data-nav");
    if (n && NAV_HASHES.includes(n)) {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        goTab(n);
      });
    }
  });

  const search = document.querySelector(".search__input");
  const clear = document.querySelector(".search__clear");
  if (search && clear) {
    search.addEventListener("input", () => {
      clear.hidden = !search.value;
    });
    clear.addEventListener("click", () => {
      search.value = "";
      clear.hidden = true;
      search.focus();
    });
  }

  const live = document.getElementById("live-on");
  const offMsg = document.getElementById("live-off");
  const liveCardWrap = document.getElementById("live-card-wrap");
  const liveVideo = document.getElementById("live-video");
  if (live && offMsg && liveCardWrap) {
    const sync = () => {
      const on = live.checked;
      offMsg.hidden = on;
      liveCardWrap.hidden = !on;
      if (!on) closeLiveVideoFullscreen();
      if (liveVideo) {
        if (on) {
          liveVideo.play().catch(() => {});
        } else {
          liveVideo.pause();
        }
      }
    };
    live.addEventListener("change", sync);
    sync();
  }

  function closeLiveVideoFullscreen() {
    const fsRoot = document.getElementById("live-fullscreen");
    if (!fsRoot || fsRoot.hidden) return;
    fsRoot.hidden = true;
    document.body.style.overflow = "";
  }

  function openLiveVideoFullscreen() {
    const fsRoot = document.getElementById("live-fullscreen");
    const vIn = document.getElementById("live-video");
    const vFs = document.getElementById("live-video-fs");
    if (!fsRoot || !vIn || !vFs) return;
    if (!document.getElementById("live-on")?.checked) return;
    fsRoot.hidden = false;
    vIn.pause();
    const src = vIn.querySelector("source");
    vFs.muted = true;
    vFs.loop = true;
    vFs.poster = vIn.poster || "";
    if (src && src.src) {
      let s = vFs.querySelector("source");
      if (!s) {
        s = document.createElement("source");
        vFs.appendChild(s);
      }
      s.src = src.src;
      s.type = src.type || "video/mp4";
      vFs.load();
    }
    vFs.currentTime = vIn.currentTime || 0;
    vFs.play().catch(() => {});
    document.body.style.overflow = "hidden";
  }

  function closeCockfightFullscreen() {
    try {
      if (screen.orientation && typeof screen.orientation.unlock === "function") screen.orientation.unlock();
    } catch (_) {}
    /* Exit native fullscreen if active */
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      (document.exitFullscreen || document.webkitExitFullscreen || (() => {})).call(document);
    }
    if (typeof window.__closeCfFsBetSheet === "function") window.__closeCfFsBetSheet();
    if (typeof window.__cockfightSyncMainFromFs === "function") window.__cockfightSyncMainFromFs();
    const fsRoot = document.getElementById("cockfight-fullscreen");
    const vFs = document.getElementById("cockfight-video-fs");
    const vIn = document.getElementById("cockfight-video");
    cockfightDialogOpen = false;
    if (fsRoot && !fsRoot.hidden) {
      fsRoot.hidden = true;
      if (vFs) {
        vFs.pause();
        vFs.removeAttribute("src");
        vFs.replaceChildren();
        destroyCfHls(cfHlsFsInstance); cfHlsFsInstance = null;
      }
      document.body.style.overflow = "";
    }
    if (document.documentElement.dataset.tab === "cockfight" && vIn) {
      vIn.muted = true;
      vIn.play().catch(() => {});
    }
  }

  function openCockfightFullscreen() {
    const vIn = document.getElementById("cockfight-video");
    if (!vIn) return;
    if (document.documentElement.dataset.tab !== "cockfight") return;
    /* Always use overlay dialog so betting strip (APK-style) stays visible */
    openCockfightFsDialog();
  }

  function openCockfightFsDialog() {
    const fsRoot = document.getElementById("cockfight-fullscreen");
    const vIn  = document.getElementById("cockfight-video");
    const vFs  = document.getElementById("cockfight-video-fs");
    if (!fsRoot || !vIn || !vFs) return;

    cockfightDialogOpen = true;
    const url = (vIn.getAttribute("data-cf-src") || "").trim();
    if (!url) { cockfightDialogOpen = false; return; }
    // Attach fresh HLS to the FS video element
    if (vFs.getAttribute("data-cf-src") !== url) {
      vFs.muted = true;
      vFs.loop = false;
      vFs.poster = "";
      destroyCfHls(cfHlsFsInstance);
      cfHlsFsInstance = attachHls(vFs, url, {
        maxBuffer: 120,
        onReady: () => {
          vFs.currentTime = vIn.currentTime || 0;
          vFs.play().catch(() => {});
          // Apply current quality preference
          if (cfHlsFsInstance && cfCurrentQuality !== -1) {
            cfHlsFsInstance.currentLevel = cfCurrentQuality;
          }
        },
      });
    }
    /** Browser fullscreen + landscape lock — mobile plays wide; portrait lock removed on close */
    function tryLandscapeFullscreenForCockfight() {
      const lockLandscape = () => {
        try {
          const o = screen.orientation;
          if (o && typeof o.lock === "function") {
            return o.lock("landscape").catch(() => o.lock("landscape-primary").catch(() => {}));
          }
        } catch (_) {}
        return Promise.resolve();
      };

      const rfs =
        fsRoot.requestFullscreen ||
        fsRoot.webkitRequestFullscreen ||
        fsRoot.webkitRequestFullScreen ||
        fsRoot.msRequestFullscreen;

      if (rfs) {
        Promise.resolve(rfs.call(fsRoot))
          .then(lockLandscape)
          .catch(() => lockLandscape());
      } else {
        lockLandscape();
      }
    }

    const syncAndShow = () => {
      try { vFs.currentTime = vIn.currentTime || 0; } catch {}
      vIn.pause();
      vFs.style.opacity = "0";
      fsRoot.hidden = false;
      document.body.style.overflow = "hidden";
      tryLandscapeFullscreenForCockfight();
      vFs.play().catch(() => {});
      /* Fade in video once first frame is ready to avoid poster/blank flash */
      const showVideo = () => {
        vFs.style.opacity = "1";
      };
      vFs.addEventListener("playing", showVideo, { once: true });
      setTimeout(showVideo, 400); /* fallback */
      if (typeof window.__closeCfMainBetSheet === "function") window.__closeCfMainBetSheet();
      if (typeof window.__cockfightSyncFsFromMain === "function") window.__cockfightSyncFsFromMain();
    };
    if (vFs.readyState >= 1) {
      syncAndShow();
    } else {
      vFs.addEventListener("loadedmetadata", syncAndShow, { once: true });
      vFs.load();
    }
  }

  document.getElementById("live-video-max")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openLiveVideoFullscreen();
  });
  document.getElementById("live-fs-close")?.addEventListener("click", () => {
    closeLiveVideoFullscreen();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const lfs = document.getElementById("live-fullscreen");
    if (lfs && !lfs.hidden) closeLiveVideoFullscreen();
    const cfs = document.getElementById("cockfight-fullscreen");
    if (cfs && !cfs.hidden) closeCockfightFullscreen();
  });

  document.getElementById("cockfight-video-max")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openCockfightFullscreen();
  });
  document.getElementById("cockfight-fs-close")?.addEventListener("click", () => {
    closeCockfightFullscreen();
  });
  /* Resume main video when native fullscreen exits */
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) {
      cockfightDialogOpen = false;
      const vIn = document.getElementById("cockfight-video");
      if (document.documentElement.dataset.tab === "cockfight" && vIn) {
        vIn.muted = true;
        vIn.play().catch(() => {});
      }
    }
  });
  document.addEventListener("webkitfullscreenchange", () => {
    if (!document.webkitFullscreenElement) {
      cockfightDialogOpen = false;
      const vIn = document.getElementById("cockfight-video");
      if (document.documentElement.dataset.tab === "cockfight" && vIn) {
        vIn.muted = true;
        vIn.play().catch(() => {});
      }
    }
  });

  window.addEventListener("kokoroko:auth", () => {
    refreshAllBalances();
  });

  (function setupWalletUI() {
    const panel = document.getElementById("wallet-panel");
    const walletApp = document.getElementById("wallet-app-root");
    if (!panel) return;
    const tabs = panel.querySelectorAll(".wallet-tabs__tab");
    const amt = document.getElementById("wallet-amount-input");
    const chips = document.getElementById("wallet-chips");
    const payCards = panel.querySelectorAll("[data-wallet-pay]");
    const btnDep = document.getElementById("wallet-btn-deposit");
    const btnWdr = document.getElementById("wallet-btn-withdraw");
    const infoDep = panel.querySelector("[data-wallet-info-deposit]");
    const infoWdr = panel.querySelector("[data-wallet-info-withdraw]");
    const howtoQ = panel.querySelector("[data-wallet-howto-q]");
    const onlyWdr = panel.querySelectorAll("[data-wallet-only-withdraw]");
    const destBank = panel.querySelector("[data-wallet-dest-bank]");
    const destUpi = panel.querySelector("[data-wallet-dest-upi]");

    let mode = "deposit";
    let pay = "upi";

    function syncPayDest() {
      if (destBank && destUpi) {
        const isBank = pay === "bank";
        destBank.hidden = !isBank;
        destUpi.hidden = isBank;
      }
    }

    function setMode(m) {
      mode = m;
      const isDep = m === "deposit";
      if (walletApp) walletApp.dataset.walletMode = m;
      tabs.forEach((t) => {
        const on = t.getAttribute("data-wallet-mode") === m;
        t.classList.toggle("is-on", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      if (infoDep && infoWdr) {
        infoDep.hidden = !isDep;
        infoWdr.hidden = isDep;
      }
      onlyWdr.forEach((el) => {
        el.hidden = isDep;
      });
      if (howtoQ) howtoQ.textContent = isDep ? "How to Deposit" : "How to Withdraw";
      if (chips) chips.setAttribute("data-wallet-hidden", isDep ? "0" : "1");
      const ctaDepBlock = document.getElementById("wallet-cta-deposit-block");
      const ctaWdrBlock = document.getElementById("wallet-cta-withdraw-block");
      if (ctaDepBlock && ctaWdrBlock) {
        ctaDepBlock.hidden = !isDep;
        ctaWdrBlock.hidden = isDep;
      }
      if (amt) {
        const phDep = amt.getAttribute("data-placeholder-deposit") || "e.g. 500";
        const phWdr = amt.getAttribute("data-placeholder-withdraw") || "e.g. 200";
        amt.placeholder = isDep ? phDep : phWdr;
        if (isDep) {
          if (!amt.value.trim()) amt.value = "1000";
        } else {
          amt.value = "";
        }
      }
      if (isDep) {
        const sel = chips?.querySelector(".wallet-chip.is-on");
        if (sel && amt) amt.value = sel.getAttribute("data-amt") || "1000";
      }
      syncPayDest();
    }

    function setPay(p) {
      pay = p;
      payCards.forEach((c) => {
        const on = c.getAttribute("data-wallet-pay") === p;
        c.classList.toggle("is-selected", on);
        c.setAttribute("aria-pressed", on ? "true" : "false");
      });
      syncPayDest();
    }

    tabs.forEach((t) => {
      t.addEventListener("click", () => {
        const m = t.getAttribute("data-wallet-mode");
        if (m) setMode(m);
      });
    });
    payCards.forEach((c) => {
      c.addEventListener("click", () => {
        const p = c.getAttribute("data-wallet-pay");
        if (p) setPay(p);
      });
    });
    if (chips) {
      chips.addEventListener("click", (e) => {
        const chip = e.target.closest(".wallet-chip");
        if (!chip || !chips.contains(chip)) return;
        chips.querySelectorAll(".wallet-chip").forEach((x) => x.classList.toggle("is-on", x === chip));
        if (amt) amt.value = chip.getAttribute("data-amt") || "";
      });
    }
    if (amt) {
      amt.addEventListener("input", () => {
        const d = amt.value.replace(/\D/g, "").slice(0, 9);
        if (amt.value !== d) amt.value = d;
      });
    }
    const fileIn = document.getElementById("wallet-deposit-screenshot");

    /* ── Deposit Flow Dialog ── */
    (function setupDepositDialog() {
      const dialog = document.getElementById("dep-dialog");
      const closeBtn = document.getElementById("dep-dialog-close");
      const amountDisplay = document.getElementById("dep-amount-display");
      const timerEl = document.getElementById("dep-timer");
      const loadingEl = document.getElementById("dep-loading");
      const methodsWrap = document.getElementById("dep-methods-wrap");
      const methodsRow = document.getElementById("dep-methods-row");
      const detailsCard = document.getElementById("dep-details-card");
      const upiBlock = document.getElementById("dep-upi-block");
      const upiIdEl = document.getElementById("dep-upi-id");
      const copyUpiBtn = document.getElementById("dep-copy-upi");
      const qrWrap = document.getElementById("dep-qr-wrap");
      const qrImg = document.getElementById("dep-qr-img");
      const bankBlock = document.getElementById("dep-bank-block");
      const bankGrid = document.getElementById("dep-bank-grid");
      const uploadSection = document.getElementById("dep-upload-section");
      const uploadBtn = document.getElementById("dep-upload-btn");
      const filePreview = document.getElementById("dep-file-preview");
      const fileNameEl = document.getElementById("dep-file-name");
      const fileRemove = document.getElementById("dep-file-remove");
      const errEl = document.getElementById("dep-err");
      const submitBtn = document.getElementById("dep-submit-btn");
      const submitTxt = document.getElementById("dep-submit-txt");
      const depFileIn = document.getElementById("dep-screenshot-input");
      const upiLabel = document.getElementById("dep-upi-label");
      const methodsTitle = document.getElementById("dep-methods-title");

      let methods = [];
      let selectedMethod = null;
      let selectedFile = null;
      let depositAmount = 0;
      let timerInterval = null;
      let depositChannel = "upi";

      /** Whether this method is a bank transfer (not UPI / app / QR). */
      function isBankDepositMethod(m) {
        const t = (m.type || "").toUpperCase();
        if (t.includes("BANK")) return true;
        if (t.includes("UPI") || t.includes("GPAY") || t.includes("PHONE") || t.includes("PAYTM") || t.includes("QR")) {
          return false;
        }
        if (m.upiId) return false;
        return !!(m.accountNumber || m.ifsc || m.bankName);
      }

      function filterMethodsByChannel(list, channel) {
        return (list || []).filter((m) => (channel === "bank" ? isBankDepositMethod(m) : !isBankDepositMethod(m)));
      }

      function startTimer() {
        let secs = 600;
        function fmt(s) {
          return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
        }
        if (timerEl) timerEl.textContent = fmt(secs);
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
          secs = Math.max(0, secs - 1);
          if (timerEl) timerEl.textContent = fmt(secs);
          if (secs === 0) clearInterval(timerInterval);
        }, 1000);
      }
      function stopTimer() { clearInterval(timerInterval); }

      function showErr(msg) {
        if (!errEl) return;
        errEl.textContent = msg;
        errEl.hidden = !msg;
      }

      function copyText(text) {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).catch(() => {});
        } else {
          const el = document.createElement("textarea");
          el.value = text;
          document.body.appendChild(el);
          el.select();
          document.execCommand("copy");
          document.body.removeChild(el);
        }
      }

      function buildUpiDeepLink(m) {
        // Build standard UPI intent URL for PhonePe / GPay / Paytm / any UPI app
        const upi = m.upiId || "";
        if (!upi) return m.deepLink || null;
        const t = (m.type || "").toUpperCase();
        const params = new URLSearchParams({
          pa: upi,
          pn: "Kokoroko",
          am: String(depositAmount),
          cu: "INR",
          tn: "Deposit to Kokoroko"
        });
        // Use app-specific scheme when possible, fallback to generic upi://
        if (t.includes("PHONEPE")) return "phonepe://pay?" + params.toString();
        if (t.includes("GPAY"))    return "tez://upi/pay?" + params.toString();
        if (t.includes("PAYTM"))   return "paytmmp://upi/pay?" + params.toString();
        return "upi://pay?" + params.toString();
      }

      function launchPayment(m) {
        const link = buildUpiDeepLink(m);
        if (link) {
          // Try app deep link; fallback to upi:// which browsers/Android handle
          window.location.href = link;
        }
        // Show upload section immediately so user can upload after paying
        if (uploadSection) uploadSection.hidden = false;
      }

      function renderMethod(m) {
        // Hide UPI ID card — payment goes direct via deep link
        if (detailsCard) detailsCard.hidden = true;
        if (upiBlock) upiBlock.hidden = true;
        if (bankBlock) bankBlock.hidden = true;

        // Bank accounts (no deep link): show details card
        const t = (m.type || "").toUpperCase();
        const isBank = t.includes("BANK");
        if (isBank && detailsCard && bankGrid) {
          const rows = [
            ["Account Name", m.accountHolder],
            ["Bank Name", m.bankName],
            ["Account Number", m.accountNumber],
            ["IFSC Code", m.ifsc]
          ].filter(([, v]) => v);
          if (rows.length) {
            bankGrid.innerHTML = rows.map(([label, val]) =>
              `<div class="dep-bank-row">
                <span class="dep-bank-row__label">${label}</span>
                <span class="dep-bank-row__val">${val}
                  <button type="button" class="dep-bank-copy" onclick="navigator.clipboard&&navigator.clipboard.writeText('${val}')" aria-label="Copy ${label}">
                    <svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
                  </button>
                </span>
              </div>`
            ).join("");
            if (bankBlock) bankBlock.hidden = false;
            if (detailsCard) detailsCard.hidden = false;
          }
        }
        if (uploadSection) uploadSection.hidden = false;
      }

      function selectMethod(m) {
        selectedMethod = m;
        if (methodsRow) {
          methodsRow.querySelectorAll(".dep-method-btn").forEach((b) => {
            b.classList.toggle("is-active", Number(b.dataset.mid) === m.id);
          });
        }
        renderMethod(m);
        // Launch payment app immediately on tap
        launchPayment(m);
      }

      function updateSubmit() {
        if (submitBtn) submitBtn.disabled = !selectedFile || !selectedMethod;
      }

      function openDialog(amount, payChannel) {
        if (!dialog) return;
        depositChannel = payChannel === "bank" ? "bank" : "upi";
        if (methodsTitle) {
          methodsTitle.textContent =
            depositChannel === "bank" ? "Bank transfer" : "Pay via UPI";
        }
        depositAmount = amount;
        selectedFile = null;
        selectedMethod = null;
        methods = [];
        if (amountDisplay) amountDisplay.textContent = "\u20B9" + amount.toLocaleString("en-IN");
        if (loadingEl) loadingEl.hidden = false;
        if (methodsWrap) methodsWrap.hidden = true;
        if (detailsCard) detailsCard.hidden = true;
        if (uploadSection) uploadSection.hidden = false;
        if (filePreview) filePreview.hidden = true;
        if (errEl) errEl.hidden = true;
        if (submitBtn) submitBtn.disabled = true;
        dialog.hidden = false;
        document.body.style.overflow = "hidden";
        startTimer();

        K.fetchPaymentMethodsDetails().then(({ data, error }) => {
          if (loadingEl) loadingEl.hidden = true;
          if (error || !data || !data.length) {
            showErr(error || "No payment methods available. Please contact support.");
            return;
          }
          methods = filterMethodsByChannel(data, depositChannel);
          if (!methods.length) {
            showErr(
              depositChannel === "bank"
                ? "No bank transfer methods available. Try UPI or contact support."
                : "No UPI methods available. Try bank transfer or contact support."
            );
            return;
          }
          if (methodsRow) {
            const iconColors = {
              PHONEPE: "#5f259f", GPAY: "#4285f4", PAYTM: "#002970",
              UPI: "#ff6b00", BANK: "#1565c0", QR: "#388e3c"
            };
            methodsRow.innerHTML = methods.map((m) => {
              const t = (m.type || "UPI").toUpperCase();
              const color = iconColors[Object.keys(iconColors).find((k) => t.includes(k)) || "UPI"] || "#ff6b00";
              return `<button type="button" class="dep-method-btn" data-mid="${m.id}">
                <span class="dep-method-btn__icon" style="background:${color}18;">
                  <svg viewBox="0 0 24 24" width="22" height="22"><path fill="${color}" d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z"/></svg>
                </span>
                <span class="dep-method-btn__name">${m.name || m.type}</span>
                <span class="dep-method-btn__arrow">
                  <svg viewBox="0 0 24 24" width="22" height="22"><path fill="${color}" d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6z"/></svg>
                </span>
              </button>`;
            }).join("");
            methodsRow.querySelectorAll(".dep-method-btn").forEach((b) => {
              b.addEventListener("click", () => {
                const m = methods.find((x) => x.id === Number(b.dataset.mid));
                if (m) selectMethod(m);
              });
            });
          }
          if (methodsWrap) methodsWrap.hidden = false;
          // Do NOT auto-select — user must explicitly tap a method
          updateSubmit();
        });
      }

      function closeDialog() {
        if (dialog) dialog.hidden = true;
        document.body.style.overflow = "";
        stopTimer();
        if (depFileIn) depFileIn.value = "";
        selectedFile = null;
        if (filePreview) filePreview.hidden = true;
        updateSubmit();
      }

      if (closeBtn) closeBtn.addEventListener("click", closeDialog);

      if (uploadBtn && depFileIn) {
        uploadBtn.addEventListener("click", () => { depFileIn.value = ""; depFileIn.click(); });
        depFileIn.addEventListener("change", () => {
          const f = depFileIn.files && depFileIn.files[0];
          if (!f) return;
          selectedFile = f;
          if (fileNameEl) fileNameEl.textContent = f.name;
          if (filePreview) filePreview.hidden = false;
          showErr("");
          updateSubmit();
        });
      }

      if (fileRemove) {
        fileRemove.addEventListener("click", () => {
          selectedFile = null;
          if (depFileIn) depFileIn.value = "";
          if (filePreview) filePreview.hidden = true;
          updateSubmit();
        });
      }

      if (submitBtn) {
        submitBtn.addEventListener("click", async () => {
          if (!selectedFile || !selectedMethod || !K) return;
          showErr("");
          submitBtn.disabled = true;
          if (submitTxt) submitTxt.textContent = "Submitting…";
          const { data, error } = await K.postDepositUpload(selectedFile, depositAmount, selectedMethod.id);
          submitBtn.disabled = false;
          if (submitTxt) submitTxt.textContent = "Submit Payment Proof";
          if (error) {
            showErr(error);
          } else {
            closeDialog();
            await refreshAllBalances();
            window.alert("Deposit submitted! Status: " + (data && data.status ? data.status : "PENDING") + "\nYour account will be credited once approved.");
          }
        });
      }

      /* Hook into Proceed to Deposit */
      window.__openDepositDialog = openDialog;
    })();

    btnDep?.addEventListener("click", async () => {
      if (!K || !K.isAuthed()) {
        location.hash = "login";
        return;
      }
      if (K.isLocalDemo()) {
        window.alert("Sign in with a real account to deposit.");
        return;
      }
      const amount = parseInt(amt && amt.value ? amt.value.replace(/\D/g, "") : "0", 10) || 0;
      if (amount < 100) {
        window.alert("Minimum deposit is ₹100.");
        return;
      }
      if (window.__openDepositDialog) window.__openDepositDialog(amount, pay);
    });
    btnWdr?.addEventListener("click", async () => {
      if (!K || !K.isAuthed()) {
        location.hash = "login";
        return;
      }
      if (K.isLocalDemo()) {
        window.alert("Demo account cannot withdraw.");
        return;
      }
      const n = parseInt(amt && amt.value ? amt.value.replace(/\D/g, "") : "0", 10) || 0;
      if (n <= 0) {
        window.alert("Enter a valid amount");
        return;
      }
      let details;
      if (pay === "upi") {
        details = (lastBankWithdraw.upi || "").trim();
      } else {
        const a = (lastBankWithdraw.bankAcc || "").trim();
        const i = (lastBankWithdraw.bankIfsc || "").trim();
        if (!a) {
          window.alert("No saved bank. Add in app or when API returns details.");
          return;
        }
        details = a + (i ? " | " + i : "");
      }
      if (!details) {
        window.alert("Add a UPI or bank for this method in your account first.");
        return;
      }
      const { data, error } = await K.postWithdrawInitiate(n, pay === "upi" ? "UPI" : "BANK", details);
      if (error) window.alert(error);
      else window.alert("Withdrawal #" + (data && data.id) + " — " + (data && data.status) + " (₹" + (data && data.amount) + ")");
      await refreshAllBalances();
    });
    panel.querySelectorAll(".wallet-outlined-btn").forEach((b) => {
      b.addEventListener("click", () => {
        const k = b.getAttribute("data-add");
        window.alert(
          k === "bank"
            ? "Add bank account (web preview; connect API for saved withdrawal details)."
            : "Add UPI ID (web preview; connect API for saved withdrawal details)."
        );
      });
    });

    setMode("deposit");
    setPay("upi");
  })();

  const txnLoaded = { deposits: false, withdrawals: false };
  async function loadTransactions(which) {
    if (!K) return;
    const listEl = document.getElementById(which === "deposits" ? "txn-list-deposits" : "txn-list-withdrawals");
    if (!listEl) return;
    if (txnLoaded[which]) return;
    listEl.innerHTML = '<p class="txn-loading">Loading…</p>';
    const { data, error } = which === "deposits" ? await K.fetchDepositsMine() : await K.fetchWithdrawsMine();
    if (error) {
      listEl.innerHTML = `<p class="txn-empty">${error}</p>`;
      return;
    }
    txnLoaded[which] = true;
    if (!data || !data.length) {
      listEl.innerHTML = `<p class="txn-empty">No ${which} yet.</p>`;
      return;
    }
    listEl.innerHTML = data.map((item) => {
      const amount = item.amount || item.total_amount || item.credit || "–";
      const status = (item.status || item.payment_status || "pending").toLowerCase();
      const date = item.created_at || item.date || item.timestamp || "";
      const dateStr = date ? new Date(date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "–";
      const id = item.id || item.transaction_id || "";
      const note = (item.admin_note || item.note || "").trim();
      const statusClass = status.includes("success") || status.includes("approv") || status.includes("complet")
        ? "txn-card--success" : status.includes("reject") || status.includes("fail")
        ? "txn-card--fail" : "txn-card--pending";
      const statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
      return `<div class="txn-card ${statusClass}">
        <div class="txn-card__row">
          <span class="txn-card__label">${which === "deposits" ? "Deposit" : "Withdrawal"}</span>
          <span class="txn-card__amount">₹${amount}</span>
        </div>
        <div class="txn-card__row txn-card__row--sub">
          <span class="txn-card__date">${dateStr}</span>
          <span class="txn-card__status">${statusLabel}</span>
        </div>
        ${note ? `<p class="txn-card__note">${note}</p>` : ""}
      </div>`;
    }).join("");
  }

  async function loadProfileForm() {
    if (!K) return;
    const hint = document.getElementById("profile-form-hint");
    const { data, error } = await K.fetchProfile();
    if (error) {
      if (hint) hint.textContent = error;
      return;
    }
    if (!data) return;
    if (hint) hint.textContent = "Edit your details.";
    const u = document.getElementById("pf-username");
    const ph = document.getElementById("pf-phone");
    const em = document.getElementById("pf-email");
    if (u) u.value = data.username || "";
    if (ph) ph.value = data.phoneNumber || "";
    if (em) em.value = data.email || "";
    if (data.gender) {
      document.querySelectorAll('input[name="gender"]').forEach((r) => {
        r.checked = r.value === data.gender;
      });
    }
  }
  (async function applySupportContacts() {
    if (!K) return;
    const c = await K.fetchSupportContacts();
    if (!c) return;
    const w = c.whatsapp
      ? "https://wa.me/" + String(c.whatsapp).replace(/\D/g, "")
      : null;
    const tg = c.telegram
      ? c.telegram.startsWith("http")
        ? c.telegram
        : "https://t.me/" + c.telegram.replace(/^@/, "")
      : null;
    const wa = document.getElementById("profile-link-wa");
    const tgel = document.getElementById("profile-link-tg");
    if (wa && w) wa.href = w;
    if (tgel && tg) tgel.href = tg;
    if (c.facebook) {
      const el = document.getElementById("profile-link-fb");
      if (el) el.href = c.facebook;
    }
    if (c.instagram) {
      const el = document.getElementById("profile-link-ig");
      if (el) el.href = c.instagram;
    }
    if (c.youtube) {
      const el = document.getElementById("profile-link-yt");
      if (el) el.href = c.youtube;
    }
  })();

  const profilePanel = document.getElementById("profile-panel");
  if (profilePanel) {
    profilePanel.addEventListener("click", (e) => {
      const back = e.target.closest("[data-profile-back]");
      if (back) {
        e.preventDefault();
        const name = back.getAttribute("data-profile-back");
        if (name) showProfileView(name);
        return;
      }
      const open = e.target.closest("[data-open-profile]");
      if (open) {
        e.preventDefault();
        const name = open.getAttribute("data-open-profile");
        if (name) {
          if (name === "transactions") {
            location.hash = "transactions";
          } else {
            showProfileView(name);
            if (name === "details") loadProfileForm();
          }
        }
        return;
      }
    });

    /* Transaction tab switching */
    profilePanel.addEventListener("click", (e) => {
      const tab = e.target.closest("[data-txn-tab]");
      if (!tab) return;
      const which = tab.getAttribute("data-txn-tab");
      profilePanel.querySelectorAll(".txn-tab").forEach((t) => {
        const active = t.getAttribute("data-txn-tab") === which;
        t.classList.toggle("txn-tab--active", active);
        t.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.getElementById("txn-list-deposits").hidden = which !== "deposits";
      document.getElementById("txn-list-withdrawals").hidden = which !== "withdrawals";
      loadTransactions(which);
    });
  }

  document.getElementById("profile-logout-btn")?.addEventListener("click", async () => {
    if (!window.confirm("Log out?")) return;
    if (K) await K.logout();
    location.hash = "home";
    refreshAllBalances();
  });

  document.getElementById("profile-update-btn")?.addEventListener("click", async () => {
    if (!K) return;
    const g = document.querySelector('input[name="gender"]:checked');
    const { ok, error } = await K.postProfile({
      username: (document.getElementById("pf-username") && document.getElementById("pf-username").value) || "",
      phoneNumber: (document.getElementById("pf-phone") && document.getElementById("pf-phone").value) || "",
      email: (document.getElementById("pf-email") && document.getElementById("pf-email").value) || "",
      gender: g ? g.value : null
    });
    if (ok) window.alert("Profile updated.");
    else window.alert(error || "Update failed");
  });

  const copyBtn = document.getElementById("referral-copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const t = copyBtn.getAttribute("data-copy") || "AGHMU545";
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(t);
        } else {
          throw new Error("no clipboard");
        }
      } catch {
        window.prompt("Copy:", t);
      }
    });
  }

  (function initGundu() {
    const panel = document.getElementById("gundu-panel");
    if (!panel) return;

    const stakes = Object.create(null);
    let tapStack = [];
    let focusedFace = null;
    let selectedChip = 100;
    let placing = false;
    let regionTab = 0;

    function syncCard(face) {
      const btn = panel.querySelector(`.gundu-dice[data-gundu-face="${face}"]`);
      if (!btn) return;
      const amt = stakes[face] | 0;
      const main = btn.querySelector(".gundu-dice__main");
      const pip = main.querySelector(".gundu-pip");
      const st = main.querySelector(".gundu-dice__stake");
      if (amt > 0) {
        pip.hidden = true;
        st.hidden = false;
        st.textContent = String(amt);
        const fs = amt >= 10000 ? 10 : amt >= 1000 ? 12 : amt >= 100 ? 14 : 16;
        st.style.fontSize = fs + "px";
      } else {
        pip.hidden = false;
        st.hidden = true;
      }
      btn.classList.toggle("gundu-dice--focus", focusedFace === face);
    }

    function syncChips() {
      panel.querySelectorAll(".gundu-chip").forEach((c) => {
        const v = +c.getAttribute("data-amt");
        c.classList.toggle("is-on", v === selectedChip);
      });
    }

    function hasAnyStake() {
      for (let f = 1; f <= 6; f++) {
        if ((stakes[f] | 0) > 0) return true;
      }
      return false;
    }

    function syncPlace() {
      const has = hasAnyStake();
      const btn = document.getElementById("gundu-place-btn");
      if (btn) {
        btn.disabled = !has || placing;
      }
      const undo = document.getElementById("gundu-undo");
      if (undo) {
        const ok = tapStack.length > 0 && !placing;
        undo.disabled = !ok;
        undo.setAttribute("aria-disabled", ok ? "false" : "true");
      }
    }

    function syncAllCards() {
      for (let f = 1; f <= 6; f++) syncCard(f);
    }

    function buildLastStrip() {
      const host = document.getElementById("gundu-last-inner");
      if (!host) return;
      host.replaceChildren();
      const pips9 = {
        1: [0, 0, 0, 0, 1, 0, 0, 0, 0],
        2: [1, 0, 0, 0, 0, 0, 0, 0, 1],
        3: [1, 0, 0, 0, 1, 0, 0, 0, 1],
        4: [1, 0, 1, 0, 0, 0, 1, 0, 1],
        5: [1, 0, 1, 0, 1, 0, 1, 0, 1],
        6: [1, 0, 1, 1, 0, 1, 1, 0, 1]
      };
      for (let r = 1; r <= 20; r++) {
        const col = document.createElement("div");
        col.className = "gundu-lastcol";
        const h = document.createElement("div");
        h.className = "gundu-lastcol__h";
        h.textContent = String(r);
        col.appendChild(h);
        const stack = document.createElement("div");
        stack.className = "gundu-lastcol__stack";
        for (let v = 1; v <= 6; v++) {
          const d = document.createElement("div");
          d.className = "gundu-mini";
          const pat = pips9[v] || pips9[1];
          const wrap = document.createElement("div");
          wrap.className = "gundu-mini__pip";
          for (let i = 0; i < 9; i++) {
            const s = document.createElement("span");
            if (pat[i]) s.className = "on";
            wrap.appendChild(s);
          }
          d.appendChild(wrap);
          stack.appendChild(d);
        }
        col.appendChild(stack);
        host.appendChild(col);
      }
    }

    function setRegion(i) {
      regionTab = i;
      panel.querySelectorAll(".gundu-pill").forEach((p) => {
        const idx = +p.getAttribute("data-gundu-region");
        p.classList.toggle("is-on", idx === i);
        p.setAttribute("aria-pressed", idx === i ? "true" : "false");
      });
    }

    const histModal = document.getElementById("gundu-bet-history");
    const fsRoot = document.getElementById("gundu-fullscreen");
    const virt = document.getElementById("gundu-virt");
    const videoInline = document.getElementById("gundu-video");
    const videoFs = document.getElementById("gundu-video-fs");

    const streamBox = document.getElementById("gundu-stream-box");
    function openFs() {
      if (!fsRoot) return;
      fsRoot.hidden = false;
      streamBox?.classList.add("gundu-stream-box--fs");
      document.body.style.overflow = "hidden";
      videoInline?.pause();
      if (!videoFs) return;
      videoFs.poster = videoInline?.poster || "assets/banner_gundu.png";
      const srcEl = videoInline?.querySelector("source");
      const srcUrl = srcEl?.src || "assets/gunduata_live.mp4";
      const savedTime = videoInline?.currentTime || 0;
      let s = videoFs.querySelector("source");
      if (!s) { s = document.createElement("source"); videoFs.appendChild(s); }
      if (s.src !== srcUrl) {
        s.src = srcUrl;
        s.type = "video/mp4";
        videoFs.load();
        videoFs.addEventListener("canplay", function onReady() {
          videoFs.removeEventListener("canplay", onReady);
          videoFs.currentTime = savedTime;
          videoFs.play().catch(() => {});
        });
      } else {
        videoFs.currentTime = savedTime;
        videoFs.play().catch(() => {});
      }
    }
    function closeFs() {
      if (fsRoot) {
        fsRoot.hidden = true;
        streamBox?.classList.remove("gundu-stream-box--fs");
        if (videoFs && videoInline) {
          videoInline.currentTime = videoFs.currentTime || 0;
          if (document.documentElement.dataset.tab === "gundu") {
            videoInline.play().catch(() => {});
          }
        }
        document.body.style.overflow = "";
      }
    }

    panel.addEventListener("click", (e) => {
      const dice = e.target.closest(".gundu-dice");
      if (dice && panel.contains(dice) && !placing) {
        const face = +dice.getAttribute("data-gundu-face");
        focusedFace = face;
        const cur = stakes[face] | 0;
        const add = selectedChip;
        stakes[face] = cur + add;
        tapStack.push([face, add]);
        syncCard(face);
        syncPlace();
        return;
      }
      const chip = e.target.closest(".gundu-chip");
      if (chip && panel.querySelector("#gundu-chips")?.contains(chip)) {
        const v = +chip.getAttribute("data-amt");
        if (v) {
          selectedChip = v;
          syncChips();
        }
        return;
      }
      const pill = e.target.closest(".gundu-pill");
      if (pill) {
        const idx = +pill.getAttribute("data-gundu-region");
        setRegion(idx);
        if (idx === 1) {
          const f = document.getElementById("gundu-virt-frame");
          if (f) f.setAttribute("src", K ? K.gunduVirtualUrl() : "https://gunduata.club/game/index.html");
          virt && (virt.hidden = false);
          document.body.style.overflow = "hidden";
        }
        return;
      }
    });

    document.getElementById("gundu-undo")?.addEventListener("click", () => {
      if (tapStack.length === 0 || placing) return;
      const [face, amt] = tapStack.pop();
      const cur = (stakes[face] | 0) - amt;
      if (cur <= 0) delete stakes[face];
      else stakes[face] = cur;
      const last = tapStack.length ? tapStack[tapStack.length - 1][0] : null;
      focusedFace = last;
      syncAllCards();
      syncPlace();
    });

    document.getElementById("gundu-place-btn")?.addEventListener("click", async () => {
      if (placing || !hasAnyStake()) return;
      if (!K || !K.isAuthed()) {
        location.hash = "login";
        return;
      }
      if (K.isLocalDemo()) {
        window.alert("Demo account cannot place bets.");
        return;
      }
      const lineItems = [];
      for (let n = 1; n <= 6; n++) {
        const a = stakes[n] | 0;
        if (a > 0) lineItems.push([n, a]);
      }
      lineItems.sort((x, y) => x[0] - y[0]);
      placing = true;
      syncPlace();
      let lastBal = null;
      let errMsg = null;
      for (const [n, amount] of lineItems) {
        const { data, error } = await K.postGundataBet(n, amount);
        if (data && data.walletBalance) lastBal = data.walletBalance;
        if (error) {
          errMsg = error;
          break;
        }
      }
      for (let n = 1; n <= 6; n++) delete stakes[n];
      tapStack = [];
      focusedFace = null;
      syncAllCards();
      placing = false;
      syncPlace();
      if (lastBal) setBalanceDisplays(lastBal, lastBal);
      else await refreshAllBalances();
      if (errMsg) window.alert(errMsg);
      else window.alert(lineItems.length === 1 ? "Bet placed" : "Bets placed");
    });

    document.getElementById("gundu-open-bet-history")?.addEventListener("click", async () => {
      if (histModal) histModal.hidden = false;
      const list = document.getElementById("gundu-bet-history-list");
      const empty = document.getElementById("gundu-bet-history-empty");
      if (!K || !K.isAuthed() || K.isLocalDemo()) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = "Sign in with a real account to see your bets.";
        }
        if (list) {
          list.hidden = true;
          list.innerHTML = "";
        }
        return;
      }
      if (empty) empty.textContent = "Loading…";
      const { data, error } = await K.fetchGundataBetsMine();
      if (error) {
        if (empty) empty.textContent = error;
        if (list) {
          list.hidden = true;
        }
        return;
      }
      if (!data || !data.length) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = "No bets yet.";
        }
        if (list) {
          list.hidden = true;
          list.innerHTML = "";
        }
        return;
      }
      if (empty) empty.hidden = true;
      if (list) {
        list.hidden = false;
        list.innerHTML = data
          .map((b) => {
            return (
              "<li>#" +
              (b.id != null ? b.id : "") +
              " · Face " +
              (b.number != null ? b.number : "") +
              " · " +
              (b.chip_amount || "") +
              " · " +
              (b.status || "") +
              " · " +
              (b.created_at || "").replace("T", " ").slice(0, 16) +
              "</li>"
            );
          })
          .join("");
      }
    });
    document.getElementById("gundu-bet-history-close")?.addEventListener("click", () => {
      if (histModal) histModal.hidden = true;
    });
    document.getElementById("gundu-bet-history-backdrop")?.addEventListener("click", () => {
      if (histModal) histModal.hidden = true;
    });
    document.getElementById("gundu-fs-open")?.addEventListener("click", openFs);
    document.getElementById("gundu-fs-close")?.addEventListener("click", closeFs);
    document.getElementById("gundu-virt-close")?.addEventListener("click", () => {
      if (virt) virt.hidden = true;
      document.body.style.overflow = "";
      setRegion(0);
    });
    document.getElementById("gundu-virt-backdrop")?.addEventListener("click", () => {
      if (virt) virt.hidden = true;
      document.body.style.overflow = "";
      setRegion(0);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (fsRoot && !fsRoot.hidden) {
        e.preventDefault();
        closeFs();
      }
      if (histModal && !histModal.hidden) histModal.hidden = true;
      if (virt && !virt.hidden) {
        virt.hidden = true;
        document.body.style.overflow = "";
        setRegion(0);
      }
    });

    buildLastStrip();
    syncChips();
    syncAllCards();
    syncPlace();
    setRegion(0);
  })();
  (function initHomeBanner() {
    const wrap = document.getElementById("home-banner");
    if (!wrap) return;
    const slides = Array.from(wrap.querySelectorAll(".banner__link"));
    const dots = Array.from(wrap.querySelectorAll(".banner__dot"));
    if (slides.length < 2) return;
    let cur = 0;
    function goTo(idx) {
      slides[cur].classList.remove("banner__link--active");
      slides[cur].setAttribute("aria-hidden", "true");
      slides[cur].setAttribute("tabindex", "-1");
      dots[cur].classList.remove("banner__dot--on");
      cur = (idx + slides.length) % slides.length;
      slides[cur].classList.add("banner__link--active");
      slides[cur].removeAttribute("aria-hidden");
      slides[cur].removeAttribute("tabindex");
      dots[cur].classList.add("banner__dot--on");
    }
    dots.forEach((d, i) => d.addEventListener("click", () => { goTo(i); clearInterval(timer); timer = setInterval(() => goTo(cur + 1), 3500); }));
    let timer = setInterval(() => goTo(cur + 1), 3500);
    wrap.addEventListener("mouseenter", () => clearInterval(timer));
    wrap.addEventListener("mouseleave", () => { timer = setInterval(() => goTo(cur + 1), 3500); });

    /* Touch / mouse swipe support */
    let startX = 0, startY = 0, dragging = false;
    function onDragStart(x, y) { startX = x; startY = y; dragging = true; }
    function onDragEnd(x, y) {
      if (!dragging) return;
      dragging = false;
      const dx = x - startX;
      const dy = y - startY;
      if (Math.abs(dx) < 30 || Math.abs(dx) < Math.abs(dy)) return; /* too short or mostly vertical */
      clearInterval(timer);
      goTo(dx < 0 ? cur + 1 : cur - 1);
      timer = setInterval(() => goTo(cur + 1), 3500);
    }
    wrap.addEventListener("touchstart", (e) => { const t = e.touches[0]; onDragStart(t.clientX, t.clientY); }, { passive: true });
    wrap.addEventListener("touchend",   (e) => { const t = e.changedTouches[0]; onDragEnd(t.clientX, t.clientY); }, { passive: true });
    wrap.addEventListener("mousedown",  (e) => onDragStart(e.clientX, e.clientY));
    wrap.addEventListener("mouseup",    (e) => onDragEnd(e.clientX, e.clientY));
  })();
  (function initCockfight() {
    function setCfSide(side) {
      ["cockfight-side-bar", "cockfight-fs-side-bar"].forEach((id) => {
        const bar = document.getElementById(id);
        if (!bar) return;
        bar.querySelectorAll(".cockfight-side-btn").forEach((b) => {
          const on = b.getAttribute("data-cf-side") === side;
          b.classList.toggle("is-selected", on);
          b.setAttribute("aria-pressed", on ? "true" : "false");
        });
      });
    }
    function setCfAmt(amtStr) {
      ["cock-chips", "cockfight-fs-chips"].forEach((id) => {
        const root = document.getElementById(id);
        if (!root) return;
        root.querySelectorAll(".cock-chip").forEach((c) => {
          const on = c.getAttribute("data-amt") === String(amtStr);
          c.classList.toggle("is-on", on);
        });
      });
    }
    function syncBodyScrollLock() {
      const fsDlg = document.getElementById("cockfight-fullscreen");
      const mainSheet = document.getElementById("cf-bet-sheet-main");
      const fsSheet = document.getElementById("cf-bet-sheet-fs");
      const fsUi = fsDlg && !fsDlg.hidden;
      const msOpen = mainSheet && !mainSheet.hidden;
      const fssOpen = fsSheet && !fsSheet.hidden;
      if (fsUi || msOpen || fssOpen) document.body.style.overflow = "hidden";
      else document.body.style.overflow = "";
    }
    function closeCfBetSheet(context) {
      const sheet =
        context === "fs"
          ? document.getElementById("cf-bet-sheet-fs")
          : document.getElementById("cf-bet-sheet-main");
      if (sheet) sheet.hidden = true;
      syncBodyScrollLock();
    }
    window.__closeCfMainBetSheet = () => closeCfBetSheet("main");
    window.__closeCfFsBetSheet = () => closeCfBetSheet("fs");

    function syncCfFsFromMain() {
      const mainBar = document.getElementById("cockfight-side-bar");
      const sel = mainBar && mainBar.querySelector(".cockfight-side-btn.is-selected");
      const side = sel ? sel.getAttribute("data-cf-side") : "COCK1";
      setCfSide(side || "COCK1");
      const mainChips = document.getElementById("cock-chips");
      const chipOn = mainChips && mainChips.querySelector(".cock-chip.is-on");
      const amt = chipOn ? chipOn.getAttribute("data-amt") : "100";
      setCfAmt(amt || "100");
    }
    function syncCfMainFromFs() {
      const fsBar = document.getElementById("cockfight-fs-side-bar");
      const sel = fsBar && fsBar.querySelector(".cockfight-side-btn.is-selected");
      const side = sel ? sel.getAttribute("data-cf-side") : "COCK1";
      setCfSide(side || "COCK1");
      const fsChips = document.getElementById("cockfight-fs-chips");
      const chipOn = fsChips && fsChips.querySelector(".cock-chip.is-on");
      const amt = chipOn ? chipOn.getAttribute("data-amt") : "100";
      setCfAmt(amt || "100");
    }
    window.__cockfightSyncFsFromMain = syncCfFsFromMain;
    window.__cockfightSyncMainFromFs = syncCfMainFromFs;

    function updateBetSheetTitle(btn, titleEl) {
      const label =
        (btn && (btn.getAttribute("data-cf-display") || btn.getAttribute("data-cf-side"))) || "";
      const odd = (btn && btn.getAttribute("data-cf-odd")) || "";
      if (titleEl) titleEl.textContent = label + " · " + odd + "×";
    }
    function openCfBetSheet(context, triggerBtn) {
      const sheet =
        context === "fs"
          ? document.getElementById("cf-bet-sheet-fs")
          : document.getElementById("cf-bet-sheet-main");
      const titleEl =
        context === "fs"
          ? document.getElementById("cf-bet-sheet-fs-title")
          : document.getElementById("cf-bet-sheet-main-title");
      if (!sheet || !triggerBtn) return;
      updateBetSheetTitle(triggerBtn, titleEl);
      sheet.hidden = false;
      syncBodyScrollLock();
    }

    ["cockfight-side-bar", "cockfight-fs-side-bar"].forEach((barId) => {
      const bar = document.getElementById(barId);
      if (!bar) return;
      bar.addEventListener("click", (e) => {
        const btn = e.target.closest(".cockfight-side-btn");
        if (!btn || !bar.contains(btn)) return;
        const side = btn.getAttribute("data-cf-side");
        if (side) setCfSide(side);
        /* Only open sheet for fullscreen mode; main layout has inline chips */
        if (barId.includes("fs")) {
          openCfBetSheet("fs", btn);
        }
      });
    });
    ["cock-chips", "cockfight-fs-chips"].forEach((id) => {
      const chips = document.getElementById(id);
      if (!chips) return;
      chips.addEventListener("click", (e) => {
        const c = e.target.closest(".cock-chip");
        if (!c || !chips.contains(c)) return;
        const amt = c.getAttribute("data-amt");
        if (amt) setCfAmt(amt);
      });
    });

    document.getElementById("cf-bet-sheet-main-bd")?.addEventListener("click", () => closeCfBetSheet("main"));
    document.getElementById("cf-bet-sheet-main-close")?.addEventListener("click", () => closeCfBetSheet("main"));
    document.getElementById("cf-bet-sheet-fs-bd")?.addEventListener("click", () => closeCfBetSheet("fs"));
    document.getElementById("cf-bet-sheet-fs-close")?.addEventListener("click", () => closeCfBetSheet("fs"));

    /** `data-cf-side` → POST body side (canonical; legacy Meron/Wala/Draw still accepted here). */
    const uiSideToCanonical = {
      COCK1: "COCK1",
      COCK2: "COCK2",
      DRAW: "DRAW",
      Meron: "COCK1",
      Wala: "COCK2",
      Draw: "DRAW",
    };
    function getCfBetContext() {
      const fsDlg = document.getElementById("cockfight-fullscreen");
      const fsSheet = document.getElementById("cf-bet-sheet-fs");
      if (fsDlg && !fsDlg.hidden && fsSheet && !fsSheet.hidden) return "fs";
      /* Main layout now always visible — always return main */
      return "main";
    }
    async function placeCockfightBet() {
      const ctx = getCfBetContext();
      const bar =
        ctx === "fs"
          ? document.getElementById("cockfight-fs-side-bar")
          : document.getElementById("cockfight-side-bar");
      const chipRoot =
        ctx === "fs" ? document.getElementById("cockfight-fs-chips") : document.getElementById("cock-chips");
      const sideEl = bar && bar.querySelector(".cockfight-side-btn.is-selected");
      if (!sideEl) {
        window.alert("Pick Cock 1, Draw, or Cock 2");
        return;
      }
      if (!K || !K.isAuthed()) {
        location.hash = "login";
        return;
      }
      if (K.isLocalDemo()) {
        window.alert("Demo account cannot place bets.");
        return;
      }
      const lab = sideEl.getAttribute("data-cf-side");
      const apiSide = uiSideToCanonical[lab] ?? "COCK1";
      const chip = chipRoot && chipRoot.querySelector(".cock-chip.is-on");
      const amt = parseInt(chip ? chip.getAttribute("data-amt") : "100", 10) || 100;
      const { data, error } = await K.postMeronWalaBet(apiSide, amt);
      if (error) window.alert(error);
      else {
        if (data && data.walletBalance) setBalanceDisplays(data.walletBalance, data.walletBalance);
        else await refreshAllBalances();
        window.alert("Bet placed");
        closeCfBetSheet(ctx);
      }
    }
    document.getElementById("cock-place-btn")?.addEventListener("click", placeCockfightBet);
    document.getElementById("cockfight-fs-place-btn")?.addEventListener("click", placeCockfightBet);

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const ms = document.getElementById("cf-bet-sheet-main");
      const fss = document.getElementById("cf-bet-sheet-fs");
      if (fss && !fss.hidden) {
        e.preventDefault();
        closeCfBetSheet("fs");
        return;
      }
      if (ms && !ms.hidden) {
        e.preventDefault();
        closeCfBetSheet("main");
      }
    });
    const hModal = document.getElementById("cf-history");
    const openH = async () => {
      if (hModal) hModal.hidden = false;
      const list = document.getElementById("cf-history-list");
      const empty = document.getElementById("cf-history-empty");
      if (!K || !K.isAuthed() || K.isLocalDemo()) {
        if (empty) {
          empty.hidden = false;
          empty.querySelector("p").textContent = "Sign in with a real account to see bet history.";
        }
        if (list) {
          list.hidden = true;
          list.innerHTML = "";
        }
        return;
      }
      const { data, error } = await K.fetchMeronWalaBetsMine();
      if (error) {
        if (empty) {
          empty.hidden = false;
          empty.querySelector("p").textContent = error;
        }
        if (list) list.hidden = true;
        return;
      }
      if (!data || !data.length) {
        if (empty) {
          empty.hidden = false;
          empty.querySelector("p").textContent = "No bets placed yet";
        }
        if (list) {
          list.hidden = true;
          list.innerHTML = "";
        }
        return;
      }
      if (empty) empty.hidden = true;
      if (list) {
        list.hidden = false;
        list.innerHTML = data
          .map(
            (b) =>
              "<li>" +
              (cockfightBetSideDisplay(b).toUpperCase()) +
              " · ₹" +
              (b.stake != null ? b.stake : "") +
              " · " +
              (b.status || "") +
              " · " +
              String(b.created_at || "")
                .replace("T", " ")
                .slice(0, 19) +
              "</li>"
          )
          .join("");
      }
    };
    const closeH = () => hModal && (hModal.hidden = true);
    document.getElementById("cock-open-history")?.addEventListener("click", openH);
    document.getElementById("cockfight-fs-open-history")?.addEventListener("click", openH);
    document.getElementById("cf-history-close")?.addEventListener("click", closeH);
    document.getElementById("cf-history-backdrop")?.addEventListener("click", closeH);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && hModal && !hModal.hidden) closeH();
    });
  })();

  document.getElementById("referral-share-row")?.addEventListener("click", () => {
    const btn = document.getElementById("referral-copy-btn");
    const code = (btn && btn.getAttribute("data-copy")) ? btn.getAttribute("data-copy").trim() : "";
    const text = code ? `Join me on Kokoroko! Code: ${code}` : "Join me on Kokoroko!";
    if (navigator.share) {
      navigator.share({ title: "Kokoroko", text }).catch(() => {});
    } else {
      window.alert(text);
    }
  });

  function setPwToggle(input, btn) {
    if (!input || !btn) return;
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.setAttribute("title", show ? "Hide password" : "Show password");
    });
  }
  setPwToggle(document.getElementById("login-pass"), document.getElementById("login-pass-toggle"));
  setPwToggle(document.getElementById("reg-pass"), document.getElementById("reg-pass-toggle"));

  document.getElementById("reg-phone")?.addEventListener("input", (e) => {
    e.target.value = e.target.value.replace(/\D/g, "").slice(0, 15);
  });

  document.getElementById("login-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const u = document.getElementById("login-user");
    const p = document.getElementById("login-pass");
    const err = document.getElementById("login-err");
    const btn = document.getElementById("login-submit");
    const btnTxt = btn && btn.querySelector(".ap-pill__txt");
    function showErr(msg) {
      if (err) { err.textContent = msg; err.hidden = false; }
    }
    function setBusy(busy) {
      if (!btn) return;
      btn.disabled = busy;
      btn.setAttribute("aria-busy", busy ? "true" : "false");
      if (btnTxt) btnTxt.textContent = busy ? "Logging in…" : "Login";
    }
    if (!K) { showErr("Page error — please refresh the page."); return; }
    if (!u || !p) return;
    if (!u.value.trim()) { showErr("Please enter your phone number or username."); return; }
    if (!p.value) { showErr("Please enter your password."); return; }
    if (err) err.hidden = true;
    setBusy(true);
    try {
      const res = await K.login(u.value, p.value);
      setBusy(false);
      if (res.ok) {
        location.hash = "home";
        u.value = "";
        p.value = "";
      } else {
        showErr(res.error || "Sign in failed. Check your credentials.");
      }
    } catch (ex) {
      setBusy(false);
      showErr("Network error — please try again.");
    }
  });

  document.getElementById("register-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const elU = document.getElementById("reg-username");
    const elP = document.getElementById("reg-phone");
    const elPw = document.getElementById("reg-pass");
    const err = document.getElementById("register-err");
    const regBtn = document.getElementById("register-submit");
    const regBtnTxt = regBtn && regBtn.querySelector(".ap-pill__txt--solo");
    if (!K || !elU || !elP || !elPw) return;
    if (err) err.hidden = true;
    if (regBtn) { regBtn.disabled = true; if (regBtnTxt) regBtnTxt.textContent = "Creating…"; }
    const res = await K.register({
      username: elU.value,
      phone: elP.value,
      password: elPw.value
    });
    if (regBtn) { regBtn.disabled = false; if (regBtnTxt) regBtnTxt.textContent = "Create account"; }
    if (res.ok) {
      if (elO) elO.value = "";
      if (res.autologin) {
        /* Backend issued tokens -- go straight to home */
        location.hash = "home";
      } else {
        window.alert("Account created. Please log in.");
        location.hash = "login";
      }
    } else {
      if (err) {
        err.style.color = "";
        err.textContent = res.error || "Could not create account";
        err.hidden = false;
      } else {
        window.alert(res.error || "Could not create account");
      }
    }
  });

  window.addEventListener("hashchange", onHash);
  onHash();

  /* APK download banner — Android only, show after 3 s on every page load */
  (function setupApkBanner() {
    const banner = document.getElementById("apk-banner");
    const closeBtn = document.getElementById("apk-banner-close");
    if (!banner) return;
    /* Hide entirely on Apple devices — APK doesn't work on iOS/iPadOS */
    const ua = navigator.userAgent || "";
    const isApple = /iPhone|iPad|iPod|Macintosh/i.test(ua);
    if (isApple) { banner.hidden = true; return; }
    setTimeout(() => {
      banner.classList.add("apk-banner--visible");
    }, 3000);
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        banner.hidden = true;
      });
    }
  })();
})();
