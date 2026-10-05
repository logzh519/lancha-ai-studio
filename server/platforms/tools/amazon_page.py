"""Amazon 商品详情页解析：标题、About this item 亮点、产品描述、主图副图。纯函数，不联网。"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

MAX_BULLETS = 10

COLOR_IMAGES_RE = re.compile(r"'colorImages'\s*:\s*\{\s*'initial'\s*:\s*A\.\$\.parseJSON\('(\[.*?\])'\)\s*\}", re.DOTALL)

GARBAGE_TEXT_MARKERS = [
    "skip to main content",
    "keyboard shortcuts",
    "deliver to hong kong",
    "all departments",
    "hello, sign in",
    "returns & orders",
    "we're showing you items that ship",
    "to move between items",
    "show/hide shortcuts",
]

# 按顺序尝试的亮点容器 id（兼容新版 product facts 与旧版 feature bullets 布局）
BULLET_CONTAINER_IDS = [
    "featurebullets_feature_div",
    "pqv-feature-bullets",
    "productFactsDesktopExpander",
    "feature-bullets",
    "productFactsDesktop_feature_div",
]

APLUS_NOISE_LINES = {
    "product description",
    "merchant video",
    "previous page",
    "next page",
    "hero-video",
    "aplus content video",
    "add to cart",
}
APLUS_NOISE_PREFIXES = ("the video ",)
APLUS_STOP_LINES = {"from the brand", "product details", "more recommendations"}

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "template"}
BLOCK_TAGS = {
    "address", "article", "br", "dd", "div", "dl", "dt", "footer", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "ol", "p", "section", "table", "td",
    "th", "tr", "ul",
}


@dataclass
class PageImage:
    variant: str        # MAIN 为主图，PT01、PT02… 为副图
    url: str


@dataclass
class AmazonPage:
    asin: str | None = None
    title: str | None = None
    bullet_points: list[str] = field(default_factory=list)
    description: str | None = None
    images: list[PageImage] = field(default_factory=list)


class Node:
    __slots__ = ("attrs", "children", "parent", "tag")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Any] = []
        self.parent = parent

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def iter(self) -> Iterator["Node"]:
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed([c for c in node.children if isinstance(c, Node)]))

    def find_all(self, tag: str, cls: str | None = None) -> list["Node"]:
        return [n for n in self.iter() if n.tag == tag and (cls is None or cls in n.classes) and n is not self]


class DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.current = self.root
        self.ids: dict[str, Node] = {}

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.current)
        self.current.children.append(node)
        node_id = node.attrs.get("id")
        if node_id and node_id not in self.ids:
            self.ids[node_id] = node
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.current = self.current.parent

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse_html(page_html: str) -> DomBuilder:
    builder = DomBuilder()
    builder.feed(page_html)
    builder.close()
    return builder


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def is_garbage_text(value: str | None) -> bool:
    text = (value or "").lower()
    if not text:
        return True
    return any(marker in text for marker in GARBAGE_TEXT_MARKERS)


def unique_keep_order(values: list[str | None]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


def text_lines(node: Node) -> list[str]:
    """按块级元素切分节点可见文本，返回去空白后的行列表。"""
    parts: list[str] = []

    def walk(current: Node) -> None:
        if current.tag in SKIP_TEXT_TAGS:
            return
        is_block = current.tag in BLOCK_TAGS
        if is_block:
            parts.append("\n")
        for child in current.children:
            if isinstance(child, Node):
                walk(child)
            else:
                parts.append(child)
        if is_block:
            parts.append("\n")

    walk(node)
    return [line for line in (clean_text(raw) for raw in "".join(parts).split("\n")) if line]


def node_text(node: Node) -> str | None:
    return clean_text(" ".join(text_lines(node)))


def detect_blocked_page(page_html: str) -> str | None:
    lower = page_html.lower()
    if "enter the characters you see below" in lower or "sorry, we just need to make sure" in lower:
        return "captcha_or_bot_check"
    if "robot check" in lower:
        return "robot_check"
    if "click the button below to continue shopping" in lower:
        return "continue_shopping_interstitial"
    return None


def extract_asin(dom: DomBuilder) -> str | None:
    for node in dom.root.iter():
        if node.tag == "input" and (node.attrs.get("id") == "ASIN" or node.attrs.get("name") == "ASIN"):
            value = node.attrs.get("value") or ""
            if re.fullmatch(r"[A-Z0-9]{10}", value, re.IGNORECASE):
                return value.upper()
    return None


def extract_title(dom: DomBuilder) -> str | None:
    node = dom.ids.get("productTitle")
    return node_text(node) if node else None


def extract_bullets(dom: DomBuilder) -> list[str]:
    bullets: list[str] = []
    for container_id in BULLET_CONTAINER_IDS:
        container = dom.ids.get(container_id)
        if not container:
            continue
        for li in container.find_all("li"):
            spans = li.find_all("span", "a-list-item")
            text = node_text(spans[0]) if spans else node_text(li)
            if text and "make sure this fits" not in text.lower() and not is_garbage_text(text):
                bullets.append(text)
    return unique_keep_order(bullets)[:MAX_BULLETS]


def extract_aplus_description(dom: DomBuilder) -> str | None:
    container = dom.ids.get("aplus_feature_div") or dom.ids.get("aplus")
    if not container:
        return None
    lines: list[str] = []
    for line in text_lines(container):
        lower = line.lower()
        if lower in APLUS_STOP_LINES:
            break
        if lower in APLUS_NOISE_LINES or lower.startswith(APLUS_NOISE_PREFIXES) or re.fullmatch(r"\d+", line):
            continue
        lines.append(line)
    return "\n".join(unique_keep_order(lines)) or None


def extract_description(dom: DomBuilder) -> str | None:
    node = dom.ids.get("productDescription")
    if node:
        text = "\n".join(unique_keep_order(text_lines(node)))
        if text and not is_garbage_text(text):
            return text
    return extract_aplus_description(dom)


def extract_images(page_html: str) -> list[PageImage]:
    """读取商品图集 colorImages.initial，仅含当前颜色。"""
    match = COLOR_IMAGES_RE.search(page_html)
    if not match:
        return []
    try:
        entries = json.loads(match.group(1).replace("\\'", "'"))
    except json.JSONDecodeError:
        return []
    images = []
    for entry in entries:
        url = entry.get("hiRes") or entry.get("large")
        if url:
            images.append(PageImage(variant=entry.get("variant") or "", url=url))
    return images


def parse_product_page(page_html: str) -> AmazonPage:
    dom = parse_html(page_html)
    return AmazonPage(
        asin=extract_asin(dom),
        title=extract_title(dom),
        bullet_points=extract_bullets(dom),
        description=extract_description(dom),
        images=extract_images(page_html),
    )
