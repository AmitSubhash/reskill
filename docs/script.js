/**
 * reSkill landing -- minimal progressive-enhancement JS.
 *
 * Everything degrades cleanly: if JS is disabled, the site still reads
 * as a beautiful static page (except the 3D cube, which is its own
 * module in hero-cube.js).
 */

(function () {
  "use strict";

  // 1. Sticky nav shadow on scroll
  const nav = document.querySelector(".nav");
  if (nav) {
    const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // 2. Copy-button for the install command
  const copyBtn = document.getElementById("copy-btn");
  const copyLabel = document.getElementById("copy-label");
  const installCmd = document.getElementById("install-cmd");
  if (copyBtn && installCmd && copyLabel) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(installCmd.textContent.trim());
        copyLabel.textContent = "copied";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyLabel.textContent = "copy";
          copyBtn.classList.remove("copied");
        }, 1800);
      } catch (e) {
        copyLabel.textContent = "err";
      }
    });
  }

  // 3. IntersectionObserver fade-in on sections
  const faders = document.querySelectorAll(
    ".step, .feat, .video-frame, .install-inner",
  );
  if ("IntersectionObserver" in window) {
    faders.forEach((el) => {
      el.style.opacity = "0";
      el.style.transform = "translateY(20px)";
      el.style.transition =
        "opacity 600ms ease, transform 600ms cubic-bezier(0.2, 0.8, 0.2, 1)";
    });
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -80px 0px" },
    );
    faders.forEach((el) => io.observe(el));
  }
})();
