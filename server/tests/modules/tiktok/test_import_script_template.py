import pytest

from modules.tiktok.scripts.import_script_template import DEFAULT_PATH, parse_template


def test_parses_bundled_template():
    template_id, fields = parse_template(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert template_id == 1
    assert fields.name == "服装开袋试穿脚本"
    assert (fields.category, fields.duration_seconds) == ("all", 15)
    assert (fields.status, fields.version, fields.reference_video_url) == ("formal", "1.0.0", None)
    assert fields.content.startswith("# 服装开袋试穿脚本｜完整母框架")
    assert fields.content.endswith("直接交给另一个模型执行。")


def test_maps_chinese_values_and_keeps_inline_content():
    text = (
        "模板ID: 7\n模板名称：下装模板\n适合类目：下衣\n适合时长：60\n"
        "脚本内容：第一行\n第二行\n\n状态：测试\n版本：2.0.1\n参考视频：https://example.com/a\n"
    )
    template_id, fields = parse_template(text)
    assert template_id == 7
    assert (fields.category, fields.status) == ("bottom", "test")
    assert fields.content == "第一行\n第二行"
    assert fields.reference_video_url == "https://example.com/a"


def test_missing_field_is_rejected():
    with pytest.raises(ValueError, match="版本"):
        parse_template("模板ID：1\n模板名称：x\n适合类目：上衣\n适合时长：15\n脚本内容：\n正文\n状态：正式\n参考视频：\n")
