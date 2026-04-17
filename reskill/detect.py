"""Detect project tech stack from filesystem signals."""

from __future__ import annotations

from pathlib import Path


# ── Language detection ───────────────────────────────────────

LANG_SIGNALS: dict[str, list[str]] = {
    "python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "setup.cfg"],
    "javascript": ["package.json"],
    "typescript": ["tsconfig.json"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
    "csharp": ["*.csproj", "*.sln"],
    "swift": ["Package.swift"],
    "dart": ["pubspec.yaml"],
    "kotlin": ["build.gradle.kts"],
    "cpp": ["CMakeLists.txt", "Makefile"],
    "r": ["DESCRIPTION", ".Rproj"],
}

# ── Framework detection (grep patterns in files) ─────────────

FRAMEWORK_FILE_SIGNALS: dict[str, tuple[str, list[str]]] = {
    # framework: (file_to_check, [patterns_to_grep])
    "fastapi": ("pyproject.toml", ["fastapi"]),
    "django": ("pyproject.toml", ["django"]),
    "flask": ("pyproject.toml", ["flask"]),
    "pytorch": ("pyproject.toml", ["torch"]),
    "numpy": ("pyproject.toml", ["numpy"]),
    "react": ("package.json", ['"react"']),
    "nextjs": ("package.json", ['"next"']),
    "vue": ("package.json", ['"vue"']),
    "express": ("package.json", ['"express"']),
    "nestjs": ("package.json", ['"@nestjs/core"']),
    "tailwind": ("package.json", ['"tailwindcss"']),
    "prisma": ("package.json", ['"prisma"', '"@prisma/client"']),
    "actix": ("Cargo.toml", ["actix-web"]),
    "tokio": ("Cargo.toml", ["tokio"]),
    "gin": ("go.mod", ["github.com/gin-gonic/gin"]),
    "spring": ("pom.xml", ["spring-boot"]),
    "rails": ("Gemfile", ["rails"]),
}

# ── Quiz topic mapping ───────────────────────────────────────

LANG_TO_TOPICS: dict[str, list[str]] = {
    "python": ["python", "python-scope", "python-types", "python-stdlib"],
    "javascript": ["javascript", "javascript-closures", "javascript-async"],
    "typescript": ["typescript", "javascript"],
    "rust": ["rust", "rust-ownership", "rust-lifetimes"],
    "go": ["go", "go-concurrency", "go-interfaces"],
    "java": ["java", "java-oop", "java-collections"],
    "ruby": ["ruby"],
    "php": ["php"],
    "csharp": ["csharp", "dotnet"],
    "swift": ["swift"],
    "cpp": ["cpp", "cpp-memory"],
}

FRAMEWORK_TO_TOPICS: dict[str, list[str]] = {
    "fastapi": ["fastapi", "http-status", "rest-api", "pydantic"],
    "django": ["django", "django-orm", "http-status"],
    "flask": ["flask", "http-status"],
    "react": ["react", "react-hooks", "jsx"],
    "nextjs": ["nextjs", "react", "ssr"],
    "express": ["express", "nodejs", "http-status"],
    "pytorch": ["pytorch", "deep-learning", "tensors"],
    "prisma": ["prisma", "sql", "orm"],
    "tailwind": ["tailwind-css", "css"],
    "spring": ["spring", "java-web"],
    "rails": ["rails", "ruby-web"],
    "actix": ["actix", "rust-web"],
    "gin": ["gin", "go-web"],
}


EXT_FALLBACK: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".dart": "dart",
    ".kt": "kotlin",
    ".cpp": "cpp",
    ".c": "cpp",
    ".r": "r",
    ".R": "r",
}


def detect_languages(project_dir: str | Path) -> list[str]:
    """Detect programming languages from project file signals and extensions."""
    root = Path(project_dir)
    detected: list[str] = []

    # Check config files first
    for lang, signals in LANG_SIGNALS.items():
        for signal in signals:
            if "*" in signal:
                if list(root.glob(signal)):
                    detected.append(lang)
                    break
            elif (root / signal).exists():
                detected.append(lang)
                break

    # Fallback: check for source files by extension (top-level + one level deep)
    if not detected:
        seen_langs: set[str] = set()
        for p in list(root.glob("*")) + list(root.glob("*/*")):
            if p.is_file() and p.suffix in EXT_FALLBACK:
                seen_langs.add(EXT_FALLBACK[p.suffix])
        detected = list(seen_langs)

    return detected


def detect_frameworks(project_dir: str | Path) -> list[str]:
    """Detect frameworks by grepping config files."""
    root = Path(project_dir)
    detected: list[str] = []
    for framework, (config_file, patterns) in FRAMEWORK_FILE_SIGNALS.items():
        config_path = root / config_file
        if not config_path.exists():
            continue
        try:
            content = config_path.read_text()
            for pattern in patterns:
                if pattern in content:
                    detected.append(framework)
                    break
        except (OSError, UnicodeDecodeError):
            continue
    return detected


def get_quiz_topics(project_dir: str | Path) -> list[str]:
    """Get relevant quiz topics for a project directory."""
    topics: list[str] = []

    languages = detect_languages(project_dir)
    for lang in languages:
        topics.extend(LANG_TO_TOPICS.get(lang, [lang]))

    frameworks = detect_frameworks(project_dir)
    for fw in frameworks:
        topics.extend(FRAMEWORK_TO_TOPICS.get(fw, [fw]))

    # Always include general topics
    topics.extend(["git", "algorithms", "data-structures"])

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique


def detect_summary(project_dir: str | Path) -> str:
    """Human-readable summary of detected stack."""
    langs = detect_languages(project_dir)
    fws = detect_frameworks(project_dir)

    parts: list[str] = []
    if langs:
        parts.append(f"Languages: {', '.join(langs)}")
    if fws:
        parts.append(f"Frameworks: {', '.join(fws)}")

    topics = get_quiz_topics(project_dir)
    if topics:
        parts.append(f"Quiz topics: {', '.join(topics[:8])}")

    return " | ".join(parts) if parts else "No stack detected"
