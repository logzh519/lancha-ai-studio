"""从 txt 导入一条爆款脚本模板，模板 ID 已存在时跳过。

在 server 目录执行：python -m modules.tiktok.scripts.import_script_template [txt 路径]

txt 格式：开头是「模板ID / 模板名称 / 适合类目 / 适合时长」，随后「脚本内容:」之后直到
结尾「状态 / 版本 / 参考视频」之前的全部内容为脚本正文。键值分隔符中英文冒号均可。
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from modules.tiktok import service
from modules.tiktok.schemas import ScriptTemplateFields
from platforms.db import dispose_engine, session_scope

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "docs" / "服装开袋试穿脚本模板.txt"

HEADER_KEYS = {"模板ID": "id", "模板名称": "name", "适合类目": "category", "适合时长": "duration_seconds"}
FOOTER_KEYS = {"状态": "status", "版本": "version", "参考视频": "reference_video_url"}
CONTENT_KEY = "脚本内容"
CATEGORIES = {"全品类": "all", "上衣": "top", "下衣": "bottom"}
STATUSES = {"正式": "formal", "测试": "test"}

_FIELD = re.compile(r"^\s*([^:：\s]+)\s*[:：]\s*(.*?)\s*$")


def _field(line: str) -> tuple[str, str] | None:
    match = _FIELD.match(line)
    return (match.group(1), match.group(2)) if match else None


def parse_template(text: str) -> tuple[int, ScriptTemplateFields]:
    lines = text.splitlines()
    content_at = next((i for i, line in enumerate(lines) if (f := _field(line)) and f[0] == CONTENT_KEY), None)
    if content_at is None:
        raise ValueError(f"缺少「{CONTENT_KEY}」")

    values: dict[str, str] = {}
    for line in lines[:content_at]:
        if (f := _field(line)) and f[0] in HEADER_KEYS:
            values[HEADER_KEYS[f[0]]] = f[1]

    end = len(lines)
    while end > content_at + 1:
        line = lines[end - 1]
        f = _field(line)
        if f and f[0] in FOOTER_KEYS:
            values[FOOTER_KEYS[f[0]]] = f[1]
        elif line.strip():
            break
        end -= 1

    missing = [key for key, name in {**HEADER_KEYS, **FOOTER_KEYS}.items() if name not in values]
    if missing:
        raise ValueError(f"缺少字段：{'、'.join(missing)}")

    inline = _field(lines[content_at])[1]
    content = "\n".join(([inline] if inline else []) + lines[content_at + 1 : end]).strip()
    fields = ScriptTemplateFields(
        name=values["name"],
        category=CATEGORIES.get(values["category"], values["category"]),
        duration_seconds=int(values["duration_seconds"]),
        content=content,
        status=STATUSES.get(values["status"], values["status"]),
        version=values["version"],
        reference_video_url=values["reference_video_url"] or None,
    )
    return int(values["id"]), fields


async def main(path: Path) -> None:
    template_id, fields = parse_template(path.read_text(encoding="utf-8"))
    try:
        async with session_scope() as session:
            if await service.get_script_template(session, template_id) is not None:
                print(f"模板 {template_id} 已存在，跳过")
                return
            await service.create_script_template(session, fields, created_by=None, template_id=template_id)
        print(f"已导入模板 {template_id}：{fields.name}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
    asyncio.run(main(args.path), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
