/* reSkill v2 editorial. Vanilla JS, no build step.
   Handles: theme toggle, live clock, interactive quiz demo, install copy. */

(function () {
  "use strict";

  // ───────── theme toggle ─────────
  const toggle = document.getElementById("theme-toggle");
  const themeLabel = toggle && toggle.querySelector(".theme-label");
  function applyTheme(t) {
    document.documentElement.classList.toggle("dark", t === "dark");
    document.documentElement.classList.toggle("light", t !== "dark");
    if (themeLabel) themeLabel.textContent = t === "dark" ? "dark" : "light";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = t === "dark" ? "#14141a" : "#f7f5ef";
  }
  function currentTheme() {
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  }
  applyTheme(currentTheme());
  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem("reskill-theme", next);
    });
  }
  // Follow OS changes when the user hasn't picked.
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", (e) => {
    if (!localStorage.getItem("reskill-theme")) {
      applyTheme(e.matches ? "dark" : "light");
    }
  });

  // ───────── live clock ─────────
  const clock = document.getElementById("clock");
  if (clock) {
    function tick() {
      const d = new Date();
      const hh = String(d.getHours()).padStart(2, "0");
      const mm = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      clock.innerHTML = `${hh}:${mm}<span style="color:var(--rule-strong)">:${ss}</span>`;
    }
    tick();
    setInterval(tick, 1000);
  }

  // ───────── copy button ─────────
  const copyBtn = document.getElementById("copy-btn");
  const cmdText = document.getElementById("install-cmd-text");
  if (copyBtn && cmdText) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(cmdText.textContent.trim());
        copyBtn.textContent = "copied";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyBtn.textContent = "copy";
          copyBtn.classList.remove("copied");
        }, 1400);
      } catch (e) {
        copyBtn.textContent = "err";
      }
    });
  }

  // ───────── interactive quiz demo ─────────
  const QUESTIONS = [
    {
      context: "reading reskill/cache.py, line 42",
      prompt: "Why does @lru_cache leak memory in long-running workers?",
      options: [
        "Unlimited cache by default in modern Python",
        "User objects aren't hashable",
        "db.query returns a new object each call",
        "lru_cache should go on methods",
      ],
      correct: 0,
      explain: "maxsize defaults to 128 but wraps self, pinning instances for the process lifetime.",
    },
    {
      context: "PreToolUse, Bash(pytest -k async_)",
      prompt: "What does asyncio.gather do when one task raises?",
      options: [
        "Cancels siblings and returns partial results",
        "Returns exceptions in the results list",
        "Propagates the first exception, siblings keep running",
        "Swallows the exception silently",
      ],
      correct: 2,
      explain: "Siblings aren't cancelled unless return_exceptions=False and you await the future tree.",
    },
    {
      context: "last commit, 17 min ago",
      prompt: "git rebase --onto main feature~3 feature does what?",
      options: [
        "Moves the last 3 commits of feature onto main",
        "Rebases all of feature onto main",
        "Squashes feature into main",
        "Cherry-picks feature~3 onto main",
      ],
      correct: 0,
      explain: "--onto <new> <old-base> <branch>, replay commits since <old-base> onto <new>.",
    },
    {
      context: "UserPromptSubmit, fix tmux layout",
      prompt: "Which tmux binding splits the window vertically by default?",
      options: ["prefix + v", "prefix + %", "prefix + |", "prefix + s"],
      correct: 1,
      explain: '% is the vertical split (left and right); " is horizontal.',
    },
  ];

  const pane = document.getElementById("quiz-pane");
  if (!pane) return;

  const state = {
    idx: 0,
    answer: null,
    streak: 3,
    skipped: 0,
    muted: false,
    elapsed: 0,
  };

  let ticker = null;
  function startTicker() {
    stopTicker();
    ticker = setInterval(() => {
      if (state.answer !== null) return;
      state.elapsed += 1;
      render();
    }, 1000);
  }
  function stopTicker() {
    if (ticker) { clearInterval(ticker); ticker = null; }
  }

  function pick(i) {
    if (state.answer !== null) return;
    state.answer = i;
    const q = QUESTIONS[state.idx];
    state.streak = i === q.correct ? state.streak + 1 : 0;
    render();
  }
  function skip() {
    state.skipped += 1;
    next();
  }
  function next() {
    state.answer = null;
    state.elapsed = 0;
    state.idx = (state.idx + 1) % QUESTIONS.length;
    render();
  }
  function toggleMute() {
    state.muted = !state.muted;
    render();
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function render() {
    const q = QUESTIONS[state.idx];
    const reveal = state.answer !== null;
    const thinkingLabel = reveal
      ? (state.answer === q.correct ? "&check; correct" : "&times; missed")
      : `claude thinking, <span class="tabnum">${String(state.elapsed).padStart(2, "0")}s</span>`;
    const streakLabel = state.muted ? "muted" : `streak ${state.streak}`;

    const opts = q.options
      .map((opt, i) => {
        const right = i === q.correct;
        const picked = state.answer === i;
        const cls = reveal ? (right ? "right" : picked ? "wrong" : "dim") : "";
        const mark = reveal && right ? "&check;" : reveal && picked ? "&times;" : "";
        return `
          <li class="quiz-opt ${cls}">
            <button type="button" data-pick="${i}" ${reveal ? "disabled" : ""}>
              <span class="opt-num">${i + 1}</span>
              <span class="opt-text">${esc(opt)}</span>
              <span class="opt-mark" aria-hidden="true">${mark}</span>
            </button>
          </li>`;
      })
      .join("");

    const explain = reveal
      ? `<div class="quiz-explain">
           <span class="quiz-explain-label">why</span>
           <span>${esc(q.explain)}</span>
         </div>`
      : "";

    const footer = reveal
      ? `<button class="quiz-link primary" data-act="next"><kbd>&crarr;</kbd> next question</button>
         <span class="sep">&middot;</span>
         <span class="quiz-meta">${state.idx + 1} of ${QUESTIONS.length}, ${state.skipped} skipped</span>`
      : `<span><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd><kbd>4</kbd> answer</span>
         <span class="sep">&middot;</span>
         <button class="quiz-link" data-act="skip"><kbd>x</kbd> skip</button>
         <span class="sep">&middot;</span>
         <button class="quiz-link" data-act="mute"><kbd>X</kbd> ${state.muted ? "unmute" : "mute"}</button>`;

    pane.innerHTML = `
      <div class="quiz-bar">
        <span class="quiz-dot" aria-hidden="true"></span>
        <span class="quiz-title">reskill, quiz pane</span>
        <span class="quiz-bar-sep">&middot;</span>
        <span class="quiz-meta">${streakLabel}</span>
        <span class="quiz-bar-spacer"></span>
        <span class="quiz-meta thinking">${thinkingLabel}</span>
      </div>
      <div class="quiz-body">
        <div class="quiz-context">&#x2503; ${esc(q.context)}</div>
        <div class="quiz-prompt">${esc(q.prompt)}</div>
        <ol class="quiz-options">${opts}</ol>
        ${explain}
        <div class="quiz-footer">${footer}</div>
      </div>`;

    pane.querySelectorAll("[data-pick]").forEach((el) => {
      el.addEventListener("click", () => pick(Number(el.dataset.pick)));
    });
    const act = {
      skip, mute: toggleMute, next,
    };
    pane.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", () => act[el.dataset.act]());
    });
  }

  render();
  startTicker();

  // Global keyboard shortcuts (only when focus isn't on a form field).
  document.addEventListener("keydown", (e) => {
    const tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const k = e.key;
    if (["1", "2", "3", "4"].includes(k)) { pick(Number(k) - 1); e.preventDefault(); }
    else if (k === "x") { skip(); e.preventDefault(); }
    else if (k === "X") { toggleMute(); e.preventDefault(); }
    else if (k === "Enter" && state.answer !== null) { next(); e.preventDefault(); }
  });
})();
