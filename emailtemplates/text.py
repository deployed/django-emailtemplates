# coding=utf-8
"""
Plain text version of an HTML email, the fallback for email clients that cannot show
HTML, so that Site Admins never write the text by hand. Rendered by inscriptis.
"""

import re
import textwrap

from inscriptis import get_text
from inscriptis.model.config import ParserConfig

# links keep their address, so that e.g. an activation link can still be followed
CONFIG = ParserConfig(display_links=True)
BLANK_LINES_RE = re.compile(r"\n{3,}")


def html_to_text(html):
    """
    Returns the plain text version of an HTML email: the text laid out as a browser shows
    it, links followed by their address, without styles, scripts, the document head and
    elements hidden with ``display: none`` (e.g. a preheader).
    """
    if not html:
        return ""
    lines = [line.rstrip() for line in get_text(html, CONFIG).splitlines()]
    text = textwrap.dedent("\n".join(lines))
    return BLANK_LINES_RE.sub("\n\n", text).strip("\n")
