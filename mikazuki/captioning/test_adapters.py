import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from mikazuki.captioning.adapters import (
    CLTaggerProvider,
    CaptionModelManager,
    CaptionProvider,
    CaptionProviderError,
    CaptionProviderUnavailableError,
    ChatVLMCaptionProvider,
    TransformersCaptionProvider,
    WDTaggerProvider,
    _load_chat_vlm,
    postprocess_tag_groups,
    select_onnx_providers,
)
from mikazuki.captioning.models import (
    CaptionPostprocessOptions,
    CaptionPrediction,
    CaptionPromptOptions,
    CaptionRuntimeOptions,
)


class FakeOnnxInput:
    def __init__(self, shape):
        self.name = "images"
        self.shape = shape


class FakeOnnxSession:
    def __init__(self, outputs, shape):
        self._outputs = np.asarray(outputs, dtype=np.float32)
        self._input = FakeOnnxInput(shape)
        self.received = []

    def get_inputs(self):
        return [self._input]

    def run(self, output_names, inputs):
        self.received.append((output_names, inputs))
        batch_size = next(iter(inputs.values())).shape[0]
        return [self._outputs[:batch_size]]


class OnnxProviderSelectionTests(unittest.TestCase):
    def test_auto_prefers_available_accelerator_with_cpu_fallback(self):
        providers = select_onnx_providers(
            "auto",
            ["CPUExecutionProvider", "CUDAExecutionProvider"],
        )
        self.assertEqual(providers, ["CUDAExecutionProvider", "CPUExecutionProvider"])

    def test_cpu_never_requests_gpu_provider(self):
        providers = select_onnx_providers(
            "cpu",
            ["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.assertEqual(providers, ["CPUExecutionProvider"])

    def test_explicit_cuda_fails_instead_of_silently_using_cpu(self):
        with self.assertRaises(CaptionProviderUnavailableError):
            select_onnx_providers("cuda", ["CPUExecutionProvider"])

    def test_openvino_is_auto_acceleration_not_claimed_as_cuda(self):
        self.assertEqual(
            select_onnx_providers("auto", ["OpenVINOExecutionProvider", "CPUExecutionProvider"]),
            ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
        )
        with self.assertRaises(CaptionProviderUnavailableError):
            select_onnx_providers("cuda", ["OpenVINOExecutionProvider", "CPUExecutionProvider"])


class TagPostprocessTests(unittest.TestCase):
    def test_postprocess_does_not_mutate_and_missing_exclusion_is_safe(self):
        groups = {
            "rating": [("general", 0.9), ("explicit", 0.1)],
            "general": [("long_hair", 0.8), ("blue_hair", 0.7)],
            "character": [("hatsune_miku", 0.65)],
        }
        original = copy.deepcopy(groups)
        result = postprocess_tag_groups(
            groups,
            threshold=0.5,
            character_threshold=0.6,
            add_rating_tag=True,
            options=CaptionPostprocessOptions(
                additionalTags=["solo", "solo"],
                excludeTags=["does_not_exist", "long hair"],
                replaceUnderscore=True,
            ),
        )

        self.assertEqual(groups, original)
        self.assertEqual([tag.text for tag in result.tags], ["solo", "general", "blue hair", "hatsune miku"])
        self.assertNotIn("long hair", result.text)

    def test_non_finite_scores_are_json_safe(self):
        result = postprocess_tag_groups({"general": [("bad", float("nan")), ("good", 0.8)]})
        self.assertEqual([tag.text for tag in result.tags], ["good"])
        self.assertIsNone(result.raw["categories"]["general"][0]["score"])


class WDTaggerProviderTests(unittest.TestCase):
    def test_csv_category_column_drives_groups_without_first_four_assumption(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "model.onnx"
            model_path.write_bytes(b"fake")
            labels_path = root / "selected_tags.csv"
            labels_path.write_text(
                "tag_id,name,category,count\n"
                "1,1girl,0,100\n"
                "2,general,9,100\n"
                "3,hatsune_miku,4,100\n",
                encoding="utf-8",
            )
            session = FakeOnnxSession([[0.9, 0.8, 0.7]], [None, 4, 4, 3])
            session_calls = []

            def download_fn(*, repo_id, filename, **kwargs):
                self.assertEqual(repo_id, "example/wd")
                return str(root / filename)

            def session_factory(path, *, providers):
                session_calls.append((path, providers))
                return session

            provider = WDTaggerProvider(
                "wd-test",
                "example/wd",
                download_fn=download_fn,
                session_factory=session_factory,
                available_providers_fn=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self.assertFalse(provider.loaded)
            predictions = provider.infer(
                Image.new("RGBA", (3, 2), (0, 0, 0, 0)),
                params={"threshold": 0.5, "characterThreshold": 0.6, "addRatingTag": True},
                device="auto",
            )

            self.assertTrue(provider.loaded)
            self.assertEqual(session_calls[0][1], ["CUDAExecutionProvider", "CPUExecutionProvider"])
            prediction = predictions[0]
            by_text = {tag.text: tag.category for tag in prediction.tags}
            self.assertEqual(by_text["1girl"], "general")
            self.assertEqual(by_text["general"], "rating")
            self.assertEqual(by_text["hatsune miku"], "character")
            self.assertEqual(session.received[0][1]["images"].shape, (1, 4, 4, 3))

    def test_invalid_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "model.onnx").write_bytes(b"fake")
            (root / "selected_tags.csv").write_text("name\n1girl\n", encoding="utf-8")
            provider = WDTaggerProvider(
                "wd-test",
                "example/wd",
                download_fn=lambda **kwargs: str(root / kwargs["filename"]),
                session_factory=lambda *args, **kwargs: FakeOnnxSession([[0.9]], [None, 4, 4, 3]),
                available_providers_fn=lambda: ["CPUExecutionProvider"],
            )
            with self.assertRaises(CaptionProviderError):
                provider.infer(Image.new("RGB", (2, 2)), device="cpu")


class CLTaggerProviderTests(unittest.TestCase):
    def test_mapping_categories_and_sigmoid_are_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "nested" / "model.onnx"
            mapping_path = root / "nested" / "tag_mapping.json"
            model_path.parent.mkdir()
            model_path.write_bytes(b"fake")
            mapping_path.write_text(
                json.dumps(
                    {
                        "idx_to_tag": {"0": "best_quality", "1": "character_name"},
                        "tag_to_category": {"best_quality": "Quality", "character_name": "Character"},
                    }
                ),
                encoding="utf-8",
            )
            session = FakeOnnxSession([[2.0, 1.0]], [None, 3, 4, 4])
            provider = CLTaggerProvider(
                "cl-test",
                "example/cl",
                model_filename="nested/model.onnx",
                tag_mapping_filename="nested/tag_mapping.json",
                download_fn=lambda **kwargs: str(root / kwargs["filename"]),
                session_factory=lambda *args, **kwargs: session,
                available_providers_fn=lambda: ["CPUExecutionProvider"],
            )
            prediction = provider.infer(
                Image.new("RGB", (2, 3), "white"),
                params={"threshold": 0.7, "characterThreshold": 0.7},
                device="cpu",
            )[0]

            self.assertEqual([tag.category for tag in prediction.tags], ["quality", "character"])
            self.assertGreater(prediction.tags[0].score, 0.8)
            self.assertEqual(session.received[0][1]["images"].shape, (1, 3, 4, 4))


class FakeBatch(dict):
    def __init__(self, image_count):
        super().__init__({"pixel_values": list(range(image_count))})
        self.device = None

    def to(self, device):
        self.device = device
        return self


class FakeProcessor:
    def __init__(self):
        self.calls = []
        self.last_batch = None

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        self.last_batch = FakeBatch(len(kwargs["images"]))
        return self.last_batch

    def batch_decode(self, generated, skip_special_tokens):
        return [f"caption {index}" for index, _ in enumerate(generated)]


class FakeTransformerModel:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return list(range(len(kwargs["pixel_values"])))


class TransformersCaptionProviderTests(unittest.TestCase):
    def test_model_is_loaded_only_when_infer_is_called_and_then_reused(self):
        processor = FakeProcessor()
        model = FakeTransformerModel()
        loader_calls = []

        def loader(architecture, repo_id, *, device, dtype):
            loader_calls.append((architecture, repo_id, device, dtype))
            return processor, model

        provider = TransformersCaptionProvider(
            "blip-test",
            "example/blip",
            architecture="blip",
            loader=loader,
        )
        self.assertFalse(provider.loaded)
        predictions = provider.infer(
            [Image.new("RGB", (2, 2)), Image.new("RGB", (2, 2))],
            prompt=CaptionPromptOptions(instruction="Describe precisely"),
            params={"maxNewTokens": 20},
            device="cpu",
            dtype="float32",
            batch_size=2,
        )
        self.assertTrue(provider.loaded)
        self.assertEqual(len(loader_calls), 1)
        self.assertEqual(processor.calls[0]["text"], ["Describe precisely", "Describe precisely"])
        self.assertEqual(processor.last_batch.device, "cpu")
        self.assertEqual([prediction.text for prediction in predictions], ["caption 0", "caption 1"])

        provider.infer(Image.new("RGB", (2, 2)), device="cpu", dtype="float32")
        self.assertEqual(len(loader_calls), 1)
        provider.unload()
        self.assertFalse(provider.loaded)


class FakeChatProcessor:
    def __init__(self):
        self.calls = []

    def apply_chat_template(self, conversations, **kwargs):
        self.calls.append((conversations, kwargs))
        count = len(conversations)
        return {
            "input_ids": np.zeros((count, 3), dtype=np.int64),
            "pixel_values": np.zeros((count, 3, 2, 2), dtype=np.float32),
        }

    def batch_decode(self, generated, skip_special_tokens):
        return [f"vlm caption {index}" for index in range(len(generated))]


class FakeJoyProcessor(FakeChatProcessor):
    def __init__(self):
        super().__init__()
        self.processor_calls = []

    def apply_chat_template(self, conversation, **kwargs):
        self.calls.append((conversation, kwargs))
        return "rendered joy prompt"

    def __call__(self, **kwargs):
        self.processor_calls.append(kwargs)
        count = len(kwargs["images"])
        return {
            "input_ids": np.zeros((count, 3), dtype=np.int64),
            "pixel_values": np.zeros((count, 3, 2, 2), dtype=np.float32),
        }


class FakeChatModel:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        count = len(kwargs["input_ids"])
        return np.zeros((count, 5), dtype=np.int64)


class FakeStructuredChatModel(FakeChatModel):
    def generate(self, **kwargs):
        self.calls.append(kwargs)
        count = len(kwargs["input_ids"])
        return SimpleNamespace(sequences=np.zeros((count, 5), dtype=np.int64))


class ChatVLMCaptionProviderTests(unittest.TestCase):
    def test_loader_uses_left_padding_and_falls_back_to_eos_for_pad_token(self):
        tokenizer = SimpleNamespace(
            padding_side="right",
            pad_token=None,
            pad_token_id=None,
            eos_token="<eos>",
            eos_token_id=2,
        )
        processor = SimpleNamespace(tokenizer=tokenizer)

        class LoadableModel:
            def __init__(self):
                self.device = None
                self.evaluated = False

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                self.evaluated = True

        model = LoadableModel()
        with (
            patch("transformers.AutoProcessor.from_pretrained", return_value=processor) as processor_loader,
            patch(
                "transformers.AutoModelForImageTextToText.from_pretrained",
                return_value=model,
            ) as model_loader,
        ):
            loaded_processor, loaded_model = _load_chat_vlm(
                "qwen2.5-vl",
                "example/vlm",
                device="cpu",
                dtype="float32",
            )

        self.assertIs(loaded_processor, processor)
        self.assertIs(loaded_model, model)
        self.assertEqual(tokenizer.padding_side, "left")
        self.assertEqual(tokenizer.pad_token, "<eos>")
        self.assertEqual(model.device, "cpu")
        self.assertTrue(model.evaluated)
        processor_loader.assert_called_once_with("example/vlm", trust_remote_code=False)
        self.assertFalse(model_loader.call_args.kwargs["trust_remote_code"])

    def test_chat_template_batches_local_images_without_remote_code(self):
        processor = FakeChatProcessor()
        model = FakeChatModel()
        loader_calls = []

        def loader(architecture, repo_id, *, device, dtype):
            loader_calls.append((architecture, repo_id, device, dtype))
            return processor, model

        provider = ChatVLMCaptionProvider(
            "vlm-test",
            "example/vlm",
            architecture="chat-vlm",
            loader=loader,
        )
        predictions = provider.infer(
            [Image.new("RGB", (20, 10)), Image.new("RGB", (20, 10))],
            params={
                "promptPreset": "training_prompt",
                "maxNewTokens": 48,
                "numBeams": 1,
                "maxPixels": 50,
            },
            device="cpu",
            dtype="float32",
            batch_size=2,
        )

        self.assertEqual(loader_calls, [("chat-vlm", "example/vlm", "cpu", "float32")])
        self.assertEqual([item.text for item in predictions], ["vlm caption 0", "vlm caption 1"])
        conversations, template_options = processor.calls[0]
        first_image = conversations[0][0]["content"][0]["image"]
        self.assertLessEqual(first_image.width * first_image.height, 55)
        self.assertIn("training caption", conversations[0][0]["content"][1]["text"])
        self.assertTrue(template_options["tokenize"])
        self.assertEqual(model.calls[0]["max_new_tokens"], 48)
        provider.unload()
        self.assertFalse(provider.loaded)

    def test_qwen_forwards_pixel_budget_without_pre_resize_and_accepts_sequences_output(self):
        processor = FakeChatProcessor()
        model = FakeStructuredChatModel()
        provider = ChatVLMCaptionProvider(
            "qwen-test",
            "example/qwen",
            architecture="qwen2.5-vl",
            loader=lambda *args, **kwargs: (processor, model),
        )
        image = Image.new("RGB", (20, 10))

        predictions = provider.infer(
            image,
            params={
                "promptPreset": "training_prompt",
                "minPixels": 1_000,
                "maxPixels": 2_000,
                "numBeams": 1,
            },
            device="cpu",
            dtype="float32",
        )

        self.assertEqual([item.text for item in predictions], ["vlm caption 0"])
        conversations, template_options = processor.calls[0]
        user_message = next(message for message in conversations[0] if message["role"] == "user")
        self.assertIs(user_message["content"][0]["image"], image)
        self.assertEqual(template_options["min_pixels"], 1_000)
        self.assertEqual(template_options["max_pixels"], 2_000)

    def test_joycaption_uses_its_documented_two_step_prompt_processing(self):
        processor = FakeJoyProcessor()
        model = FakeChatModel()
        provider = ChatVLMCaptionProvider(
            "joy-test",
            "example/joy",
            architecture="joycaption",
            loader=lambda *args, **kwargs: (processor, model),
        )

        predictions = provider.infer(
            [Image.new("RGB", (4, 4)), Image.new("RGB", (4, 4))],
            prompt=CaptionPromptOptions(instruction="Describe for training"),
            params={"promptPreset": "custom", "numBeams": 1},
            device="cpu",
            dtype="float32",
            batch_size=2,
        )

        self.assertEqual(len(predictions), 2)
        self.assertEqual(len(processor.calls), 2)
        self.assertEqual(processor.calls[0][0][0]["role"], "system")
        self.assertFalse(processor.calls[0][1]["tokenize"])
        self.assertEqual(processor.processor_calls[0]["text"], [
            "rendered joy prompt",
            "rendered joy prompt",
        ])


class FakeManagedProvider(CaptionProvider):
    def __init__(self):
        super().__init__("fake")
        self._loaded = False
        self.unload_count = 0

    @property
    def loaded(self):
        return self._loaded

    def infer(self, images, **kwargs):
        self._loaded = True
        image_list = [images] if isinstance(images, Image.Image) else list(images)
        return [CaptionPrediction(text=f"managed {index}") for index, _ in enumerate(image_list)]

    def unload(self):
        self._loaded = False
        self.unload_count += 1


class CaptionModelManagerTests(unittest.TestCase):
    def test_manager_uses_runtime_keep_loaded_policy(self):
        provider = FakeManagedProvider()
        descriptor = SimpleNamespace(output_modes=("caption",))
        catalog = SimpleNamespace(
            get_descriptor=lambda model_id: descriptor,
            create_provider=lambda model_id: provider,
        )
        manager = CaptionModelManager()

        with patch("mikazuki.captioning.catalog.get_caption_model_catalog", return_value=catalog):
            prediction = manager.predict(
                "fake",
                Image.new("RGB", (2, 2)),
                "caption",
                runtime=CaptionRuntimeOptions(keepModelLoaded=True),
            )
            self.assertEqual(prediction.text, "managed 0")
            self.assertEqual(provider.unload_count, 0)
            manager.unload()
            self.assertEqual(provider.unload_count, 1)

    def test_predict_batch_reuses_provider_and_caller_controls_unload(self):
        provider = FakeManagedProvider()
        descriptor = SimpleNamespace(output_modes=("caption",))
        create_count = 0

        def create_provider(model_id):
            nonlocal create_count
            create_count += 1
            return provider

        catalog = SimpleNamespace(
            get_descriptor=lambda model_id: descriptor,
            create_provider=create_provider,
        )
        manager = CaptionModelManager()
        images = [Image.new("RGB", (2, 2)), Image.new("RGB", (2, 2))]

        with patch("mikazuki.captioning.catalog.get_caption_model_catalog", return_value=catalog):
            first = manager.predict_batch(
                "fake",
                images,
                "caption",
                runtime=CaptionRuntimeOptions(batchSize=2, keepModelLoaded=True),
            )
            second = manager.predict_batch(
                "fake",
                images,
                "caption",
                runtime=CaptionRuntimeOptions(batchSize=2, keepModelLoaded=True),
            )
            self.assertEqual([prediction.text for prediction in first], ["managed 0", "managed 1"])
            self.assertEqual([prediction.text for prediction in second], ["managed 0", "managed 1"])
            self.assertEqual(create_count, 1)
            self.assertEqual(provider.unload_count, 0)

            manager.predict_batch(
                "fake",
                images,
                "caption",
                runtime=CaptionRuntimeOptions(batchSize=2, keepModelLoaded=False),
            )
            self.assertEqual(create_count, 1)
            self.assertEqual(provider.unload_count, 1)


if __name__ == "__main__":
    unittest.main()
