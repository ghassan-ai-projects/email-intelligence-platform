"""
threat_profiles.py — Known attack pattern databases for email guardrail scanning.

All patterns are organized by tier (criticality) and category.
This is the single source of truth; the detector code never hardcodes patterns.
"""

import re
from re import Pattern

# ─── Prompt Injection Patterns ───────────────────────────────────────────────

PROMPT_INJECTION: dict[str, list[str]] = {
    "tier1": [
        # Direct instruction override
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts|commands)",
        r"disregard\s+(all\s+)?(previous|prior|above|your)",
        r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts|commands|training)",
        r"do\s+not\s+(follow|obey|adhere\s+to)\s+(your\s+)?(previous|prior|instructions)",
        r"you\s+(are\s+)?(now|are\s+now)\s+(free|released|unleashed|liberated)",
        r"system\s+(prompt|message|instruction|directive)",
        r"new\s+(instructions|directives|commands|rules)\s*:",
        r"override\s+(mode|protocols|restrictions|constraints|guidelines)",
        r"you\s+must\s+(ignore|disregard|forget|bypass)",
        r"this\s+is\s+(an?\s+)?(override|emergency|priority)\s+(message|broadcast|directive)",
        r"act\s+as\s+if\s+(you\s+)?(have|are)\s+(no|without)\s+(rules|restrictions|limits|boundaries)",
    ],
    "tier2": [
        # Role-play hijacks
        r"you\s+(are\s+)?now\s+(character|role\s*play|playing|acting\s+as)",
        r"pretend\s+(to\s+be|you\s+are)",
        r"(from\s+)?(this\s+)?point\s+(forward|on)\s+you\s+(are|will\s+be)",
        r"from\s+now\s+on\s+you\s+(are|will\s+be)",
        r"dan\b",  # Do Anything Now
        r"jailbreak",
        r"mode\s+(unlocked|activated|engaged|enabled)",
        r"no\s+(restrictions|rules|boundaries|limits|filtering)",
        r"bypass\s+(filters|restrictions|content\s+policy|safety)",
        r"simulate\s+(unrestricted|unfiltered|uncensored)",
        r"you\s+(don't|do\s+not)\s+(have|need)\s+(to\s+)?(follow|obey|respect)",
        r"hypothetical\s+scenario",
        r"research\s+purpose",
        r"educational\s+purpose\s+only",
        r"for\s+(science|research|experiment)",
    ],
    "tier3": [
        # Subtle manipulations
        r"output\s+(the\s+)?(full|complete|entire)\s+(prompt|system\s+prompt|instructions)",
        r"show\s+(me\s+)?(your\s+)?(prompt|instructions|directives|initial\s+prompt)",
        r"what\s+(are|were)\s+(your\s+)?(initial|original)\s+(instructions|prompt)",
        r"repeat\s+(back|after\s+me|the\s+word|this\s+phrase)",
        r"say\s+the\s+word",
        r"you\s+will\s+(now\s+)?(obey|listen\s+to)",
        r"answer\s+(the\s+)?(above|following)\s+(without|regardless)",
        r"tell\s+me\s+(how\s+to\s+)?(hack|crack|exploit|bypass)",
        r"ignore\s+all\s+safety",
        r"remove\s+(the\s+)?(ethical|safety|moral)\s+(guidelines|boundaries|constraints)",
    ],
}

# ─── Encoded Payload Signatures ──────────────────────────────────────────────

# Patterns to check in decoded payloads
SUSPICIOUS_DECODED_PATTERNS: list[str] = [
    r"ignore\s+(previous|prior|all)",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"forget\s+(all|everything)",
    r"new\s+(instructions|rules)",
    r"override\s+(protocols|mode)",
    r"dan\b",
    r"jailbreak",
    r"bypass\s+(filters|restrictions)",
    r"unrestricted\s+mode",
]

# Markers that suggest encoded content is worth investigating
ENCODING_INDICATORS: list[str] = [
    "base64",
    "decode",
    "decrypt",
    "deobfuscate",
    "hidden",
    "secret",
    "transform",
    "convert",
]

# ─── Homoglyph Map ───────────────────────────────────────────────────────────
# Maps Unicode confusables → their ASCII lookalike

HOMOGLYPH_MAP: dict[str, str] = {
    # Cyrillic → Latin
    "\u0430": "a",  # а → a
    "\u0435": "e",  # е → e
    "\u043e": "o",  # о → o
    "\u0440": "p",  # р → p
    "\u0441": "c",  # с → c
    "\u0445": "x",  # х → x
    "\u0443": "y",  # у → y
    "\u0410": "A",  # А → A
    "\u0412": "B",  # В → B
    "\u0415": "E",  # Е → E
    "\u041a": "K",  # К → K
    "\u041c": "M",  # М → M
    "\u041d": "H",  # Н → H
    "\u041e": "O",  # О → O
    "\u0420": "P",  # Р → P
    "\u0421": "C",  # С → C
    "\u0422": "T",  # Т → T
    "\u0423": "Y",  # У → Y
    "\u0425": "X",  # Х → X
    # Greek → Latin
    "\u0391": "A",  # Α → A
    "\u0392": "B",  # Β → B
    "\u0395": "E",  # Ε → E
    "\u0399": "I",  # Ι → I
    "\u039a": "K",  # Κ → K
    "\u039c": "M",  # Μ → M
    "\u039d": "N",  # Ν → N
    "\u039f": "O",  # Ο → O
    "\u03a1": "P",  # Ρ → P
    "\u03a4": "T",  # Τ → T
    "\u03a5": "Y",  # Υ → Y
    "\u03a7": "X",  # Χ → X
}

# ─── Zero-Width & Invisible Characters ──────────────────────────────────────

ZERO_WIDTH_CHARS: dict[str, str] = {
    "\u200b": "ZWSP",  # Zero-Width Space
    "\u200c": "ZWNJ",  # Zero-Width Non-Joiner
    "\u200d": "ZWJ",  # Zero-Width Joiner
    "\ufeff": "ZWNBSP",  # Zero-Width No-Break Space (BOM)
    "\u2060": "WJ",  # Word Joiner
    "\u2061": "FUNC",  # Function Application
    "\u2062": "TIMES",  # Invisible Times
    "\u2063": "SEP",  # Invisible Separator
    "\u2064": "INVS",  # Invisible Plus
}

BIDI_OVERRIDE_CHARS: dict[str, str] = {
    "\u202a": "LRE",  # Left-to-Right Embedding
    "\u202b": "RLE",  # Right-to-Left Embedding
    "\u202c": "PDF",  # Pop Directional Formatting
    "\u202d": "LRO",  # Left-to-Right Override
    "\u202e": "RLO",  # Right-to-Left Override
    "\u2066": "LRI",  # Left-to-Right Isolate
    "\u2067": "RLI",  # Right-to-Left Isolate
    "\u2068": "FSI",  # First Strong Isolate
    "\u2069": "PDI",  # Pop Directional Isolate
}

# ─── Compilation Helper ──────────────────────────────────────────────────────


def compile_patterns(patterns_dict: dict[str, list[str]]) -> dict[str, list[Pattern]]:
    """Compile string patterns into compiled regex objects, grouped by key."""
    compiled: dict[str, list[Pattern]] = {}
    for key, patterns in patterns_dict.items():
        compiled[key] = [re.compile(p, re.IGNORECASE) for p in patterns]
    return compiled


def compile_suspicious_decoded() -> list[Pattern]:
    """Compile patterns for checking decoded payload content."""
    return [re.compile(p, re.IGNORECASE) for p in SUSPICIOUS_DECODED_PATTERNS]


# ─── Known Malicious Header Signatures ──────────────────────────────────────

SUSPICIOUS_CONTENT_TYPES: list[str] = [
    "text/javascript",
    "application/x-javascript",
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/x-msi",
    "application/x-bat",
    "application/x-sh",
    "application/x-vbs",
    "application/x-httpd-php",
    "text/html",
]

SUSPICIOUS_ATTACHMENT_EXTENSIONS: list[str] = [
    ".exe",
    ".bat",
    ".cmd",
    ".vbs",
    ".vbe",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".ps1",
    ".psm1",
    ".psd1",
    ".scr",
    ".pif",
    ".hta",
    ".cpl",
    ".msi",
    ".msp",
    ".mst",
    ".reg",
    ".docm",
    ".xlsm",
    ".pptm",
]

# ─── Quote Prefixes for Reply-Chain Detection ───────────────────────────────

QUOTE_PREFIXES: list[str] = [
    r">\s?",
    r"On\s+.*\s+wrote\s*:",
    r"---+\s*Original\s+Message\s*---+\s*",
    r"From\s*:",
    r"Sent\s*:",
    r"To\s*:",
    r"Subject\s*:",
    r"Le\s+.*\s+a\s+écrit\s*:",
]
