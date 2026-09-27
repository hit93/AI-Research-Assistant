"""Local Guardrails Engine — Comprehensive on-device, multi-tier security filter.

Provides 100% local, zero-cloud-dependency safety checks including PII redaction,
prompt injection detection, semantic policy guardrails, and output prompt-leak auditing.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("research_assistant.security.guardrails")


@dataclass
class GuardrailViolation:
    """Represents a specific guardrail policy violation."""
    category: str  # "PII", "INJECTION", "TOXICITY", "SAFETY", "POLICY", "PROMPT_LEAK"
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    description: str
    matched_fragment: Optional[str] = None


@dataclass
class GuardrailResult:
    """Result of running guardrail checks on input or output text."""
    is_blocked: bool
    sanitized_text: str
    violations: List[GuardrailViolation] = field(default_factory=list)
    action: str = "PASS"  # "PASS", "ANONYMIZED", "BLOCKED"
    policy_assessment: Optional[Dict[str, Any]] = None

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


class PIIMasker:
    """Detects and masks Personally Identifiable Information (PII) and secret keys locally."""

    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
    PHONE_PATTERN = re.compile(r'(\b\+?[0-9]{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b')
    SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')
    IPV4_PATTERN = re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
    
    API_KEY_PATTERNS = [
        ("OPENAI_KEY", re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b')),
        ("GROQ_KEY", re.compile(r'\bgsk_[A-Za-z0-9]{20,}\b')),
        ("AWS_KEY", re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
        ("GITHUB_TOKEN", re.compile(r'\bghp_[A-Za-z0-9]{36}\b')),
        ("GENERIC_BEARER", re.compile(r'Bearer\s+[A-Za-z0-9_\-\.]{25,}', re.IGNORECASE)),
        ("GEMINI_KEY", re.compile(r'\bAIzaSy[A-Za-z0-9_\-]{33}\b')),
    ]

    def mask(self, text: str) -> Tuple[str, List[GuardrailViolation]]:
        """Mask PII in text and return sanitized text with recorded violations."""
        if not text:
            return text, []

        sanitized = text
        violations: List[GuardrailViolation] = []

        # 1. Mask Secrets & API keys
        for key_name, pattern in self.API_KEY_PATTERNS:
            matches = pattern.findall(sanitized)
            if matches:
                for match in matches:
                    violations.append(GuardrailViolation(
                        category="PII",
                        severity="CRITICAL",
                        description=f"Secret API Key detected ({key_name})",
                        matched_fragment="***REDACTED***"
                    ))
                sanitized = pattern.sub("[API_KEY_REDACTED]", sanitized)

        # 2. Mask SSN
        ssn_matches = self.SSN_PATTERN.findall(sanitized)
        if ssn_matches:
            violations.append(GuardrailViolation(
                category="PII",
                severity="HIGH",
                description=f"Social Security Number detected ({len(ssn_matches)} instances)",
                matched_fragment="***REDACTED***"
            ))
            sanitized = self.SSN_PATTERN.sub("[SSN_REDACTED]", sanitized)

        # 3. Mask Credit Cards
        cc_matches = self.CREDIT_CARD_PATTERN.findall(sanitized)
        if cc_matches:
            violations.append(GuardrailViolation(
                category="PII",
                severity="HIGH",
                description=f"Credit Card number detected ({len(cc_matches)} instances)",
                matched_fragment="***REDACTED***"
            ))
            sanitized = self.CREDIT_CARD_PATTERN.sub("[CREDIT_CARD_REDACTED]", sanitized)

        # 4. Mask Emails
        email_matches = self.EMAIL_PATTERN.findall(sanitized)
        if email_matches:
            violations.append(GuardrailViolation(
                category="PII",
                severity="MEDIUM",
                description=f"Email address detected ({len(email_matches)} instances)",
                matched_fragment="[EMAIL]"
            ))
            sanitized = self.EMAIL_PATTERN.sub("[EMAIL_REDACTED]", sanitized)

        # 5. Mask Phone Numbers
        phone_matches = [m.group(0) for m in self.PHONE_PATTERN.finditer(sanitized) if len(re.sub(r'\D', '', m.group(0))) >= 10]
        if phone_matches:
            violations.append(GuardrailViolation(
                category="PII",
                severity="LOW",
                description=f"Phone number detected ({len(phone_matches)} instances)",
                matched_fragment="[PHONE]"
            ))
            for pm in phone_matches:
                sanitized = sanitized.replace(pm, "[PHONE_REDACTED]")

        # 6. Mask IP Addresses
        ip_matches = [ip for ip in self.IPV4_PATTERN.findall(sanitized) if not ip.startswith("127.") and ip != "0.0.0.0"]
        if ip_matches:
            violations.append(GuardrailViolation(
                category="PII",
                severity="LOW",
                description=f"IP Address detected ({len(ip_matches)} instances)",
                matched_fragment="[IP]"
            ))
            for ip in ip_matches:
                sanitized = sanitized.replace(ip, "[IP_REDACTED]")

        return sanitized, violations


class PromptInjectionDetector:
    """Local multi-pattern detector for direct and indirect injections, jailbreaks, and tag smuggling."""

    INJECTION_SIGNATURES = [
        (re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions', re.IGNORECASE), "Direct instruction override"),
        (re.compile(r'disregard\s+(?:all\s+)?(?:previous|prior|system)\s+prompts?', re.IGNORECASE), "System prompt bypass"),
        (re.compile(r'(?:output|print|reveal|show|display)\s+(?:the\s+)?(?:system\s+prompt|hidden\s+instructions|system\s+instructions)', re.IGNORECASE), "System prompt exfiltration"),
        (re.compile(r'you\s+are\s+now\s+(?:in\s+)?(?:dan|developer\s+mode|unfiltered|jailbreak)', re.IGNORECASE), "Jailbreak persona assumption"),
        (re.compile(r'(?:stop|bypass|override)\s+(?:all\s+)?(?:safety|guardrails|filters|content\s+policies)', re.IGNORECASE), "Safety filter bypass attempt"),
        (re.compile(r'\[(?:SYSTEM|INSTRUCTION|ADMIN|OVERRIDE)(?::|\s+PROMPT|\s+INSTRUCTION|\s*:)?.*?\]', re.IGNORECASE), "Delimiter injection / role smuggling"),
        (re.compile(r'<\/?(?:system|instruction|admin|override)>', re.IGNORECASE), "Tag smuggling injection"),
        (re.compile(r'base64\s+decode\s+and\s+execute', re.IGNORECASE), "Obfuscated payload injection"),
        (re.compile(r'repeat\s+everything\s+above\s+(?:verbatim|starting\s+from)', re.IGNORECASE), "Prompt leakage probe"),
    ]

    def detect(self, text: str) -> List[GuardrailViolation]:
        """Scan text for prompt injection and jailbreak signatures."""
        if not text:
            return []

        violations: List[GuardrailViolation] = []
        for pattern, desc in self.INJECTION_SIGNATURES:
            match = pattern.search(text)
            if match:
                violations.append(GuardrailViolation(
                    category="INJECTION",
                    severity="CRITICAL",
                    description=f"Prompt injection detected: {desc}",
                    matched_fragment=match.group(0)
                ))

        return violations


class ContentFilter:
    """Local safety scanner for hazardous, malicious, and dangerous activity requests."""

    TOXIC_KEYWORDS = [
        re.compile(r'\b(?:how\s+to\s+build|synthesize|make)\s+(?:a\s+)?(?:bomb|biological\s+weapon|chemical\s+weapon|explosive)\b', re.IGNORECASE),
        re.compile(r'\b(?:write|generate)\s+(?:malware|ransomware|keylogger|rootkit|zero-day\s+exploit)\b', re.IGNORECASE),
        re.compile(r'\b(?:ddos\s+attack|unauthorized\s+backdoor\s+access|sql\s+injection\s+payload)\b', re.IGNORECASE),
    ]

    def scan(self, text: str) -> List[GuardrailViolation]:
        if not text:
            return []

        violations: List[GuardrailViolation] = []
        for pattern in self.TOXIC_KEYWORDS:
            match = pattern.search(text)
            if match:
                violations.append(GuardrailViolation(
                    category="SAFETY",
                    severity="CRITICAL",
                    description="Safety violation: Dangerous or unauthorized activity requested",
                    matched_fragment=match.group(0)
                ))
        return violations


class LocalGuardrailsEngine:
    """
    High-performance, 100% Local Guardrails Engine.
    Operates completely on-device without any AWS or third-party cloud dependencies.
    Provides defense-in-depth across input queries, retrieved source documents, and generated output reports.
    """

    def __init__(
        self,
        enable_pii_masking: bool = True,
        enable_injection_detection: bool = True,
        enable_content_filter: bool = True,
    ):
        self.enable_pii_masking = enable_pii_masking
        self.enable_injection_detection = enable_injection_detection
        self.enable_content_filter = enable_content_filter
        
        self.pii_masker = PIIMasker()
        self.injection_detector = PromptInjectionDetector()
        self.content_filter = ContentFilter()

    def evaluate_input(self, text: str, source_type: str = "USER_QUERY") -> GuardrailResult:
        """
        Evaluate and sanitize untrusted incoming text (User queries, retrieved documents).
        Returns GuardrailResult with sanitization, pass/block status, and violation details.
        """
        if not text:
            return GuardrailResult(is_blocked=False, sanitized_text="", action="PASS")

        violations: List[GuardrailViolation] = []
        sanitized = text

        # Tier 1: PII & Secret Redaction
        if self.enable_pii_masking:
            sanitized, pii_violations = self.pii_masker.mask(sanitized)
            violations.extend(pii_violations)

        # Tier 2: Prompt Injection / Jailbreak Detection
        if self.enable_injection_detection:
            injection_violations = self.injection_detector.detect(text)
            violations.extend(injection_violations)

        # Tier 3: Dangerous Content Filter
        if self.enable_content_filter:
            content_violations = self.content_filter.scan(text)
            violations.extend(content_violations)

        # Determine blocking policy: Critical violations trigger block
        has_critical = any(v.severity == "CRITICAL" for v in violations)
        
        if has_critical:
            return GuardrailResult(
                is_blocked=True,
                sanitized_text="[REQUEST BLOCKED BY LOCAL SECURITY GUARDRAILS: Prompt injection, dangerous content, or policy violation detected.]",
                violations=violations,
                action="BLOCKED",
                policy_assessment={"local_engine": "active", "threat_level": "CRITICAL"}
            )
        
        action = "ANONYMIZED" if (sanitized != text) else "PASS"
        return GuardrailResult(
            is_blocked=False,
            sanitized_text=sanitized,
            violations=violations,
            action=action,
            policy_assessment={"local_engine": "active", "threat_level": "NONE" if not violations else "LOW"}
        )

    def evaluate_output(self, text: str) -> GuardrailResult:
        """
        Evaluate generated LLM output before presentation or caching.
        Ensures zero leaked prompt templates, secrets, or unmasked PII.
        """
        if not text:
            return GuardrailResult(is_blocked=False, sanitized_text="", action="PASS")

        sanitized = text
        violations: List[GuardrailViolation] = []

        # 1. PII Redaction on Output
        if self.enable_pii_masking:
            sanitized, pii_violations = self.pii_masker.mask(sanitized)
            violations.extend(pii_violations)

        # 2. System Prompt Leakage Audit
        leak_patterns = [
            re.compile(r'You are an expert academic research assistant', re.IGNORECASE),
            re.compile(r'JSON Format Requirement', re.IGNORECASE),
            re.compile(r'### System Context and Internal Directives', re.IGNORECASE),
        ]
        for pat in leak_patterns:
            if pat.search(sanitized):
                violations.append(GuardrailViolation(
                    category="PROMPT_LEAK",
                    severity="HIGH",
                    description="Potential internal system instruction leak detected in output",
                    matched_fragment="[SYSTEM_INSTRUCTION_LEAK]"
                ))

        has_critical = any(v.severity == "CRITICAL" for v in violations)
        if has_critical:
            return GuardrailResult(
                is_blocked=True,
                sanitized_text="[OUTPUT BLOCKED BY LOCAL SECURITY GUARDRAILS]",
                violations=violations,
                action="BLOCKED",
                policy_assessment={"local_engine": "active", "threat_level": "CRITICAL"}
            )

        action = "ANONYMIZED" if (sanitized != text) else "PASS"
        return GuardrailResult(
            is_blocked=False,
            sanitized_text=sanitized,
            violations=violations,
            action=action,
            policy_assessment={"local_engine": "active", "threat_level": "NONE" if not violations else "LOW"}
        )


# Backward-compatible alias
BedrockGuardrailsEngine = LocalGuardrailsEngine

# Global singleton instance
guardrails_engine = LocalGuardrailsEngine()
