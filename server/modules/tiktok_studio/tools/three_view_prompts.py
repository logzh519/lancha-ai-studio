"""three_view_gen 用到的视觉识别指令与生图提示词。

假人路线（上衣、套装、连衣裙/连体衣）把商品套到固定木质假人模板上；下装走无人物的单品三视图路线。
"""

from pathlib import Path

PRODUCT_ONLY_TEMPLATE = Path(__file__).with_name("three_view_assets") / "product_only_prompt.txt"

CLASSIFY_PRODUCT_INSTRUCTION = """You classify the actual sellable fashion product for an e-commerce three-view generator.
Use product text facts as the primary evidence of what the ASIN sells. Use the image only as supporting evidence; a model may wear styling pieces that are not included in the sale.
Return JSON only: {"category":"upper|bottom|set|one_piece|uncertain","confidence":0.00,"reason":"short Chinese reason"}.
Definitions: upper=only a top is sold; bottom=only pants/skirt/shorts are sold; set=matching upper and lower are both sold; one_piece=dress/jumpsuit/romper is one complete garment.
If the text and image conflict, or the sale scope cannot be established confidently, return uncertain. Do not guess."""

DETAIL_LOCK_INSTRUCTION = """You are a product-fact inspector for a high-fidelity garment image workflow.
The images are already selected factual references in this exact upload order: FRONT, BACK, and optional SIDE. Identify only clearly visible, product-specific facts that the image generator must not omit or redesign.

Prioritize distinctive construction details that generic garment generation commonly loses: thumb holes, unusual cuffs, raglan or panel seams, neckline construction, side slits, curved/high-low hems, pockets, zippers, buttons, ties, pleats, prints, trims, and exact front/back/side structural connections. Also include clearly supported color, surface texture, sheen, thickness impression, drape, length, looseness, and proportion facts when visually distinctive.

Do not describe the model, pose, hair, jewelry, jeans, styling pieces, background, shadows, or photography. Do not mistake a hand position, body pose, fold, or occlusion for a garment feature. Do not infer hidden details. If a fact is uncertain, omit it rather than guess.

Return JSON only in this exact shape:
{"critical_details":[{"fact":"concise English imperative product lock","confidence":0.00}],"mannequin_limb_support":"required|not_required","limb_reason":"short English reason"}
Every fact must be directly visible and actionable for image generation. Use confidence >= 0.85 only when the evidence is clear.
Set mannequin_limb_support to required only when a clearly visible garment construction must be worn over or around a limb to be represented truthfully, such as a thumb-hole cuff, fingerless glove construction, stirrup hem, or comparable wearable opening. Ordinary sleeves, cuffs, armholes, pant legs, and hems are not enough. Human hands in a reference are never themselves a product fact."""

PRODUCT_RESTORATION_RULES = """PRODUCT RESTORATION PRIORITY RULES (mandatory):
The reference images are factual evidence of the sellable product, not style inspiration. Preserve the actual product; do not redesign, beautify, optimize, or complete it from common fashion knowledge.

VIEW-SPECIFIC AUTHORITY:
- Generate the front view from the FRONT reference. Its visible front structure, color, fit, and details override other references.
- Generate the back view from the BACK reference. Its visible back neckline, back panel, back pockets, zippers, closures, and details override other references.
- If a SIDE reference is present, generate the side silhouette from it. If absent, make only the simplest conservative connection supported by the front and back; never invent complex side features.
- The three outputs must show exactly the same product, color, material, and sellable scope.

LOCK THESE VISIBLE FACTS: color and tonal range; visible fabric texture, sheen, thickness impression, drape or stiffness; neckline, sleeve, straps, waistband, hems, cuffs, legs, or skirt shape; pockets, zippers, buttons, ties, seams, pleats; prints, lace, embroidery, wash effects, distressing, and visible decorations; length, looseness, and proportions.

DO NOT: change color, material appearance, sheen, texture, length, or fit; add, remove, move, hide, or replace any visible pocket, zipper, button, tie, seam, print, trim, or decoration; turn one material into another; add a design because it is common for this garment type; make uncertain areas ornate or complex. Unobserved details must stay simple and neutral.

TYPE SCOPE: obey the selected sellable type. For an upper, show only the sold top. For a bottom, show only the sold bottom. For a set, every view must include both the sold upper and lower as one complete matching set. For a dress or jumpsuit, preserve one complete garment and never split it into upper and lower.

OUTPUT LOCK: preserve the existing clean product-only three-view layout, white background, neutral even light, and no-person requirement. Do not bring people, body parts, styling items, props, scenery, text, logos, watermarks, or extra products from the references into the result.

FINAL SELF-CHECK: before output, verify front follows the FRONT reference, back follows the BACK reference, and side follows the SIDE reference when present. Verify no color shift, material substitution, invented or omitted visible detail, or mismatch of product/color/material across the three views. When accuracy conflicts with beauty, product accuracy always wins."""

DUMMY_TRYON_RULES = """FIXED DUMMY TRY-ON THREE-VIEW RULES (mandatory):
Image 1 is the immutable full-body wooden dummy triptych template. Preserve its canvas, side-front-back panel order, dummy identity, full-body proportions, pose, wooden arms, hands, fingers, legs, feet, camera height, framing, white background, and neutral even lighting exactly. Replace only the garment. Do not delete, move, reshape, duplicate, or regenerate any wooden body part. Do not add a human head, face, realistic skin, accessories, scenery, text, logos, watermarks, extra products, metal support rods, knobs, clamps, connectors, or bases.

The remaining images are factual product evidence, not style inspiration: Image 2 is the true FRONT product reference; Image 3 is the true BACK product reference; Image 4, if present, is the true SIDE product reference. The front dummy view must follow Image 2, the back dummy view must follow Image 3, and the side dummy view must follow Image 4 when present. If no side reference exists, create only the simplest neutral side connection supported by front and back; never invent complex structures.

Lock all visible product facts: exact color and tonal range, fabric texture and sheen, thickness impression, drape or stiffness, neckline, sleeves, straps, waistband, hems, cuffs, legs or skirt shape, pockets, zippers, buttons, ties, seams, pleats, prints, lace, embroidery, wash effects, distressing, decorations, length, looseness, and proportion. Do not change, add, remove, hide, move, beautify, or redesign any visible product fact. Do not infer common fashion features that are not visible. Uncertain areas must remain simple and neutral.

Type scope is mandatory: upper = dress only the torso and arms in the sold top while uncovered lower areas remain the original wooden dummy; bottom = dress only the lower body in the sold bottom while uncovered upper areas remain the original wooden dummy; set = every panel includes both sold upper and lower as one matching outfit; one-piece = one complete dress/jumpsuit and never split it into separate garments. All three dummy views must be the same colorway, material, and sellable product.

Before output, verify product structure first, then color, material appearance, details, fit/proportion, wooden dummy consistency, absence of support hardware, and only then visual beauty. Product accuracy always wins."""

TYPE_LABELS = {
    "upper": "upper (only the sold top)",
    "bottom": "bottom (only the sold bottom)",
    "set": "set (the sold matching upper and lower together)",
    "one_piece": "one-piece (one complete dress or jumpsuit)",
}


def input_layout(side_kind: str) -> str:
    """参考图上传顺序的中文描述，同时写进提示词与细节识别请求。"""
    if side_kind == "none":
        return "正面 + 背面"
    if side_kind == "true_side":
        return "正面 + 背面 + 侧面"
    return "正面 + 背面 + 斜侧面（侧面证据）"


def rules_for_template(template: str) -> str:
    if template != "v3":
        return DUMMY_TRYON_RULES
    return DUMMY_TRYON_RULES.replace(
        "immutable full-body wooden dummy triptych template",
        "immutable upper-body wooden dummy triptych template with complete wooden arms and hands",
    ).replace(
        "full-body proportions, pose, wooden arms, hands, fingers, legs, feet",
        "upper-body proportions, pose, wooden torso, arms, hands, and fingers",
    ) + """

V3 TEMPLATE SCOPE LOCK (mandatory): This template is only for an upper garment. Preserve its existing cropped lower-torso boundary and complete wooden arms and hands exactly. Do not extend the canvas into a full body and do not invent wooden legs or feet. The sold upper garment may cover the torso and arms only; every uncovered area remains the original wooden dummy."""


def render_dummy_prompt(
    category: str,
    layout: str,
    critical_details: list[str],
    side_kind: str,
    mannequin_limb_required: bool,
    template: str,
) -> str:
    original_prompt = f"""Generate exactly one photorealistic fixed dummy try-on triptych. The input order is: template + {layout}. Selected sellable type: {TYPE_LABELS[category]}.

{rules_for_template(template)}"""
    if side_kind == "true_side":
        side_rule = "The final product reference is a true side view and is authoritative for the side silhouette and all clearly visible lateral construction."
    elif side_kind in {"front_three_quarter", "back_three_quarter"}:
        side_rule = "The final product reference is an oblique three-quarter SIDE-EVIDENCE image, not a literal side-view template. Use it only to lock clearly visible side seam, slit, front/back hem relationship, cuff profile, thickness, lateral silhouette, and drape. Do not copy the model's pose or camera perspective."
    else:
        side_rule = "No reliable side-evidence image is supplied. Build only the simplest conservative side connection supported by the confirmed front and back; do not invent complex lateral structures."
    if mannequin_limb_required:
        limb_rule = """WEARABLE-OPENING USE OF THE EXISTING WOODEN LIMBS: The fixed template already supplies every required arm, hand, finger, leg, and foot. Do not add or regenerate a limb. Use only the existing wooden limb to demonstrate the real wearable construction. For a thumb-hole cuff, route the existing wooden thumb naturally through the actual thumb opening and the remaining existing wooden hand through the main cuff opening. For a stirrup or comparable foot opening, route the existing wooden foot through the actual product opening. Keep the original wood finish, anatomy, finger count, joint positions, and pose unchanged. Never create realistic skin, flesh tones, pores, veins, fingernails, nail polish, jewelry, copied human anatomy, floating parts, severed parts, duplicate hands, or extra limbs."""
    else:
        limb_rule = """No special wearable opening requires limb routing. Keep every existing wooden arm, hand, finger, leg, and foot exactly as supplied by the fixed template. Dress or expose them only according to the actual product type and ordinary sleeve, cuff, waist, hem, leg, and shoe-free openings. Do not add, delete, reshape, duplicate, or replace any limb."""
    isolation_lock = f"""

REFERENCE EVIDENCE AND HUMAN-CONTAMINATION ISOLATION (additional; this does not replace or weaken any rule above):
{side_rule}
Extract the garment only from every product reference. The reference model, head, hair, arms, hands, fingers, skin, jewelry, jeans, shoes, pose, and accessories are contamination and must never appear in the output.
{limb_rule}
Product-detail preservation never authorizes copying human anatomy from a reference image.
The output must contain no metal support pole, stand, knob, clamp, connector, bracket, or base; do not recreate hardware from any older template or prior output.
Keep the exact product color and tonal range shown by the same-color references. Do not normalize, brighten, pastelize, desaturate, or shift the garment color to match the dummy template or studio lighting."""
    if not critical_details:
        return original_prompt + isolation_lock
    detail_lines = "\n".join(f"- {detail}" for detail in critical_details)
    additional_lock = f"""

PRODUCT-SPECIFIC CRITICAL DETAIL LOCK (additional; this does not replace or weaken any rule above):
The following facts were extracted from this product's confirmed front, back, and optional side references. Preserve every listed fact visibly in its corresponding view. Do not simplify it into a more common garment construction.
{detail_lines}

MANDATORY PRODUCT CHECK: Before output, compare the generated front against the confirmed FRONT reference, the back against the confirmed BACK reference, and the side against the confirmed side or oblique side-evidence reference when supplied. Do not output a result that omits, converts, hides, relocates, or redesigns any listed critical detail. If a listed detail is not relevant to a view, preserve it in every view where it should naturally be visible."""
    return original_prompt + isolation_lock + additional_lock


def render_bottom_prompt(product_code: str, color: str, asin: str, layout: str) -> str:
    """下装的单品三视图提示词：不上传假人模板，参考图即 Image 1 起。"""
    template = PRODUCT_ONLY_TEMPLATE.read_text(encoding="utf-8")
    template = template.replace("基于参考图中的服装", "基于参考图中的目标下装")
    template = template.replace("三件服装视图", "三件下装视图")
    template = template.replace(
        "只展示目标服装本身，不出现真人、不出现模特、不出现人脸、不出现皮肤、不出现手臂、不出现腿、不出现裤子、不出现鞋、不出现饰品。",
        "只展示目标下装本身，不出现真人、不出现模特、不出现人脸、不出现皮肤、不出现手臂、不出现腿、不出现上衣、不出现鞋、不出现饰品。",
    )
    template = template.replace("同一件服装的三个角度", "同一件下装的三个角度")
    template = template.replace("三件服装主体", "三件下装主体")
    template = template.replace(
        "左侧正面：完整展示领口、袖型、胸前结构、下摆和整体宽松度。\n中间45度微侧面：展示厚度、侧缝、袖口、衣身垂坠和下摆弧度。\n右侧背面：完整展示后领、背部版型、袖背、下摆和后片轮廓。",
        "左侧正面：完整展示腰头、前片结构、口袋（如参考图存在）、裆部、裤腿或裙摆轮廓和整体宽松度。\n中间45度微侧面：展示腰侧结构、侧缝、裤腿或裙摆垂坠、长度和版型厚度。\n右侧背面：完整展示后腰、后片、后袋（如参考图存在）、后侧缝及裤腿或裙摆轮廓。",
    )
    template = template.replace("不要裤子，不要鞋", "不要上衣，不要鞋")
    rendered = template.format(product_code=product_code, color=color, asin=asin)
    return f"""Reference-image roles and priority: product facts are supplied as separate original Amazon images, never as a collage. Their upload order is {layout}.
Image 1 is the true FRONT reference and is authoritative for front structure, color, fit, and visible front details. Image 2 is the true BACK reference and is authoritative for back structure and visible back details. If Image 3 is present, it is the SIDE reference and is authoritative only for the side silhouette and visible side details.
All images show the same ASIN, color, and sellable product. Do not treat them as different products. Do not invent pockets, zippers, prints, trims, or other unobserved details merely because they are common for this garment type.

{PRODUCT_RESTORATION_RULES}

{rendered}"""
