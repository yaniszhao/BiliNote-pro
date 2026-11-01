"""思考强度（reasoning_effort）回归测试。

覆盖三条路径：
1. 配置了 reasoning_effort 时，create 调用必须带上该参数；
2. 模型不认识 reasoning_effort 时，自动去掉参数重试并成功；
3. reasoning_effort=None 时不传该参数（走模型端默认）。
"""
import importlib.util
import pathlib
import sys
import types
import unittest


def _install_stubs():
    app_mod = types.ModuleType("app")
    gpt_pkg = types.ModuleType("app.gpt")
    models_pkg = types.ModuleType("app.models")

    base_mod = types.ModuleType("app.gpt.base")

    class _GPT:
        pass

    base_mod.GPT = _GPT

    prompt_builder_mod = types.ModuleType("app.gpt.prompt_builder")

    def _generate_base_prompt(**_kwargs):
        return "PROMPT_BODY"

    prompt_builder_mod.generate_base_prompt = _generate_base_prompt

    prompt_mod = types.ModuleType("app.gpt.prompt")
    prompt_mod.BASE_PROMPT = ""
    prompt_mod.AI_SUM = ""
    prompt_mod.SCREENSHOT = ""
    prompt_mod.LINK = ""
    prompt_mod.MERGE_PROMPT = "MERGE_HEAD"

    utils_mod = types.ModuleType("app.gpt.utils")

    def _fix_markdown(text):
        return text

    utils_mod.fix_markdown = _fix_markdown

    request_chunker_mod = types.ModuleType("app.gpt.request_chunker")

    class _RequestChunker:
        def __init__(self, *_args, **_kwargs):
            pass

        def group_texts_by_budget(self, texts, _builder, **_kwargs):
            return [texts]

    request_chunker_mod.RequestChunker = _RequestChunker

    gpt_model_mod = types.ModuleType("app.models.gpt_model")

    class _GPTSource:
        pass

    gpt_model_mod.GPTSource = _GPTSource

    transcriber_model_mod = types.ModuleType("app.models.transcriber_model")

    class _TranscriptSegment:
        def __init__(self, **kwargs):
            self.start = kwargs.get("start", 0)
            self.end = kwargs.get("end", 0)
            self.text = kwargs.get("text", "")

    transcriber_model_mod.TranscriptSegment = _TranscriptSegment

    sys.modules.setdefault("app", app_mod)
    sys.modules.setdefault("app.gpt", gpt_pkg)
    sys.modules.setdefault("app.models", models_pkg)
    sys.modules["app.gpt.base"] = base_mod
    sys.modules["app.gpt.prompt_builder"] = prompt_builder_mod
    sys.modules["app.gpt.prompt"] = prompt_mod
    sys.modules["app.gpt.utils"] = utils_mod
    sys.modules["app.gpt.request_chunker"] = request_chunker_mod
    sys.modules["app.models.gpt_model"] = gpt_model_mod
    sys.modules["app.models.transcriber_model"] = transcriber_model_mod


def _load_universal_gpt_class():
    _install_stubs()
    root = pathlib.Path(__file__).resolve().parents[1]
    module_path = root / "app" / "gpt" / "universal_gpt.py"
    spec = importlib.util.spec_from_file_location(
        "universal_gpt_reasoning_effort", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError("universal_gpt module spec not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UniversalGPT


UniversalGPT = _load_universal_gpt_class()


class _RecordingClient:
    """记录每次 create 调用的 kwargs，按预设脚本抛错或返回。"""

    def __init__(self, failures=None):
        self.calls = []
        self.failures = list(failures or [])

    def _completions_create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return self._make_response()

    @staticmethod
    def _make_response():
        class _Msg:
            content = "ok"

        class _Choice:
            message = _Msg()

        class _Response:
            choices = [_Choice()]

        return _Response()

    @property
    def chat(self):
        outer = self

        class _Completions:
            @staticmethod
            def create(**kwargs):
                return outer._completions_create(**kwargs)

        class _Chat:
            completions = _Completions()

        return _Chat()


class TestReasoningEffort(unittest.TestCase):
    def test_effort_passed_to_create(self):
        """配置 low 时 create 请求带上 reasoning_effort='low'。"""
        client = _RecordingClient()
        gpt = UniversalGPT(client, model="z-ai/glm-5.3-flash", reasoning_effort="low")

        gpt._do_create([{"role": "user", "content": "hi"}])

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["reasoning_effort"], "low")
        self.assertEqual(client.calls[0]["temperature"], 0.7)

    def test_unsupported_effort_strips_and_retries(self):
        """普通模型不认识 reasoning_effort 时，去掉该参数重试一次并成功。"""
        client = _RecordingClient(failures=[ValueError("unrecognized argument: reasoning_effort")])
        gpt = UniversalGPT(client, model="deepseek-chat", reasoning_effort="low")

        response = gpt._do_create([{"role": "user", "content": "hi"}])

        self.assertEqual(response.choices[0].message.content, "ok")
        self.assertEqual(len(client.calls), 2)
        self.assertNotIn("reasoning_effort", client.calls[1])
        self.assertEqual(client.calls[1]["temperature"], 0.7)

    def test_none_effort_not_sent(self):
        """reasoning_effort=None 时不传该参数，走模型端默认。"""
        client = _RecordingClient()
        gpt = UniversalGPT(client, model="gpt-4o", reasoning_effort=None)

        gpt._do_create([{"role": "user", "content": "hi"}])

        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("reasoning_effort", client.calls[0])

    def test_unsupported_effort_does_not_break_temperature(self):
        """去掉 reasoning_effort 重试时，temperature 仍然保留。"""
        client = _RecordingClient(failures=[ValueError("unexpected value: reasoning_effort")])
        gpt = UniversalGPT(client, model="qwen-max", reasoning_effort="high")

        gpt._do_create([{"role": "user", "content": "hi"}])

        self.assertNotIn("reasoning_effort", client.calls[1])
        self.assertIn("temperature", client.calls[1])

    def test_default_effort_is_low(self):
        """不显式传 reasoning_effort 时默认为 low。"""
        client = _RecordingClient()
        gpt = UniversalGPT(client, model="test-model")

        self.assertEqual(gpt.reasoning_effort, "low")

    def test_source_signature_changes_with_effort(self):
        """reasoning_effort 变化要改变 checkpoint 签名，避免命中旧缓存。"""
        client = _RecordingClient()

        class _Source:
            title = "t"
            tags = ""
            _format = []
            style = ""
            extras = ""
            video_img_urls = []
            segment = []

        gpt_a = UniversalGPT(client, model="m", reasoning_effort="low")
        gpt_b = UniversalGPT(client, model="m", reasoning_effort="high")

        self.assertNotEqual(
            gpt_a._build_source_signature(_Source()),
            gpt_b._build_source_signature(_Source()),
        )


if __name__ == "__main__":
    unittest.main()
