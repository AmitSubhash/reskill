/* reSkill landing -- progressive-enhancement JS.
 * Everything degrades cleanly if JS fails or is disabled. */

(function () {
  "use strict";

  /* Custom cursor (sage circle with inertial follow, morphs over links/mono). */
  const cursor = document.querySelector(".cursor");
  const isFinePointer = window.matchMedia("(pointer: fine)").matches;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (cursor && isFinePointer) {
    let targetX = 0, targetY = 0;
    let curX = 0, curY = 0;
    let hasMoved = false;
    const stiffness = reducedMotion ? 1 : 0.22;

    document.addEventListener("pointermove", (e) => {
      targetX = e.clientX;
      targetY = e.clientY;
      if (!hasMoved) {
        curX = targetX;
        curY = targetY;
        cursor.classList.add("visible");
        hasMoved = true;
      }
    }, { passive: true });

    document.addEventListener("pointerleave", () => cursor.classList.remove("visible"));
    document.addEventListener("pointerenter", () => { if (hasMoved) cursor.classList.add("visible"); });
    document.addEventListener("pointerdown", () => cursor.classList.add("press"));
    document.addEventListener("pointerup", () => cursor.classList.remove("press"));
    document.addEventListener("selectstart", () => cursor.classList.remove("visible"));
    document.addEventListener("selectionchange", () => {
      const sel = window.getSelection && window.getSelection();
      if (sel && sel.toString().length > 0) cursor.classList.remove("visible");
      else if (hasMoved) cursor.classList.add("visible");
    });

    const linkTargets = "a, button, summary, kbd";
    const monoTargets = "code, pre, .install, .mono-block";
    document.addEventListener("pointerover", (e) => {
      const t = e.target;
      if (t.closest && t.closest(linkTargets)) cursor.classList.add("link");
      else if (t.closest && t.closest(monoTargets)) cursor.classList.add("mono");
    });
    document.addEventListener("pointerout", (e) => {
      const t = e.target;
      if (t.closest && t.closest(linkTargets)) cursor.classList.remove("link");
      if (t.closest && t.closest(monoTargets)) cursor.classList.remove("mono");
    });

    function tick() {
      curX += (targetX - curX) * stiffness;
      curY += (targetY - curY) * stiffness;
      cursor.style.transform = `translate(${curX}px, ${curY}px) translate(-50%, -50%)`;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* Copy button. */
  const copyBtn = document.getElementById("copy-btn");
  const copyLabel = document.getElementById("copy-label");
  const installCmd = document.getElementById("install-cmd");
  const installBlock = document.getElementById("install-primary");
  if (copyBtn && installCmd && copyLabel) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(installCmd.textContent.trim());
        copyLabel.textContent = "copied";
        if (installBlock) installBlock.classList.add("copied");
        setTimeout(() => {
          copyLabel.textContent = "copy";
          if (installBlock) installBlock.classList.remove("copied");
        }, 1400);
      } catch (e) {
        copyLabel.textContent = "err";
      }
    });
  }

  /* Install block caret pauses on hover. */
  document.querySelectorAll(".install").forEach((el) => {
    el.addEventListener("pointerenter", () => el.classList.add("paused"));
    el.addEventListener("pointerleave", () => el.classList.remove("paused"));
  });

  /* Section title settle-in via IntersectionObserver. */
  if ("IntersectionObserver" in window && !reducedMotion) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    document.querySelectorAll("main > section").forEach((s) => io.observe(s));
  } else {
    document.querySelectorAll("main > section").forEach((s) => s.classList.add("visible"));
  }

  /* Easter egg: typing "reskill" flashes the tagline word "skill". */
  let buf = "";
  const target = "reskill";
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (!/^[a-z]$/i.test(e.key)) { buf = ""; return; }
    buf = (buf + e.key.toLowerCase()).slice(-target.length);
    if (buf === target) {
      const em = document.querySelector(".hero h1 em");
      if (em) {
        em.classList.remove("flash");
        void em.offsetWidth; /* reflow to restart animation */
        em.classList.add("flash");
      }
      buf = "";
    }
  });

  /* Sticky-nav visual state. */
  const nav = document.querySelector(".topnav");
  if (nav) {
    const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }
})();
