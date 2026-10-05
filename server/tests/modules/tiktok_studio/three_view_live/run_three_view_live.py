"""three_view_gen 真实调用验证：会调用 OpenAI 视觉与生图、上传 TOS，产生真实费用。不被 pytest 收集。

用法（在 server 目录）：python tests/modules/tiktok_studio/three_view_live/run_three_view_live.py [样例根目录]

每个样例：本地输入图上传 TOS → amazon_crawler 取标题/卖点（失败则不带文案）→ view_select 选正背侧 → three_view_gen 生图。
结果写到本目录 output/<job_id>/，并附上原工程的输出图便于对比。
"""

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

import httpx

from modules.tiktok_studio import tools
from platforms.llm import AsyncLLMClient
from platforms.storage import get_storage

SAMPLE_ROOT = Path("/mnt/d/Lancha/完整工作台数据包_20260924/extract")
OUTPUT_ROOT = Path(__file__).with_name("output")
TYPE_MAP = {"自动判断": "auto", "上衣": "upper", "下装": "bottom", "套装": "set", "连衣裙/连体衣": "one_piece"}
CRAWL_TIMEOUT = 30.0
VIEW_TIMEOUT = 120.0
GEN_TIMEOUT = 300.0


async def run_job(job_dir: Path, deps: tools.ToolDeps, storage) -> dict:
    spec = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    job_id, product = spec["job_id"], spec["product"]
    out_dir = OUTPUT_ROOT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = f"live:{product['asin']}"
    summary: dict = {"job_id": job_id, "requested_type": spec.get("generation_type")}

    urls = []
    for index, name in enumerate(spec["images"], start=1):
        key = f"three_view_live/{product['asin']}/{job_dir.name[-12:]}/{index:02d}{Path(name).suffix}"
        record = await asyncio.to_thread(storage.upload_file, key, job_dir / name)
        urls.append(record.url)

    crawl = await tools.build("amazon_crawler", deps).execute(
        {"asin": product["asin"]}, tools.ToolSettings(timeout=CRAWL_TIMEOUT, trace_id=trace),
    )
    facts = {"title": None, "bullet_points": [], "description": None}
    if crawl.success:
        facts = {k: crawl.output[k] for k in facts}
    summary["amazon_crawler"] = {"success": crawl.success, "error": crawl.error_message, **facts}

    view = await tools.build("view_select", deps).execute(
        {"images": urls, **facts}, tools.ToolSettings(timeout=VIEW_TIMEOUT, trace_id=trace),
    )
    summary["view_select"] = view.output if view.success else {"error_code": view.error_code, "error": view.error_message}
    if not view.success:
        return summary

    payload = {
        "asin": product["asin"], "product_code": product.get("product_code", ""), "color": product.get("color", ""),
        **facts,
        "front_url": view.output["front_url"], "back_url": view.output["back_url"],
        "side_url": view.output["side_url"], "side_kind": view.output["side_kind"],
        "generation_type": TYPE_MAP.get(spec.get("generation_type"), "auto"),
    }
    gen = await tools.build("three_view_gen", deps).execute(
        payload, tools.ToolSettings(timeout=GEN_TIMEOUT, trace_id=trace),
    )
    summary["three_view_gen"] = gen.output if gen.success else {"error_code": gen.error_code, "error": gen.error_message}

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        for role in ("front", "back", "side"):
            if view.output.get(f"{role}_url"):
                response = await http.get(view.output[f"{role}_url"])
                (out_dir / f"reference_{role}.jpg").write_bytes(response.content)
        if gen.success:
            (out_dir / "prompt.txt").write_text(gen.output["prompt"], encoding="utf-8")
            response = await http.get(gen.output["image"]["url"])
            response.raise_for_status()
            (out_dir / "three_view.png").write_bytes(response.content)
    for original in (SAMPLE_ROOT / "output" / job_id).glob("*.png"):
        shutil.copy2(original, out_dir / f"original_{original.name}")
    return summary


async def main() -> int:
    global SAMPLE_ROOT
    if len(sys.argv) > 1:
        SAMPLE_ROOT = Path(sys.argv[1])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    storage = get_storage()
    llm = AsyncLLMClient(provider="lch_tk")
    deps = tools.ToolDeps(session=None, storage=storage, llm=llm)
    failed = 0
    try:
        for job_dir in sorted(p.parent for p in (SAMPLE_ROOT / "input").glob("*/job.json")):
            summary = await run_job(job_dir, deps, storage)
            out_dir = OUTPUT_ROOT / summary["job_id"]
            (out_dir / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            gen = summary.get("three_view_gen") or {}
            failed += "image" not in gen
            print(f"RESULT {summary['job_id']}: {gen.get('workflow')} {gen.get('template')} "
                  f"{gen.get('error_code') or (gen.get('image') or {}).get('url') or summary.get('view_select')}")
    finally:
        await llm.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
