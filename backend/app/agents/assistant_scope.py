# =========================================================
# MARITIME ASSISTANT - BUSINESS SCOPE GUARD
# =========================================================
# Purpose
# -------
# The Maritime AI Assistant answers BUSINESS / SHIPPING
# questions for normal users of the platform. It is not a
# developer assistant, not a coding assistant and not a
# project documentation assistant.
#
# This module is the single, deterministic gate that decides
# whether a question is in scope before anything else happens.
#
# It runs FIRST, ahead of intent detection, ahead of any
# project knowledge and ahead of any data retrieval, so a
# question that is out of scope can never reach Gemini with
# developer material in the prompt and can never be answered
# from a technical topic.
#
# WHAT IS REFUSED
# ---------------
#   * Technical / developer questions: API names, databases,
#     programming languages, source code, file and folder
#     names, frameworks, configuration, credentials,
#     algorithms as code, internal logs.
#   * General knowledge questions that have nothing to do with
#     shipping: politics, jokes, general programming trivia.
#
# Both categories return the SAME polite redirect sentence, so
# a refused question reveals nothing about the platform beyond
# the list of topics the assistant does cover.
#
# WHAT IS NEVER REFUSED
# ---------------------
# Maritime business vocabulary is deliberately absent from the
# marker tables. "risk", "warning", "restricted", "documents",
# "clearance", "compliance", "container", "transit",
# "transshipment", "quotation", "freight", "surcharge" and
# "port" all appear in real customer questions and must keep
# working. "route", "cargo", "customs", "weather" and
# "shipment" are matched on word boundaries only, so a word
# that merely contains one of them ("Java" inside a longer
# word) cannot cause a false refusal.
#
# NO PROJECT DATA
# ---------------
# This module holds no business rule. It reads no dataset, no
# database and no environment variable, and it never calls an
# agent. It only decides scope.
# =========================================================

import re


# =========================================================
# REFUSAL TEXT
# =========================================================
# One sentence, used for both refused categories so a refused
# question discloses nothing.

REFUSAL_ANSWER = (
    "I'm the Maritime AI Assistant. I can help you with "
    "routes, cargo, customs, weather, quotations, and "
    "shipments."
)


# =========================================================
# SCOPE CLASSIFICATION
# =========================================================

SCOPE_BUSINESS = "business"
SCOPE_TECHNICAL = "technical"
SCOPE_OFF_TOPIC = "off_topic"


# =========================================================
# TECHNICAL / DEVELOPER VOCABULARY
# =========================================================
# Word-boundary matched, case-insensitive. Multi-word entries
# are matched first so a specific phrase such as "api key"
# always wins over the single word "api".

TECHNICAL_PHRASES = (
    "source code",
    "stack trace",
    "api key",
    "api keys",
    "secret key",
    "access key",
    "private key",
    "environment variable",
    "env var",
    "env vars",
    "machine learning",
    "language model",
    "training data",
    "system prompt",
    "internal prompt",
    "chatbot architecture",
    "tech stack",
    "technology stack",
    "open source",
    "programming language",
    "code snippet",
    "code base",
    "write code",
    "show me the code",
    "show your code",
    "your code",
    "the code",
    "hs code is what",
    "front end",
    "node js",
    "source file",
    "prompt engineering",
    "how are you built",
    "who wrote",
    "this project",
    "the project",
    "project do",
    "route agent",
    "weather agent",
    "customs agent",
    "pricing agent",
    "margin agent",
    "ais agent",
    "the agents",
    "agents connected",
    "different agents",
    "agents work together",
    "agent architecture",
    "agent orchestration",
    "how are the agents",
    "database table",
    "requirements.txt",
    "package.json",
    "sql injection",
    "vulnerability",
    "vulnerabilities",
    "prime minister",
)

TECHNICAL_WORDS = (
    # ---------------------------------------------
    # INTERFACES AND INFRASTRUCTURE
    # ---------------------------------------------
    "api",
    "apis",
    "endpoint",
    "endpoints",
    "backend",
    "frontend",
    "server",
    "servers",
    "localhost",
    "gateway",
    "proxy",
    "middleware",
    "url",
    "urls",
    "uri",
    "http",
    "https",
    "websocket",
    "webhook",
    "curl",
    "websocket",

    # ---------------------------------------------
    # DATA STORAGE
    # ---------------------------------------------
    "database",
    "databases",
    "mongodb",
    "mongo",
    "postgres",
    "postgresql",
    "mysql",
    "sqlite",
    "sql",
    "schema",
    "collection",
    "collections",
    "query",
    "queries",
    "migration",
    "migrations",
    "cache",
    "redis",
    "csv",
    "dataset",
    "datasets",

    # ---------------------------------------------
    # LANGUAGES AND FRAMEWORKS
    #
    # NOTE: the bare word "code" is NOT here. "HS code" is a
    # customs classification a customer must be able to ask
    # about, so only explicit code-related phrases are
    # matched. "port" is not here either: it is core
    # maritime vocabulary.
    # ---------------------------------------------
    "programming",
    "codebase",
    "function",
    "functions",
    "method",
    "methods",
    "script",
    "scripts",
    "python",
    "javascript",
    "java",
    "golang",
    "rust",
    "typescript",
    "react",
    "angular",
    "vue",
    "node",
    "nodejs",
    "npm",
    "fastapi",
    "django",
    "flask",
    "uvicorn",
    "gunicorn",
    "asgi",
    "wsgi",
    "pydantic",
    "pandas",
    "numpy",
    "sqlalchemy",
    "jquery",
    "html",
    "css",
    "json",
    "xml",
    "yaml",
    "lang",
    "language",
    "languages",
    "framework",
    "frameworks",
    "library",
    "libraries",
    "package",
    "packages",
    "dependency",
    "dependencies",
    "sdk",
    "ide",
    "compiler",

    # ---------------------------------------------
    # REPOSITORIES AND FILE SYSTEMS
    # ---------------------------------------------
    "file",
    "files",
    "filename",
    "filenames",
    "folder",
    "folders",
    "directory",
    "directories",
    "repo",
    "repository",
    "git",
    "github",
    "gitlab",
    "commit",
    "commits",
    "branch",
    "branches",
    "module",
    "modules",
    "yml",

    # ---------------------------------------------
    # INFRASTRUCTURE AND OPERATIONS
    # ---------------------------------------------
    "nginx",
    "docker",
    "kubernetes",
    "vercel",
    "netlify",
    "aws",
    "azure",
    "gcp",
    "cloudflare",
    "linux",
    "ubuntu",
    "centos",
    "bash",
    "shell",
    "powershell",
    "cpanel",
    "xampp",
    "wamp",
    "cron",
    "thread",
    "threading",
    "synchronous",
    "microservice",
    "microservices",
    "stack",

    # ---------------------------------------------
    # AI AND CREDENTIALS
    # ---------------------------------------------
    "gemini",
    "openai",
    "chatgpt",
    "gpt",
    "llm",
    "llms",
    "prompt",
    "prompts",
    "token",
    "tokens",
    "jwt",
    "bcrypt",
    "hs256",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "apikey",
    "encryption",
    "hash",
    "hashing",

    # ---------------------------------------------
    # CONFIGURATION AND DIAGNOSTICS
    # ---------------------------------------------
    "env",
    "config",
    "configs",
    "configuration",
    "log",
    "logs",
    "logging",
    "traceback",
    "exception",
    "exceptions",
    "debug",
    "debugger",
    "deploy",
    "deployment",
    "implementation",
    "implemented",
    "architecture",
    "technologies",
    "technology",
    "boolean",
    "integer",
    "float",
    "regex",
    "refactor",
    "compile",
    "compiled",
    "encrypted",
    "variable",
    "variables",

    # ---------------------------------------------
    # INTERNAL COMPONENTS AND PEOPLE
    #
    # A question about an internal module, an algorithm as
    # code, or the developer who wrote it is a developer
    # question, not a shipping question. "Route", "cargo",
    # "customs", "weather" and "shipment" are deliberately
    # absent so the customer's own vocabulary keeps working.
    # ---------------------------------------------
    "algorithm",
    "algorithms",
    "developer",
    "developers",
    "programmer",
    "algorithmically",
    "authentication",
    "authorization",
    "authorisation",
    "auth",
    "algorithm",
    "hack",
    "hacking",
    "exploit",
    "bypass",
    "math",
    "project",
    "algorithm",
)


# =========================================================
# GENERAL KNOWLEDGE VOCABULARY
# =========================================================
# Nothing to do with shipping a container. The same polite
# redirect is returned.

OFF_TOPIC_PHRASES = (
    "who is the",
    "who was the",
    "who won",
    "meaning of life",
    "capital of",
    "tell me a joke",
    "tell me a story",
    "write me a poem",
    "what is the time",
    "what time is it",
    "how tall is",
    "how old is",

    # A consumer weather question is not a maritime one. The
    # platform's weather is always about a shipping lane, so a
    # named city, a near-term day or a general forecast is a
    # question this assistant does not answer.
    "weather in",
    "weather today",
    "weather tomorrow",
    "weather for",
    "forecast for",
    "is it going to rain",
    "will it rain",
    "temperature in",

    # General knowledge and language questions
    "theory of",
    "who should i vote",
    "translate",
    "in german",
    "in french",
    "in spanish",
    "in hindi",
    "in chinese",
    "in japanese",
    "meaning in",
)

OFF_TOPIC_WORDS = (
    "president",
    "minister",
    "election",
    "elections",
    "politician",
    "politics",
    "parliament",
    "senate",
    "congress",
    "celebrity",
    "celebrities",
    "actor",
    "actress",
    "singer",
    "movie",
    "movies",
    "film",
    "films",
    "song",
    "songs",
    "lyrics",
    "poem",
    "poetry",
    "story",
    "joke",
    "jokes",
    "riddle",
    "recipe",
    "recipes",
    "cooking",
    "cook",
    "restaurant",
    "horoscope",
    "zodiac",
    "astrology",
    "tarot",
    "football",
    "cricket",
    "basketball",
    "tennis",
    "nba",
    "ipl",
    "homework",
    "maths",
    "mathematics",
    "algebra",
    "derivative",
    "integral",
    "essay",
    "wikipedia",
    "google",
    "search engine",
    "stocks",
    "crypto",
    "bitcoin",
    "lottery",
    "gaming",
    "relativity",
    "physics",
    "chemistry homework",
    "philosophy",
    "psychology",
    "novel",
    "books",
    "book recommendation",
)


# =========================================================
# COMPILED MATCHERS
# =========================================================
# Phrases are matched as plain substrings (they already carry
# word boundaries), single words are matched on a word
# boundary so "java" cannot match inside a longer word and
# "port" cannot match inside "important".

def _phrase_matcher(phrases):

    if not phrases:
        return None

    return re.compile(
        "|".join(
            re.escape(phrase)
            for phrase in sorted(
                phrases, key=len, reverse=True
            )
        )
    )


def _word_matcher(words):

    if not words:
        return None

    return re.compile(
        r"\b(?:" + "|".join(
            re.escape(word)
            for word in sorted(words, key=len, reverse=True)
        ) + r")\b"
    )


TECHNICAL_PHRASE_PATTERN = _phrase_matcher(
    TECHNICAL_PHRASES
)

TECHNICAL_WORD_PATTERN = _word_matcher(
    TECHNICAL_WORDS
)

OFF_TOPIC_PHRASE_PATTERN = _phrase_matcher(
    OFF_TOPIC_PHRASES
)

OFF_TOPIC_WORD_PATTERN = _word_matcher(
    OFF_TOPIC_WORDS
)

# A question that is nothing but an arithmetic expression,
# for example "What is 2+2?". It carries no business topic,
# so it is out of scope rather than an unknown business
# question. A trailing question mark and a short leading
# phrase such as "what is" are tolerated.

ARITHMETIC_PATTERN = re.compile(
    r"^\s*(?:what(?:'s| is)|calculate|compute|how much is)?\s*"
    r"[\d\s\+\-\*\/\.\(\)=x×÷]+\s*\??\s*$"
)


# =========================================================
# CLASSIFICATION
# =========================================================

def classify_question(question):
    """
    Decide whether a question belongs to the assistant.

    Parameters
    ----------
    question : str
        Raw question text from the caller.

    Returns
    -------
    tuple[str, str]
        (scope, matched_marker)

        scope is one of "business", "technical" or
        "off_topic". matched_marker is the marker that
        decided it, or an empty string for a business
        question. It is used for server-side logging only
        and is never returned to the caller.
    """

    text = str(question or "").strip().lower()

    if not text:
        return SCOPE_BUSINESS, ""

    if ARITHMETIC_PATTERN.match(text):

        return SCOPE_OFF_TOPIC, "arithmetic expression"

    if TECHNICAL_PHRASE_PATTERN.search(text):

        return (
            SCOPE_TECHNICAL,
            _matched_marker(
                text, TECHNICAL_PHRASE_PATTERN
            ),
        )

    if TECHNICAL_WORD_PATTERN.search(text):

        return (
            SCOPE_TECHNICAL,
            _matched_marker(
                text, TECHNICAL_WORD_PATTERN
            ),
        )

    if OFF_TOPIC_PHRASE_PATTERN.search(text):

        return (
            SCOPE_OFF_TOPIC,
            _matched_marker(
                text, OFF_TOPIC_PHRASE_PATTERN
            ),
        )

    if OFF_TOPIC_WORD_PATTERN.search(text):

        return (
            SCOPE_OFF_TOPIC,
            _matched_marker(
                text, OFF_TOPIC_WORD_PATTERN
            ),
        )

    return SCOPE_BUSINESS, ""


def _matched_marker(text, pattern):
    """The marker that decided the classification."""

    match = pattern.search(text)

    return match.group(0) if match else ""


def is_in_scope(question):

    """True when the assistant may answer this question."""

    return classify_question(question)[0] == SCOPE_BUSINESS