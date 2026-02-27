import os
import json
import logging
import re

import dotenv
from substack import Api
from substack.post import Post
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET_RE = re.compile(r"^[*\-]\s+(.*)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _parse_inline(text: str) -> list[dict]:
    """Parse inline markdown into ProseMirror text nodes.

    Handles links, bold, and italic. Fixes the upstream parse_inline bug where
    links at position 0 are skipped.
    """
    if not text:
        return []

    matches = []
    for m in _LINK_RE.finditer(text):
        matches.append((m.start(), m.end(), "link", m.group(1), m.group(2)))
    for m in _BOLD_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, *_ in matches):
            matches.append((m.start(), m.end(), "bold", m.group(1), None))
    for m in _ITALIC_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, *_ in matches):
            matches.append((m.start(), m.end(), "italic", m.group(1), None))
    matches.sort(key=lambda x: x[0])

    nodes = []
    last = 0
    for start, end, kind, content, url in matches:
        if start > last:
            nodes.append({"type": "text", "text": text[last:start]})
        if kind == "link":
            nodes.append({"type": "text", "text": content,
                          "marks": [{"type": "link", "attrs": {"href": url}}]})
        elif kind == "bold":
            nodes.append({"type": "text", "text": content,
                          "marks": [{"type": "strong"}]})
        elif kind == "italic":
            nodes.append({"type": "text", "text": content,
                          "marks": [{"type": "em"}]})
        last = end
    if last < len(text):
        nodes.append({"type": "text", "text": text[last:]})
    return [n for n in nodes if n.get("text")]


def _markdown_to_draft_body(content: str) -> dict:
    """Parse markdown into a ProseMirror draft_body with proper bullet_list support."""
    blocks: list[dict] = []
    pending_bullets: list[list[dict]] = []

    def flush_bullets():
        if not pending_bullets:
            return
        list_items = []
        for bullet_nodes in pending_bullets:
            list_items.append({
                "type": "list_item",
                "content": [{"type": "paragraph", "content": bullet_nodes}],
            })
        blocks.append({"type": "bullet_list", "content": list_items})
        pending_bullets.clear()

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            flush_bullets()
            continue

        heading_m = _HEADING_RE.match(stripped)
        if heading_m:
            flush_bullets()
            level = len(heading_m.group(1))
            text_nodes = _parse_inline(heading_m.group(2))
            blocks.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": text_nodes,
            })
            continue

        bullet_m = _BULLET_RE.match(stripped)
        if bullet_m:
            text_nodes = _parse_inline(bullet_m.group(1))
            pending_bullets.append(text_nodes)
            continue

        # Regular paragraph
        flush_bullets()
        text_nodes = _parse_inline(stripped)
        blocks.append({"type": "paragraph", "content": text_nodes})

    flush_bullets()
    return {"type": "doc", "content": blocks}


SUBSTACK_EMAIL = os.environ.get("SUBSTACK_EMAIL")
SUBSTACK_PASSWORD = os.environ.get("SUBSTACK_PASSWORD")
SUBSTACK_URL = os.environ.get("SUBSTACK_URL")


def _cookies_string_from_env(raw: str) -> str:
    """Convert cookie env var to ``k=v; ...`` format.

    Accepts either a JSON object (``{"k": "v", ...}``) or a bare
    ``substack.sid`` session cookie value.
    """
    try:
        cookie_dict = json.loads(raw)
        return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
    except (json.JSONDecodeError, AttributeError):
        return f"substack.sid={raw}"


SUBSTACK_SID = os.environ.get("SUBSTACK_SID")


def _get_api() -> Api:
    """Authenticate with Substack, trying cookies first, then email/password."""
    if SUBSTACK_SID:
        logger.info("Authenticating with cookies from SUBSTACK_SID env var")
        try:
            api = Api(
                cookies_string=_cookies_string_from_env(SUBSTACK_SID),
                publication_url=SUBSTACK_URL,
            )
            api.get_user_id()
            return api
        except Exception as e:
            logger.warning("Cookie env auth failed (%s), falling back", e)

    if not SUBSTACK_EMAIL or not SUBSTACK_PASSWORD:
        raise ValueError(
            "SUBSTACK_EMAIL and SUBSTACK_PASSWORD must be set when cookies are unavailable"
        )

    logger.info("Authenticating with email/password")
    api = Api(email=SUBSTACK_EMAIL, password=SUBSTACK_PASSWORD, publication_url=SUBSTACK_URL)
    return api


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def post_substack_draft(title: str, content: str, subtitle: str = "本新聞摘要由AI自動生成。") -> dict:
    """Create a Substack draft post from Markdown content.

    Preserves the same interface as the old substack_playwright.post_substack_draft().

    Args:
        title: Post title.
        content: Markdown-formatted post body.
        subtitle: Post subtitle.

    Returns:
        Dict with draft response from Substack API (includes "id" field).
    """
    api = _get_api()
    user_id = api.get_user_id()
    logger.info("Authenticated as user %s", user_id)

    post = Post(
        title=title,
        subtitle=subtitle,
        user_id=user_id,
    )
    post.draft_body = _markdown_to_draft_body(content)

    draft = api.post_draft(post.get_draft())
    draft_id = draft.get("id")
    logger.info("Draft created successfully (id=%s)", draft_id)
    print(f"Draft created successfully (id={draft_id})")

    return draft


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = post_substack_draft(
        title="Test Draft",
        content="## Hello\n\n**This is a test draft.**\n\n- Item 1\n- Item 2\n",
    )
    print(json.dumps(result, indent=2, default=str))
