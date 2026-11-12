"""Recognize identifiers in query text and source passages."""

import re


ERROR_CODE = re.compile(r'\b(?:0x[0-9a-f]{8}|[a-z]\d-\d{4,5}-\d)\b', re.IGNORECASE)
RELEASE_VERSION = re.compile(
    r'\b(?:v?\d+(?:\.\d+)+|[vr]\d+)(?:[-+][a-z0-9]+(?:[.-][a-z0-9]+)*)?(?!\w|[.+-]\w)',
    re.IGNORECASE,
)


def error_codes(text):
    return set(ERROR_CODE.findall(text.casefold()))


def release_versions(text):
    return {version.removeprefix('v') for version in RELEASE_VERSION.findall(text.casefold())}
