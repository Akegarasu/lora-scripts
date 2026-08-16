from __future__ import annotations

import csv
import json
import math
import re
import threading
from abc import ABC, abstractmethod
from contextlib import nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

from .models import (
    CaptionOutputMode,
    CaptionPostprocessOptions,
    CaptionPrediction,
    CaptionPromptOptions,
    CaptionRuntimeOptions,
    CaptionTag,
)


ImageInput = Union[Image.Image, Sequence[Image.Image]]
OnnxSessionFactory = Callable[..., Any]
DownloadFunction = Callable[..., str]
TransformerLoader = Callable[..., Tuple[Any, Any]]
ChatTransformerLoader = Callable[..., Tuple[Any, Any]]

_TAG_ESCAPE_PATTERN = re.compile(r"([\\()])")
_GPU_ONNX_PROVIDERS = (
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "DmlExecutionProvider",
)
_AUTO_ACCELERATED_ONNX_PROVIDERS = _GPU_ONNX_PROVIDERS + (
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
)
_QWEN_PIXEL_BUDGET_ARCHITECTURES = frozenset({"qwen2-vl", "qwen2.5-vl", "qwen3-vl"})


class CaptionProviderError(RuntimeError):
    """Base exception raised by caption providers."""


class CaptionProviderUnavailableError(CaptionProviderError):
    """Raised when a requested runtime or provider is unavailable."""


@dataclass(frozen=True)
class LabelEntry:
    name: str
    category: str


class CaptionProvider(ABC):
    """Common interface for local taggers and natural-language captioners."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    @property
    @abstractmethod
    def loaded(self) -> bool:
        """Whether heavyweight model resources are currently resident."""

    @abstractmethod
    def infer(
        self,
        images: ImageInput,
        *,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 1,
    ) -> List[CaptionPrediction]:
        """Infer normalized predictions for one image or an image sequence."""

    @abstractmethod
    def unload(self) -> None:
        """Release heavyweight model resources."""

    def __enter__(self) -> "CaptionProvider":
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        self.unload()


def select_onnx_providers(device: str, available_providers: Sequence[str]) -> List[str]:
    """Choose an ONNX Runtime provider list without requesting unavailable providers."""

    available = list(dict.fromkeys(available_providers))
    if not available:
        raise CaptionProviderUnavailableError("ONNX Runtime 没有可用的执行 Provider")

    normalized_device = (device or "auto").lower()
    if normalized_device == "cpu":
        if "CPUExecutionProvider" not in available:
            raise CaptionProviderUnavailableError("当前 ONNX Runtime 不提供 CPUExecutionProvider")
        return ["CPUExecutionProvider"]

    accelerated = [provider for provider in _AUTO_ACCELERATED_ONNX_PROVIDERS if provider in available]
    if normalized_device == "cuda":
        gpu_providers = [provider for provider in _GPU_ONNX_PROVIDERS if provider in available]
        if not gpu_providers:
            raise CaptionProviderUnavailableError("请求了 GPU 推理，但 ONNX Runtime 没有可用的 GPU Provider")
        selected = [gpu_providers[0]]
    elif normalized_device == "auto":
        selected = [accelerated[0]] if accelerated else []
    else:
        raise CaptionProviderUnavailableError(f"不支持的推理设备：{device}")

    if "CPUExecutionProvider" in available and "CPUExecutionProvider" not in selected:
        selected.append("CPUExecutionProvider")
    if not selected:
        raise CaptionProviderUnavailableError("无法为 ONNX Runtime 选择执行 Provider")
    return selected


def postprocess_tag_groups(
    groups: Mapping[str, Sequence[Tuple[str, float]]],
    *,
    threshold: float = 0.35,
    character_threshold: float = 0.6,
    add_rating_tag: bool = False,
    add_model_tag: bool = False,
    options: Optional[CaptionPostprocessOptions] = None,
) -> CaptionPrediction:
    """Convert categorized scores into an immutable, normalized tag prediction."""

    opts = options or CaptionPostprocessOptions()
    excluded = {tag.strip() for tag in opts.excludeTags if tag.strip()}
    underscore_excludes = {tag.strip() for tag in opts.replaceUnderscoreExcludes if tag.strip()}
    candidates: List[CaptionTag] = []

    def add_candidate(raw_text: str, score: Optional[float], category: str) -> None:
        raw_text = str(raw_text).strip()
        if not raw_text:
            return
        replaced = raw_text
        if opts.replaceUnderscore and raw_text not in underscore_excludes:
            replaced = raw_text.replace("_", " ")
        if raw_text in excluded or replaced in excluded:
            return
        if opts.escapeTags:
            replaced = _TAG_ESCAPE_PATTERN.sub(r"\\\1", replaced)
        candidates.append(CaptionTag(text=replaced, score=_finite_score(score), category=category))

    for tag in opts.additionalTags:
        add_candidate(tag, 1.0, "additional")

    normalized_groups = {
        str(category).strip().lower(): list(entries)
        for category, entries in groups.items()
    }
    for category, entries in normalized_groups.items():
        if category == "rating":
            if add_rating_tag and entries:
                tag, score = max(entries, key=lambda item: _score_for_sort(item[1]))
                finite_score = _finite_score(score)
                if finite_score is not None and finite_score >= threshold:
                    add_candidate(tag, finite_score, category)
            continue
        if category == "quality":
            if entries:
                tag, score = max(entries, key=lambda item: _score_for_sort(item[1]))
                finite_score = _finite_score(score)
                if finite_score is not None and finite_score >= threshold:
                    add_candidate(tag, finite_score, category)
            continue
        if category == "model" and not add_model_tag:
            continue

        category_threshold = character_threshold if category == "character" else threshold
        for tag, score in entries:
            finite_score = _finite_score(score)
            if finite_score is not None and finite_score >= category_threshold:
                add_candidate(tag, finite_score, category)

    if opts.deduplicate:
        candidates = _deduplicate_tags(candidates)

    additional = [tag for tag in candidates if tag.category == "additional"]
    predicted = [tag for tag in candidates if tag.category != "additional"]
    predicted.sort(key=lambda tag: _score_for_sort(tag.score), reverse=True)
    candidates = additional + predicted

    rendered = []
    for tag in candidates:
        if opts.includeConfidence and tag.score is not None:
            rendered.append(f"({tag.text}:{tag.score:.4f})")
        else:
            rendered.append(tag.text)
    text = opts.separator.join(rendered)
    if opts.prefix:
        text = f"{opts.prefix}{text}"
    if opts.suffix:
        text = f"{text}{opts.suffix}"

    return CaptionPrediction(
        text=text,
        tags=candidates,
        raw={"categories": _json_safe_groups(groups)},
    )


class _OnnxTaggerProvider(CaptionProvider):
    def __init__(
        self,
        model_id: str,
        repo_id: str,
        *,
        revision: Optional[str] = None,
        model_filename: str = "model.onnx",
        download_fn: Optional[DownloadFunction] = None,
        session_factory: Optional[OnnxSessionFactory] = None,
        available_providers_fn: Optional[Callable[[], Sequence[str]]] = None,
    ) -> None:
        super().__init__(model_id)
        self.repo_id = repo_id
        self.revision = revision
        self.model_filename = model_filename
        self._download_fn = download_fn
        self._session_factory = session_factory
        self._available_providers_fn = available_providers_fn
        self._session: Optional[Any] = None
        self._labels: List[Optional[LabelEntry]] = []
        self._loaded_device: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self._session is not None

    def unload(self) -> None:
        self._session = None
        self._loaded_device = None

    def _download(self, filename: str) -> Path:
        download_fn = self._download_fn
        if download_fn is None:
            from huggingface_hub import hf_hub_download

            download_fn = hf_hub_download
        kwargs: Dict[str, Any] = {"repo_id": self.repo_id, "filename": filename}
        if self.revision:
            kwargs["revision"] = self.revision
        return Path(download_fn(**kwargs))

    def _runtime_components(self) -> Tuple[OnnxSessionFactory, Sequence[str]]:
        if self._session_factory is not None and self._available_providers_fn is not None:
            return self._session_factory, self._available_providers_fn()

        import onnxruntime as ort

        return self._session_factory or ort.InferenceSession, (
            self._available_providers_fn() if self._available_providers_fn else ort.get_available_providers()
        )

    @abstractmethod
    def _load_labels(self) -> List[Optional[LabelEntry]]:
        raise NotImplementedError()

    @abstractmethod
    def _preprocess(self, image: Image.Image, input_shape: Sequence[Any]) -> np.ndarray:
        raise NotImplementedError()

    def _transform_outputs(self, outputs: np.ndarray) -> np.ndarray:
        return outputs

    def _ensure_loaded(self, device: str) -> None:
        requested_device = (device or "auto").lower()
        if self._session is not None and self._loaded_device == requested_device:
            return
        if self._session is not None:
            self.unload()

        model_path = self._download(self.model_filename)
        session_factory, available = self._runtime_components()
        providers = select_onnx_providers(requested_device, available)
        self._session = session_factory(str(model_path), providers=providers)
        self._labels = self._load_labels()
        self._loaded_device = requested_device

    def infer(
        self,
        images: ImageInput,
        *,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 1,
    ) -> List[CaptionPrediction]:
        del prompt, dtype
        image_list = _coerce_images(images)
        if not image_list:
            return []
        self._ensure_loaded(device)
        assert self._session is not None

        input_meta = self._session.get_inputs()[0]
        input_shape = list(input_meta.shape)
        fixed_batch = _fixed_batch_size(input_shape)
        requested_batch = max(1, int(batch_size))
        effective_batch = fixed_batch or requested_batch
        raw_groups: List[Dict[str, List[Tuple[str, float]]]] = []

        for offset in range(0, len(image_list), effective_batch):
            image_batch = image_list[offset : offset + effective_batch]
            tensors = [self._preprocess(image, input_shape) for image in image_batch]
            tensor_batch = np.stack(tensors).astype(np.float32, copy=False)
            actual_size = len(image_batch)
            if fixed_batch and actual_size < fixed_batch:
                padding = np.zeros((fixed_batch - actual_size, *tensor_batch.shape[1:]), dtype=tensor_batch.dtype)
                tensor_batch = np.concatenate((tensor_batch, padding), axis=0)

            outputs = np.asarray(self._session.run(None, {input_meta.name: tensor_batch})[0])
            outputs = self._transform_outputs(outputs)[:actual_size]
            for probabilities in outputs:
                raw_groups.append(self._group_probabilities(probabilities))

        options = dict(params or {})
        threshold = float(options.get("threshold", options.get("generalThreshold", 0.35)))
        character_threshold = float(options.get("characterThreshold", 0.6))
        add_rating_tag = bool(options.get("addRatingTag", False))
        add_model_tag = bool(options.get("addModelTag", False))
        return [
            postprocess_tag_groups(
                groups,
                threshold=threshold,
                character_threshold=character_threshold,
                add_rating_tag=add_rating_tag,
                add_model_tag=add_model_tag,
                options=postprocess,
            )
            for groups in raw_groups
        ]

    def _group_probabilities(self, probabilities: Sequence[float]) -> Dict[str, List[Tuple[str, float]]]:
        groups: Dict[str, List[Tuple[str, float]]] = {}
        for index, score in enumerate(probabilities):
            if index >= len(self._labels):
                break
            label = self._labels[index]
            if label is None:
                continue
            groups.setdefault(label.category, []).append((label.name, float(score)))
        return groups


class WDTaggerProvider(_OnnxTaggerProvider):
    """SmilingWolf WD tagger using the category column from selected_tags.csv."""

    def __init__(
        self,
        model_id: str,
        repo_id: str,
        *,
        revision: Optional[str] = None,
        labels_filename: str = "selected_tags.csv",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_id, repo_id, revision=revision, **kwargs)
        self.labels_filename = labels_filename

    def _load_labels(self) -> List[Optional[LabelEntry]]:
        labels_path = self._download(self.labels_filename)
        labels: List[Optional[LabelEntry]] = []
        category_map = {"9": "rating", "0": "general", "4": "character"}
        with labels_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"name", "category"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise CaptionProviderError("selected_tags.csv 缺少 name/category 列")
            for row in reader:
                name = str(row.get("name", "")).strip()
                category_value = str(row.get("category", "")).strip()
                category = category_map.get(category_value, f"category-{category_value or 'unknown'}")
                labels.append(LabelEntry(name=name, category=category) if name else None)
        return labels

    def _preprocess(self, image: Image.Image, input_shape: Sequence[Any]) -> np.ndarray:
        layout, height, width = _onnx_image_layout(input_shape, default_size=448)
        processed = _white_square_rgb(image).resize((width, height), Image.Resampling.BICUBIC)
        array = np.asarray(processed, dtype=np.float32)[:, :, ::-1]
        if layout == "nchw":
            array = array.transpose(2, 0, 1)
        return array


class CLTaggerProvider(_OnnxTaggerProvider):
    def __init__(
        self,
        model_id: str,
        repo_id: str,
        *,
        tag_mapping_filename: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_id, repo_id, **kwargs)
        self.tag_mapping_filename = tag_mapping_filename

    def _load_labels(self) -> List[Optional[LabelEntry]]:
        mapping_path = self._download(self.tag_mapping_filename)
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        entries: Dict[int, LabelEntry] = {}

        if isinstance(mapping, dict) and "idx_to_tag" in mapping:
            idx_to_tag = mapping.get("idx_to_tag") or {}
            tag_to_category = mapping.get("tag_to_category") or {}
            for raw_index, name in idx_to_tag.items():
                index = int(raw_index)
                text = str(name)
                category = str(tag_to_category.get(text, "general")).strip().lower()
                entries[index] = LabelEntry(text, category)
        elif isinstance(mapping, dict):
            for raw_index, value in mapping.items():
                if not isinstance(value, dict) or "tag" not in value:
                    raise CaptionProviderError("不支持的 CL tag_mapping.json 格式")
                index = int(raw_index)
                text = str(value["tag"])
                category = str(value.get("category", "general")).strip().lower()
                entries[index] = LabelEntry(text, category)
        else:
            raise CaptionProviderError("不支持的 CL tag_mapping.json 格式")

        if not entries:
            return []
        labels: List[Optional[LabelEntry]] = [None] * (max(entries) + 1)
        for index, entry in entries.items():
            labels[index] = entry
        return labels

    def _preprocess(self, image: Image.Image, input_shape: Sequence[Any]) -> np.ndarray:
        layout, height, width = _onnx_image_layout(input_shape, default_size=448)
        processed = _white_square_rgb(image).resize((width, height), Image.Resampling.BICUBIC)
        array = np.asarray(processed, dtype=np.float32)[:, :, ::-1] / 255.0
        array = (array - 0.5) / 0.5
        if layout == "nchw":
            array = array.transpose(2, 0, 1)
        return array

    def _transform_outputs(self, outputs: np.ndarray) -> np.ndarray:
        clipped = np.clip(outputs, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-clipped))


class TransformersCaptionProvider(CaptionProvider):
    """Lazy Transformers adapter shared by BLIP, BLIP-2 and GIT."""

    def __init__(
        self,
        model_id: str,
        repo_id: str,
        *,
        architecture: str,
        loader: Optional[TransformerLoader] = None,
    ) -> None:
        super().__init__(model_id)
        self.repo_id = repo_id
        self.architecture = architecture
        self._loader = loader
        self._processor: Optional[Any] = None
        self._model: Optional[Any] = None
        self._loaded_runtime: Optional[Tuple[str, str]] = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._loaded_runtime = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, RuntimeError):
            pass

    def _ensure_loaded(self, device: str, dtype: str) -> Tuple[str, str]:
        resolved_device, resolved_dtype = _resolve_transformer_runtime(device, dtype)
        runtime = (resolved_device, resolved_dtype)
        if self.loaded and self._loaded_runtime == runtime:
            return runtime
        if self.loaded:
            self.unload()

        loader = self._loader or _load_transformers_model
        self._processor, self._model = loader(
            self.architecture,
            self.repo_id,
            device=resolved_device,
            dtype=resolved_dtype,
        )
        self._loaded_runtime = runtime
        return runtime

    def infer(
        self,
        images: ImageInput,
        *,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 1,
    ) -> List[CaptionPrediction]:
        del postprocess
        image_list = _coerce_images(images)
        if not image_list:
            return []
        resolved_device, resolved_dtype = self._ensure_loaded(device, dtype)
        assert self._processor is not None and self._model is not None

        options = dict(params or {})
        generation_options = _generation_options(options)
        instruction = (prompt.instruction if prompt else "").strip()
        use_prompt = self.architecture in {"blip", "blip2"} and bool(instruction)
        predictions: List[CaptionPrediction] = []
        effective_batch = max(1, int(batch_size))

        inference_context = nullcontext()
        try:
            import torch

            inference_context = torch.inference_mode()
        except ImportError:
            pass

        with inference_context:
            for offset in range(0, len(image_list), effective_batch):
                image_batch = image_list[offset : offset + effective_batch]
                processor_kwargs: Dict[str, Any] = {"images": image_batch, "return_tensors": "pt", "padding": True}
                if use_prompt:
                    processor_kwargs["text"] = [instruction] * len(image_batch)
                inputs = self._processor(**processor_kwargs)
                inputs = _move_transformer_inputs(inputs, resolved_device, resolved_dtype)
                model_inputs = dict(inputs) if isinstance(inputs, Mapping) else vars(inputs)
                generated = _extract_generation_sequences(
                    self._model.generate(**model_inputs, **generation_options)
                )
                captions = self._processor.batch_decode(generated, skip_special_tokens=True)
                if len(captions) != len(image_batch):
                    raise CaptionProviderError(
                        f"模型返回 {len(captions)} 条 Caption，但输入批次有 {len(image_batch)} 张图片"
                    )
                predictions.extend(
                    CaptionPrediction(
                        text=str(caption).strip(),
                        raw={"modelId": self.model_id, "repoId": self.repo_id},
                    )
                    for caption in captions
                )
        return predictions


class ChatVLMCaptionProvider(CaptionProvider):
    """Safe, registry-backed adapter for chat-template vision-language models."""

    def __init__(
        self,
        model_id: str,
        repo_id: str,
        *,
        architecture: str = "chat-vlm",
        loader: Optional[ChatTransformerLoader] = None,
    ) -> None:
        super().__init__(model_id)
        self.repo_id = repo_id
        self.architecture = architecture
        self._loader = loader
        self._processor: Optional[Any] = None
        self._model: Optional[Any] = None
        self._loaded_runtime: Optional[Tuple[str, str]] = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._loaded_runtime = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, RuntimeError):
            pass

    def _ensure_loaded(self, device: str, dtype: str) -> Tuple[str, str]:
        resolved_device, resolved_dtype = _resolve_transformer_runtime(device, dtype)
        runtime = (resolved_device, resolved_dtype)
        if self.loaded and self._loaded_runtime == runtime:
            return runtime
        if self.loaded:
            self.unload()

        loader = self._loader or _load_chat_vlm
        self._processor, self._model = loader(
            self.architecture,
            self.repo_id,
            device=resolved_device,
            dtype=resolved_dtype,
        )
        self._loaded_runtime = runtime
        return runtime

    def infer(
        self,
        images: ImageInput,
        *,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        device: str = "auto",
        dtype: str = "auto",
        batch_size: int = 1,
    ) -> List[CaptionPrediction]:
        del postprocess
        image_list = _coerce_images(images)
        if not image_list:
            return []
        resolved_device, resolved_dtype = self._ensure_loaded(device, dtype)
        assert self._processor is not None and self._model is not None

        options = dict(params or {})
        generation_options = _generation_options(options)
        instruction = _chat_instruction(prompt, options)
        effective_batch = max(1, int(batch_size))
        predictions: List[CaptionPrediction] = []

        inference_context = nullcontext()
        try:
            import torch

            inference_context = torch.inference_mode()
        except ImportError:
            pass

        with inference_context:
            for offset in range(0, len(image_list), effective_batch):
                image_batch = image_list[offset : offset + effective_batch]
                if self.architecture not in _QWEN_PIXEL_BUDGET_ARCHITECTURES:
                    image_batch = [_resize_to_pixel_budget(image, options) for image in image_batch]
                inputs = _prepare_chat_vlm_inputs(
                    self._processor,
                    self.architecture,
                    image_batch,
                    instruction,
                    options,
                )
                inputs = _move_transformer_inputs(inputs, resolved_device, resolved_dtype)
                model_inputs = dict(inputs) if isinstance(inputs, Mapping) else vars(inputs)
                generated = _extract_generation_sequences(
                    self._model.generate(**model_inputs, **generation_options)
                )
                prompt_length = _input_sequence_length(model_inputs.get("input_ids"))
                generated_tokens = (
                    generated[:, prompt_length:]
                    if prompt_length is not None and getattr(generated, "ndim", 0) >= 2
                    else generated
                )
                captions = self._processor.batch_decode(
                    generated_tokens,
                    skip_special_tokens=True,
                )
                if len(captions) != len(image_batch):
                    raise CaptionProviderError(
                        f"模型返回 {len(captions)} 条 Caption，但输入批次有 {len(image_batch)} 张图片"
                    )
                predictions.extend(
                    CaptionPrediction(
                        text=str(caption).strip(),
                        raw={
                            "modelId": self.model_id,
                            "repoId": self.repo_id,
                            "engine": "chat_vlm",
                        },
                    )
                    for caption in captions
                )
        return predictions


class CaptionModelManager:
    """Owns lazy provider instances and presents the single-image runner API."""

    def __init__(self) -> None:
        self._providers: Dict[str, CaptionProvider] = {}
        self._lock = threading.RLock()

    def predict(
        self,
        model_id: str,
        image: Image.Image,
        output_mode: CaptionOutputMode,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        runtime: Optional[CaptionRuntimeOptions] = None,
    ) -> CaptionPrediction:
        predictions = self.predict_batch(
            model_id,
            [image],
            output_mode,
            params,
            prompt,
            postprocess,
            runtime,
        )
        if len(predictions) != 1:
            raise CaptionProviderError(f"单图推理预期返回 1 条结果，实际返回 {len(predictions)} 条")
        return predictions[0]

    def predict_batch(
        self,
        model_id: str,
        images: Sequence[Image.Image],
        output_mode: CaptionOutputMode,
        params: Optional[Mapping[str, Any]] = None,
        prompt: Optional[CaptionPromptOptions] = None,
        postprocess: Optional[CaptionPostprocessOptions] = None,
        runtime: Optional[CaptionRuntimeOptions] = None,
    ) -> List[CaptionPrediction]:
        from .catalog import get_caption_model_catalog

        catalog = get_caption_model_catalog()
        descriptor = catalog.get_descriptor(model_id)
        if descriptor is None:
            raise KeyError(f"Caption 模型不存在：{model_id}")
        if output_mode not in descriptor.output_modes:
            raise CaptionProviderError(f"模型 {model_id} 不支持输出模式 {output_mode}")

        runtime_options = runtime or CaptionRuntimeOptions()
        with self._lock:
            provider = self._providers.get(model_id)
            if provider is None:
                provider = catalog.create_provider(model_id)
                self._providers[model_id] = provider
            try:
                predictions = provider.infer(
                    images,
                    params=params,
                    prompt=prompt,
                    postprocess=postprocess,
                    device=runtime_options.device,
                    dtype=runtime_options.dtype,
                    batch_size=runtime_options.batchSize,
                )
                if len(predictions) != len(images):
                    raise CaptionProviderError(
                        f"批量推理预期返回 {len(images)} 条结果，实际返回 {len(predictions)} 条"
                    )
                return predictions
            finally:
                if not runtime_options.keepModelLoaded:
                    provider.unload()
                    self._providers.pop(model_id, None)

    def unload(self) -> None:
        with self._lock:
            providers = list(self._providers.values())
            self._providers.clear()
        for provider in providers:
            provider.unload()


@lru_cache(maxsize=1)
def get_caption_model_manager() -> CaptionModelManager:
    return CaptionModelManager()


def _load_transformers_model(
    architecture: str,
    repo_id: str,
    *,
    device: str,
    dtype: str,
) -> Tuple[Any, Any]:
    import torch

    if architecture == "blip":
        from transformers import BlipForConditionalGeneration, BlipProcessor

        processor_class = BlipProcessor
        model_class = BlipForConditionalGeneration
    elif architecture == "blip2":
        from transformers import Blip2ForConditionalGeneration, Blip2Processor

        processor_class = Blip2Processor
        model_class = Blip2ForConditionalGeneration
    elif architecture == "git":
        from transformers import AutoModelForCausalLM, AutoProcessor

        processor_class = AutoProcessor
        model_class = AutoModelForCausalLM
    else:
        raise CaptionProviderError(f"不支持的 Transformers Caption 架构：{architecture}")

    torch_dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[dtype]
    processor = processor_class.from_pretrained(repo_id)
    model = model_class.from_pretrained(repo_id, torch_dtype=torch_dtype)
    model = model.to(device)
    if hasattr(model, "eval"):
        model.eval()
    return processor, model


def _load_chat_vlm(
    architecture: str,
    repo_id: str,
    *,
    device: str,
    dtype: str,
) -> Tuple[Any, Any]:
    del architecture
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    torch_dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[dtype]
    # Model ids are selected exclusively from the server-side registry. Remote
    # repository code stays disabled so a frontend request cannot execute code.
    processor = AutoProcessor.from_pretrained(repo_id, trust_remote_code=False)
    _configure_chat_vlm_tokenizer(processor)
    model = AutoModelForImageTextToText.from_pretrained(
        repo_id,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    model = model.to(device)
    if hasattr(model, "eval"):
        model.eval()
    return processor, model


def _configure_chat_vlm_tokenizer(processor: Any) -> None:
    tokenizer = getattr(processor, "tokenizer", None)
    if tokenizer is None:
        return

    tokenizer.padding_side = "left"
    if getattr(tokenizer, "pad_token_id", None) is not None:
        return

    eos_token = getattr(tokenizer, "eos_token", None)
    if eos_token is not None:
        tokenizer.pad_token = eos_token
        return

    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if eos_token_id is not None:
        tokenizer.pad_token_id = eos_token_id
        return
    raise CaptionProviderUnavailableError("VLM tokenizer 未配置 pad_token，且没有 eos_token 可安全回退")


def _resolve_transformer_runtime(device: str, dtype: str) -> Tuple[str, str]:
    import torch

    normalized_device = (device or "auto").lower()
    if normalized_device == "auto":
        resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    elif normalized_device == "cuda":
        if not torch.cuda.is_available():
            raise CaptionProviderUnavailableError("请求了 CUDA 推理，但 PyTorch CUDA 当前不可用")
        resolved_device = "cuda"
    elif normalized_device == "cpu":
        resolved_device = "cpu"
    else:
        raise CaptionProviderUnavailableError(f"不支持的推理设备：{device}")

    normalized_dtype = (dtype or "auto").lower()
    if normalized_dtype == "auto":
        if resolved_device == "cuda" and getattr(torch.cuda, "is_bf16_supported", lambda: False)():
            resolved_dtype = "bfloat16"
        else:
            resolved_dtype = "float16" if resolved_device == "cuda" else "float32"
    elif normalized_dtype in {"float16", "bfloat16", "float32"}:
        resolved_dtype = normalized_dtype
    else:
        raise CaptionProviderUnavailableError(f"不支持的推理精度：{dtype}")
    if resolved_device == "cpu" and resolved_dtype == "float16":
        raise CaptionProviderUnavailableError("CPU Caption 推理不支持 float16，请使用 float32 或 bfloat16")
    return resolved_device, resolved_dtype


def _prepare_chat_vlm_inputs(
    processor: Any,
    architecture: str,
    images: Sequence[Image.Image],
    instruction: str,
    options: Mapping[str, Any],
) -> Any:
    if architecture == "joycaption":
        # JoyCaption's model card explicitly recommends rendering text first and
        # passing images in a separate processor call to avoid duplicate BOS tokens.
        prompts = [
            processor.apply_chat_template(
                [
                    {"role": "system", "content": "You are a helpful image captioner."},
                    {"role": "user", "content": instruction},
                ],
                tokenize=False,
                add_generation_prompt=True,
            )
            for _ in images
        ]
        return processor(
            text=prompts,
            images=list(images),
            padding=True,
            return_tensors="pt",
        )

    conversations = []
    for image in images:
        messages = []
        if architecture in _QWEN_PIXEL_BUDGET_ARCHITECTURES:
            messages.append(
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "You are an accurate image-captioning expert.",
                        }
                    ],
                }
            )
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": instruction},
                ],
            }
        )
        conversations.append(messages)
    template_options: Dict[str, Any] = {}
    if architecture in _QWEN_PIXEL_BUDGET_ARCHITECTURES:
        min_pixels, max_pixels = _pixel_budget(options)
        if min_pixels:
            template_options["min_pixels"] = min_pixels
        if max_pixels:
            template_options["max_pixels"] = max_pixels
    return processor.apply_chat_template(
        conversations,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        padding=True,
        **template_options,
    )


def _move_transformer_inputs(inputs: Any, device: str, dtype: str) -> Any:
    torch_dtype = None
    try:
        import torch

        torch_dtype = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }.get(dtype)
    except ImportError:
        pass
    if hasattr(inputs, "to"):
        if torch_dtype is not None:
            try:
                return inputs.to(device=device, dtype=torch_dtype)
            except TypeError:
                pass
        return inputs.to(device)
    if isinstance(inputs, Mapping):
        moved = {}
        for key, value in inputs.items():
            if not hasattr(value, "to"):
                moved[key] = value
                continue
            if torch_dtype is not None and hasattr(value, "is_floating_point"):
                try:
                    if value.is_floating_point():
                        moved[key] = value.to(device=device, dtype=torch_dtype)
                        continue
                except (TypeError, RuntimeError):
                    pass
            moved[key] = value.to(device)
        return moved
    return inputs


def _generation_options(options: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "max_new_tokens": int(options.get("maxNewTokens", 64)),
        "num_beams": int(options.get("numBeams", 3)),
        "do_sample": bool(options.get("doSample", False)),
    }
    if result["do_sample"]:
        result["temperature"] = float(options.get("temperature", 1.0))
        top_p = options.get("topP")
        if top_p is not None:
            result["top_p"] = float(top_p)
    repetition_penalty = options.get("repetitionPenalty")
    if repetition_penalty is not None:
        result["repetition_penalty"] = float(repetition_penalty)
    return result


_CHAT_PROMPT_PRESETS = {
    "straightforward": "Write a concise, literal caption describing the image. Do not speculate.",
    "descriptive": (
        "Describe the image in detail, including the subject, appearance, action, composition, "
        "lighting, background, and visual style. Avoid unsupported claims."
    ),
    "training_prompt": (
        "Write a high-quality image-generation training caption. Describe visible subjects, "
        "attributes, pose, composition, lighting, background, and style using concrete wording."
    ),
    "booru": (
        "Return only a comma-separated list of concise booru-style tags for visible content. "
        "Do not add explanations or confidence scores."
    ),
}


def _chat_instruction(
    prompt: Optional[CaptionPromptOptions],
    options: Mapping[str, Any],
) -> str:
    preset = str(options.get("promptPreset", "custom"))
    if preset != "custom":
        instruction = _CHAT_PROMPT_PRESETS.get(preset)
        if instruction is None:
            raise CaptionProviderError(f"未知的提示预设：{preset}")
    else:
        instruction = (prompt.instruction if prompt else "").strip()
        instruction = instruction or _CHAT_PROMPT_PRESETS["training_prompt"]
    if prompt and prompt.language.lower() == "zh":
        instruction = f"{instruction}\nWrite the final caption in Simplified Chinese."
    return instruction


def _resize_to_pixel_budget(image: Image.Image, options: Mapping[str, Any]) -> Image.Image:
    min_pixels, max_pixels = _pixel_budget(options)
    pixels = image.width * image.height
    if pixels <= 0:
        raise CaptionProviderError("图片尺寸无效")
    target_pixels = pixels
    if max_pixels and pixels > max_pixels:
        target_pixels = max_pixels
    elif min_pixels and pixels < min_pixels:
        target_pixels = min_pixels
    if target_pixels == pixels:
        return image
    scale = math.sqrt(target_pixels / pixels)
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _pixel_budget(options: Mapping[str, Any]) -> Tuple[int, int]:
    min_pixels = int(options.get("minPixels", 0) or 0)
    max_pixels = int(options.get("maxPixels", 0) or 0)
    if min_pixels < 0 or max_pixels < 0 or (min_pixels and max_pixels and min_pixels > max_pixels):
        raise CaptionProviderError("视觉像素下限不能高于上限")
    return min_pixels, max_pixels


def _extract_generation_sequences(generated: Any) -> Any:
    sequences = getattr(generated, "sequences", None)
    return sequences if sequences is not None else generated


def _input_sequence_length(input_ids: Any) -> Optional[int]:
    shape = getattr(input_ids, "shape", None)
    if shape is None or len(shape) < 2:
        return None
    return int(shape[-1])


def _coerce_images(images: ImageInput) -> List[Image.Image]:
    if isinstance(images, Image.Image):
        return [images]
    result = list(images)
    if any(not isinstance(image, Image.Image) for image in result):
        raise TypeError("Caption Provider 仅接受 PIL.Image.Image")
    return result


def _white_square_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        rgb = Image.new("RGB", rgba.size, "white")
        rgb.paste(rgba, mask=rgba.getchannel("A"))
    else:
        rgb = image.convert("RGB")
    size = max(rgb.size)
    square = Image.new("RGB", (size, size), "white")
    square.paste(rgb, ((size - rgb.width) // 2, (size - rgb.height) // 2))
    return square


def _onnx_image_layout(input_shape: Sequence[Any], *, default_size: int) -> Tuple[str, int, int]:
    if len(input_shape) != 4:
        return "nhwc", default_size, default_size
    if _dimension(input_shape[1]) in {1, 3}:
        return "nchw", _dimension(input_shape[2]) or default_size, _dimension(input_shape[3]) or default_size
    if _dimension(input_shape[-1]) in {1, 3, 4}:
        return "nhwc", _dimension(input_shape[1]) or default_size, _dimension(input_shape[2]) or default_size
    if _dimension(input_shape[1]) == 4:
        return "nchw", _dimension(input_shape[2]) or default_size, _dimension(input_shape[3]) or default_size
    return "nhwc", default_size, default_size


def _fixed_batch_size(input_shape: Sequence[Any]) -> Optional[int]:
    if not input_shape:
        return None
    batch = _dimension(input_shape[0])
    return batch if batch and batch > 0 else None


def _dimension(value: Any) -> Optional[int]:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _finite_score(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    score = float(value)
    return score if math.isfinite(score) else None


def _score_for_sort(value: Optional[float]) -> float:
    score = _finite_score(value)
    return score if score is not None else float("-inf")


def _deduplicate_tags(tags: Iterable[CaptionTag]) -> List[CaptionTag]:
    result: List[CaptionTag] = []
    indexes: Dict[str, int] = {}
    for tag in tags:
        existing_index = indexes.get(tag.text)
        if existing_index is None:
            indexes[tag.text] = len(result)
            result.append(tag)
            continue
        existing = result[existing_index]
        if _score_for_sort(tag.score) > _score_for_sort(existing.score):
            result[existing_index] = tag
    return result


def _json_safe_groups(groups: Mapping[str, Sequence[Tuple[str, float]]]) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    for category, entries in groups.items():
        result[str(category)] = [
            {"text": str(text), "score": _finite_score(score)}
            for text, score in entries
        ]
    return result
