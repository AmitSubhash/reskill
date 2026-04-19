/**
 * Hero 3D: rotating glass terminal cube. Each face is a 2D canvas
 * drawn to look like a reSkill screen (quiz / streak / reveal). The
 * canvases are used as textures on the six faces of a RoundedBox.
 *
 * Pure ES modules, loaded via importmap from index.html. No build
 * step, no bundler. Ships as-is to GitHub Pages.
 */

import * as THREE from "three";

const EVERGREEN = {
  bg: "#0e1117",
  bgPanel: "#1a1f24",
  ink: "#d3c6aa",
  inkDim: "#9caaa4",
  sage: "#a7c080",
  teal: "#7fbbb3",
  gold: "#dbbc7f",
  rose: "#e67e80",
};

const FACE_SIZE = 512; // texture resolution per face

/** Draw the contents of a single cube face onto a 2D canvas texture. */
function drawFace(kind) {
  const canvas = document.createElement("canvas");
  canvas.width = FACE_SIZE;
  canvas.height = FACE_SIZE;
  const ctx = canvas.getContext("2d");

  // Background
  ctx.fillStyle = EVERGREEN.bg;
  ctx.fillRect(0, 0, FACE_SIZE, FACE_SIZE);

  // Subtle noise
  for (let i = 0; i < 600; i++) {
    ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.015})`;
    ctx.fillRect(
      Math.random() * FACE_SIZE,
      Math.random() * FACE_SIZE,
      1,
      1,
    );
  }

  const draw = FACE_RENDERERS[kind];
  if (draw) draw(ctx);

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const FACE_RENDERERS = {
  question(ctx) {
    const pad = 32;
    // title bar
    ctx.fillStyle = EVERGREEN.teal;
    ctx.font = "bold 20px 'Geist Mono', ui-monospace, monospace";
    ctx.fillText("┃ think about this", pad, pad + 18);

    // question
    ctx.fillStyle = EVERGREEN.ink;
    ctx.font = "bold 26px 'Geist', 'Inter', sans-serif";
    wrapText(
      ctx,
      "Why does @lru_cache leak memory in long workers?",
      pad,
      pad + 70,
      FACE_SIZE - pad * 2,
      32,
    );

    // code
    const codeY = pad + 170;
    ctx.fillStyle = EVERGREEN.bgPanel;
    roundRect(ctx, pad, codeY, FACE_SIZE - pad * 2, 84, 10);
    ctx.fill();
    ctx.fillStyle = EVERGREEN.teal;
    ctx.font = "16px 'Geist Mono', monospace";
    ctx.fillText("@lru_cache", pad + 16, codeY + 26);
    ctx.fillText("def get_user(user: User) -> dict:", pad + 16, codeY + 50);
    ctx.fillText("    return db.query(...).first()", pad + 16, codeY + 74);

    // options
    const opts = [
      ["1)", "unlimited cache by default in modern Python", true],
      ["2)", "User objects aren't hashable", false],
      ["3)", "db.query returns a new object each call", false],
      ["4)", "lru_cache should go on methods", false],
    ];
    let y = codeY + 115;
    ctx.font = "16px 'Geist', sans-serif";
    opts.forEach(([num, text, correct]) => {
      ctx.fillStyle = EVERGREEN.sage;
      ctx.font = "bold 16px 'Geist Mono', monospace";
      ctx.fillText(num, pad, y);
      ctx.fillStyle = correct ? EVERGREEN.sage : EVERGREEN.ink;
      ctx.font = `${correct ? "600" : "400"} 16px 'Geist', sans-serif`;
      wrapText(ctx, text, pad + 32, y, FACE_SIZE - pad - 32, 22);
      y += 42;
    });
  },

  reveal(ctx) {
    const pad = 32;
    // gold-border feel for the "good to know" reveal
    ctx.strokeStyle = EVERGREEN.gold;
    ctx.lineWidth = 2;
    roundRect(ctx, pad - 4, pad - 4, FACE_SIZE - pad * 2 + 8, FACE_SIZE - pad * 2 + 8, 12);
    ctx.stroke();

    ctx.fillStyle = EVERGREEN.gold;
    ctx.font = "bold 20px 'Geist Mono', monospace";
    ctx.fillText("── good to know ──", pad, pad + 20);

    // big check
    ctx.fillStyle = EVERGREEN.sage;
    ctx.font = "bold 140px 'Geist', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("✓", FACE_SIZE / 2, FACE_SIZE / 2 + 10);
    ctx.textAlign = "start";

    ctx.fillStyle = EVERGREEN.ink;
    ctx.font = "22px 'Geist', sans-serif";
    wrapText(
      ctx,
      "bare @lru_cache defaults to unlimited in modern Python -- set maxsize explicitly.",
      pad,
      FACE_SIZE - 150,
      FACE_SIZE - pad * 2,
      28,
    );

    ctx.fillStyle = EVERGREEN.gold;
    ctx.font = "bold 18px 'Geist Mono', monospace";
    ctx.fillText("◉ sticky one · high-confidence miss", pad, FACE_SIZE - 50);
  },

  streak(ctx) {
    const pad = 32;
    // header
    ctx.fillStyle = EVERGREEN.gold;
    ctx.font = "bold 24px 'Geist', sans-serif";
    ctx.fillText("🔥 day 5 streak", pad, pad + 28);

    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "18px 'Geist', sans-serif";
    ctx.fillText("12 mastered · 24 in progress · 14 new", pad, pad + 58);

    // heatmap grid
    const cols = 14;
    const rows = 7;
    const gridW = FACE_SIZE - pad * 2;
    const cell = (gridW - (cols - 1) * 4) / cols;
    const tiers = [
      0,0,0,0,0,0,0,
      1,0,1,0,0,0,0,
      2,1,2,0,1,0,1,
      2,2,2,1,0,0,0,
      2,2,2,2,1,1,0,
      2,2,2,2,2,0,0,
      2,2,2,2,2,1,0,
      2,1,2,2,2,0,0,
      2,2,2,2,2,1,1,
      2,2,2,2,2,2,1,
      2,2,2,2,2,2,2,
      2,2,2,1,0,0,0,
      2,1,0,0,0,0,0,
      1,0,0,0,0,0,0,
    ];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const tier = tiers[c * rows + r] ?? 0;
        const color =
          tier === 2 ? EVERGREEN.sage : tier === 1 ? EVERGREEN.gold : "rgba(255,255,255,0.06)";
        ctx.fillStyle = color;
        ctx.globalAlpha = tier === 2 ? 0.85 : tier === 1 ? 0.55 : 1;
        const x = pad + c * (cell + 4);
        const y = pad + 100 + r * (cell + 4);
        roundRect(ctx, x, y, cell, cell, 3);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;

    // footer
    ctx.fillStyle = EVERGREEN.ink;
    ctx.font = "bold 22px 'Geist', sans-serif";
    ctx.fillText("+10 xp", pad, FACE_SIZE - 70);
    ctx.fillStyle = EVERGREEN.sage;
    ctx.font = "bold 22px 'Geist', sans-serif";
    ctx.fillText("4/5 today", pad + 110, FACE_SIZE - 70);

    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "16px 'Geist Mono', monospace";
    ctx.fillText("$ reskill streak", pad, FACE_SIZE - 30);
  },

  session(ctx) {
    const pad = 32;
    // header
    ctx.fillStyle = EVERGREEN.teal;
    ctx.font = "bold 22px 'Geist', sans-serif";
    ctx.fillText("reSkill", pad, pad + 24);
    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "18px 'Geist', sans-serif";
    ctx.fillText("session · from your last 14 days", pad, pad + 50);

    // commit chip list
    const commits = [
      ["from ad4e688", "DECSTBM scroll-region overlay"],
      ["from 8fd11c8", "hero GIF inline in README"],
      ["from 009f9ac", "ship the launch videos"],
      ["from c2926dd", "rewrite 20 questions for depth"],
    ];
    let y = pad + 100;
    commits.forEach(([sha, msg]) => {
      ctx.fillStyle = EVERGREEN.teal;
      ctx.font = "bold 16px 'Geist Mono', monospace";
      ctx.fillText(sha, pad, y);
      ctx.fillStyle = EVERGREEN.ink;
      ctx.font = "16px 'Geist', sans-serif";
      ctx.fillText(msg, pad + 140, y);
      y += 32;
    });

    // score
    y += 12;
    ctx.fillStyle = EVERGREEN.sage;
    ctx.font = "bold 28px 'Geist', sans-serif";
    ctx.fillText("3 nailed", pad, y);
    ctx.fillStyle = EVERGREEN.rose;
    ctx.fillText("1 tricky", pad + 160, y);

    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "16px 'Geist Mono', monospace";
    ctx.fillText("$ reskill session --since 14d", pad, FACE_SIZE - 30);
  },

  topics(ctx) {
    const pad = 32;
    ctx.fillStyle = EVERGREEN.teal;
    ctx.font = "bold 22px 'Geist', sans-serif";
    ctx.fillText("topics", pad, pad + 24);

    const clusters = [
      ["python-concurrency", 0.85],
      ["scientific-python", 0.4],
      ["auth-and-sessions", 0.6],
      ["frontend", 0.25],
      ["python-gotchas", 0.75],
      ["shell-and-git", 0.5],
    ];
    let y = pad + 70;
    clusters.forEach(([name, pct]) => {
      ctx.fillStyle = EVERGREEN.ink;
      ctx.font = "17px 'Geist Mono', monospace";
      ctx.fillText(name, pad, y);

      // progress bar
      const barX = pad + 230;
      const barW = FACE_SIZE - pad - barX;
      ctx.fillStyle = "rgba(255,255,255,0.06)";
      roundRect(ctx, barX, y - 12, barW, 14, 7);
      ctx.fill();

      ctx.fillStyle = pct >= 0.75 ? EVERGREEN.sage : pct >= 0.5 ? EVERGREEN.gold : EVERGREEN.rose;
      roundRect(ctx, barX, y - 12, barW * pct, 14, 7);
      ctx.fill();

      y += 42;
    });

    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "16px 'Geist Mono', monospace";
    ctx.fillText("$ reskill topics", pad, FACE_SIZE - 30);
  },

  install(ctx) {
    const pad = 32;
    ctx.fillStyle = EVERGREEN.ink;
    ctx.font = "bold 34px 'Geist', sans-serif";
    ctx.fillText("replace", pad, 110);
    ctx.fillText("the scroll.", pad, 156);

    // install box
    ctx.strokeStyle = EVERGREEN.sage;
    ctx.lineWidth = 2;
    roundRect(ctx, pad, 220, FACE_SIZE - pad * 2, 68, 12);
    ctx.stroke();
    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "22px 'Geist Mono', monospace";
    ctx.fillText("$", pad + 20, 262);
    ctx.fillStyle = EVERGREEN.sage;
    ctx.font = "bold 22px 'Geist Mono', monospace";
    ctx.fillText("pip install reskill", pad + 48, 262);

    ctx.fillStyle = EVERGREEN.teal;
    ctx.font = "bold 22px 'Geist', sans-serif";
    ctx.fillText("reSkill", pad, 380);

    ctx.fillStyle = EVERGREEN.inkDim;
    ctx.font = "16px 'Geist', sans-serif";
    ctx.fillText("quizzes during Claude's thinking time", pad, 410);
  },
};

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const words = text.split(" ");
  let line = "";
  let currentY = y;
  words.forEach((word) => {
    const test = line + word + " ";
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line.trim(), x, currentY);
      line = word + " ";
      currentY += lineHeight;
    } else {
      line = test;
    }
  });
  if (line) ctx.fillText(line.trim(), x, currentY);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ───────── Three.js scene ───────── */

function init() {
  const canvas = document.getElementById("hero-cube");
  if (!canvas) return;

  const parent = canvas.parentElement;
  const sizeOf = () => {
    const rect = parent.getBoundingClientRect();
    return { w: rect.width, h: rect.height };
  };

  const { w, h } = sizeOf();
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h, false);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, w / h, 0.1, 100);
  camera.position.set(0, 0, 7);

  // lighting
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xa7c080, 1.1);
  key.position.set(3, 4, 3);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x7fbbb3, 0.7);
  fill.position.set(-3, -1, -2);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xdbbc7f, 0.4);
  rim.position.set(0, -4, 3);
  scene.add(rim);

  // face textures in a specific order (THREE.BoxGeometry face order:
  // +X, -X, +Y, -Y, +Z, -Z)
  const faces = ["question", "reveal", "streak", "session", "topics", "install"];
  const materials = faces.map((kind) => {
    return new THREE.MeshPhysicalMaterial({
      map: drawFace(kind),
      roughness: 0.3,
      metalness: 0.1,
      clearcoat: 0.5,
      clearcoatRoughness: 0.3,
      emissive: new THREE.Color("#0e1117"),
      emissiveIntensity: 0.35,
    });
  });

  const geometry = new THREE.BoxGeometry(2.3, 2.3, 2.3, 1, 1, 1);
  const cube = new THREE.Mesh(geometry, materials);
  scene.add(cube);

  // subtle edge-glow via a slightly-larger wireframe box
  const edgeGeo = new THREE.EdgesGeometry(
    new THREE.BoxGeometry(2.32, 2.32, 2.32),
  );
  const edge = new THREE.LineSegments(
    edgeGeo,
    new THREE.LineBasicMaterial({
      color: 0x7fbbb3,
      transparent: true,
      opacity: 0.3,
    }),
  );
  cube.add(edge);

  // initial orientation: slightly isometric
  cube.rotation.x = 0.4;
  cube.rotation.y = -0.5;

  // pointer tracking for subtle interactive tilt
  let targetX = 0.4;
  let targetY = -0.5;
  let userInteracting = false;
  let idleTimer = 0;

  const onMove = (e) => {
    const rect = parent.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width - 0.5;
    const ny = (e.clientY - rect.top) / rect.height - 0.5;
    targetY = -0.5 + nx * 1.2;
    targetX = 0.4 - ny * 0.6;
    userInteracting = true;
    idleTimer = 0;
  };
  parent.addEventListener("pointermove", onMove);
  parent.addEventListener("pointerleave", () => {
    userInteracting = false;
  });

  // continuous auto-rotate when idle
  let autoYaw = 0;
  const animate = () => {
    requestAnimationFrame(animate);

    if (!userInteracting) {
      autoYaw += 0.004;
      targetY = -0.5 + Math.sin(autoYaw) * 0.6;
      targetX = 0.4 + Math.cos(autoYaw * 0.6) * 0.15;
    }

    cube.rotation.x += (targetX - cube.rotation.x) * 0.08;
    cube.rotation.y += (targetY - cube.rotation.y) * 0.08;

    renderer.render(scene, camera);
  };
  animate();

  // resize
  const onResize = () => {
    const { w, h } = sizeOf();
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  };
  window.addEventListener("resize", onResize);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
