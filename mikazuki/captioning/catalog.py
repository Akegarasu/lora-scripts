from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from packaging.version import InvalidVersion, Version

from .adapters import (
    CLTaggerProvider,
    CaptionProvider,
    ChatVLMCaptionProvider,
    TransformersCaptionProvider,
    WDTaggerProvider,
)
from .models import (
    CaptionModelCapabilities,
    CaptionModelParam,
    CaptionModelParamGroup,
    CaptionModelSummary,
    CaptionModelsResponse,
    CaptionOutputMode,
)


ProviderKind = Literal["local-onnx", "local-transformers", "remote"]
ProviderFactory = Callable[..., CaptionProvider]
DependencyChecker = Callable[[str], bool]
CacheChecker = Callable[["ModelDescriptor"], bool]
DeviceResolver = Callable[["ModelDescriptor"], List[str]]


@dataclass(frozen=True)
class ModelDependency:
    module: str
    package: str


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    title: str
    description: str
    family: str
    engine: str
    provider: ProviderKind
    output_modes: Tuple[CaptionOutputMode, ...]
    default_output_mode: CaptionOutputMode
    capabilities: CaptionModelCapabilities
    factory: ProviderFactory = field(repr=False, compare=False)
    repo_id: Optional[str] = None
    revision: Optional[str] = None
    dependencies: Tuple[ModelDependency, ...] = ()
    cache_files: Tuple[str, ...] = ()
    param_groups: Tuple[CaptionModelParamGroup, ...] = ()
    recommended_vram_gb: Optional[float] = None
    license: Optional[str] = None
    homepage: Optional[str] = None
    min_transformers: Optional[str] = None
    gated: bool = False
    requires_hf_token: bool = False
    trust_remote_code: bool = False
    warnings: Tuple[str, ...] = ()
    experimental: bool = False


class CaptionModelCatalog:
    def __init__(
        self,
        descriptors: Optional[Sequence[ModelDescriptor]] = None,
        *,
        default_model_id: str = "wd-vit-v3",
        dependency_checker: Optional[DependencyChecker] = None,
        cache_checker: Optional[CacheChecker] = None,
        device_resolver: Optional[DeviceResolver] = None,
    ) -> None:
        model_descriptors = list(descriptors or builtin_model_descriptors())
        self._descriptors: Dict[str, ModelDescriptor] = {descriptor.id: descriptor for descriptor in model_descriptors}
        if len(self._descriptors) != len(model_descriptors):
            raise ValueError("Caption 模型目录包含重复 id")
        if default_model_id not in self._descriptors:
            raise ValueError(f"默认 Caption 模型不存在：{default_model_id}")
        self.default_model_id = default_model_id
        self._dependency_checker = dependency_checker or _module_available
        self._cache_checker = cache_checker or _model_cached
        self._device_resolver = device_resolver or _available_devices

    def list_models(self) -> List[CaptionModelSummary]:
        return [self._summary(descriptor) for descriptor in self._descriptors.values()]

    def get_model(self, model_id: str) -> Optional[CaptionModelSummary]:
        descriptor = self._descriptors.get(model_id)
        return self._summary(descriptor) if descriptor is not None else None

    def get(self, model_id: str) -> Optional[CaptionModelSummary]:
        return self.get_model(model_id)

    def get_descriptor(self, model_id: str) -> Optional[ModelDescriptor]:
        return self._descriptors.get(model_id)

    def create_provider(self, model_id: str, **overrides) -> CaptionProvider:
        descriptor = self._descriptors.get(model_id)
        if descriptor is None:
            raise KeyError(f"Caption 模型不存在：{model_id}")
        missing = self._missing_dependencies(descriptor)
        if missing:
            packages = "、".join(missing)
            raise RuntimeError(f"Caption 模型 {model_id} 缺少依赖：{packages}")
        version_issue = _minimum_version_issue(descriptor)
        if version_issue:
            raise RuntimeError(version_issue)
        return descriptor.factory(**overrides)

    def validate_params(self, model_id: str, values: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate untrusted dynamic parameters against the public model schema."""

        descriptor = self._descriptors.get(model_id)
        if descriptor is None:
            raise ValueError(f"Caption 模型不存在：{model_id}")
        definitions = {
            parameter.name: parameter
            for group in descriptor.param_groups
            for parameter in group.params
        }
        unknown = sorted(set(values).difference(definitions))
        if unknown:
            raise ValueError(f"模型不支持以下参数：{'、'.join(unknown)}")

        normalized: Dict[str, Any] = {}
        for name, parameter in definitions.items():
            if name not in values:
                if parameter.required and parameter.default is None:
                    raise ValueError(f"缺少必填参数：{parameter.label}")
                if parameter.default is not None:
                    normalized[name] = parameter.default
                continue
            normalized[name] = _validate_param_value(parameter, values[name])
        return normalized

    def response(self) -> CaptionModelsResponse:
        models = self.list_models()
        default_model_id = self.default_model_id
        preferred = next((model for model in models if model.id == default_model_id), None)
        if preferred is None or preferred.status != "ready":
            cached = next((model for model in models if model.status == "ready"), None)
            if cached is not None:
                default_model_id = cached.id
        return CaptionModelsResponse(models=models, defaultModelId=default_model_id)

    def _summary(self, descriptor: ModelDescriptor) -> CaptionModelSummary:
        missing = self._missing_dependencies(descriptor)
        version_issue = _minimum_version_issue(descriptor)
        if missing:
            status = "unavailable"
            status_reason = f"缺少运行依赖：{'、'.join(missing)}"
            devices: List[str] = []
        elif version_issue:
            status = "unavailable"
            status_reason = version_issue
            devices = []
        else:
            cached = self._cache_checker(descriptor)
            status = "ready" if cached else "downloadable"
            status_reason = None if cached else "模型将在首次使用时下载到本地缓存"
            devices = self._device_resolver(descriptor)

        capabilities = descriptor.capabilities.copy(update={"devices": devices})
        return CaptionModelSummary(
            id=descriptor.id,
            title=descriptor.title,
            description=descriptor.description,
            family=descriptor.family,
            engine=descriptor.engine,
            provider=descriptor.provider,
            repoId=descriptor.repo_id,
            outputModes=list(descriptor.output_modes),
            defaultOutputMode=descriptor.default_output_mode,
            status=status,
            statusReason=status_reason,
            missingDependencies=missing,
            capabilities=capabilities,
            paramGroups=list(descriptor.param_groups),
            recommendedVramGb=descriptor.recommended_vram_gb,
            license=descriptor.license,
            homepage=descriptor.homepage,
            minTransformers=descriptor.min_transformers,
            gated=descriptor.gated,
            requiresHfToken=descriptor.requires_hf_token,
            trustRemoteCode=descriptor.trust_remote_code,
            warnings=list(descriptor.warnings),
            experimental=descriptor.experimental,
        )

    def _missing_dependencies(self, descriptor: ModelDescriptor) -> List[str]:
        result: List[str] = []
        for dependency in descriptor.dependencies:
            if not self._dependency_checker(dependency.module) and dependency.package not in result:
                result.append(dependency.package)
        return result


def builtin_model_descriptors() -> Tuple[ModelDescriptor, ...]:
    descriptors: List[ModelDescriptor] = []
    wd_models = (
        ("wd-convnext-v3", "WD ConvNeXt v3", "SmilingWolf/wd-convnext-tagger-v3", None, 1.0),
        ("wd-swinv2-v3", "WD SwinV2 v3", "SmilingWolf/wd-swinv2-tagger-v3", None, 1.0),
        ("wd-vit-v3", "WD ViT v3", "SmilingWolf/wd-vit-tagger-v3", None, 1.0),
        (
            "wd14-convnextv2-v2",
            "WD ConvNeXtV2 v2",
            "SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
            "v2.0",
            1.0,
        ),
        ("wd14-swinv2-v2", "WD SwinV2 v2", "SmilingWolf/wd-v1-4-swinv2-tagger-v2", "v2.0", 1.0),
        ("wd14-vit-v2", "WD ViT v2", "SmilingWolf/wd-v1-4-vit-tagger-v2", "v2.0", 1.0),
        ("wd14-moat-v2", "WD MOAT v2", "SmilingWolf/wd-v1-4-moat-tagger-v2", "v2.0", 1.0),
        (
            "wd-eva02-large-tagger-v3",
            "WD EVA02 Large v3",
            "SmilingWolf/wd-eva02-large-tagger-v3",
            None,
            2.0,
        ),
        (
            "wd-vit-large-tagger-v3",
            "WD ViT Large v3",
            "SmilingWolf/wd-vit-large-tagger-v3",
            None,
            2.0,
        ),
    )
    for model_id, title, repo_id, revision, vram in wd_models:
        descriptors.append(
            ModelDescriptor(
                id=model_id,
                title=title,
                description="适合动漫与插画数据集的 Danbooru 标签识别，返回标签分类与置信度。",
                family="wd-tagger",
                engine="classifier_tagger",
                provider="local-onnx",
                repo_id=repo_id,
                revision=revision,
                output_modes=("tags",),
                default_output_mode="tags",
                capabilities=_tagger_capabilities(),
                factory=_wd_factory(model_id, repo_id, revision),
                dependencies=_ONNX_DEPENDENCIES,
                cache_files=("model.onnx", "selected_tags.csv"),
                param_groups=_tagger_param_groups(include_model=False),
                recommended_vram_gb=vram,
                homepage=f"https://huggingface.co/{repo_id}",
            )
        )

    cl_repo = "cella110n/cl_tagger"
    descriptors.append(
        ModelDescriptor(
            id="cl_tagger_1_01",
            title="CL Tagger 1.01",
            description="带艺术家、角色、版权、质量、模型等细分类的通用插画标签识别器。",
            family="cl-tagger",
            engine="classifier_tagger",
            provider="local-onnx",
            repo_id=cl_repo,
            output_modes=("tags",),
            default_output_mode="tags",
            capabilities=_tagger_capabilities(),
            factory=lambda **kwargs: CLTaggerProvider(
                "cl_tagger_1_01",
                cl_repo,
                model_filename="cl_tagger_1_01/model.onnx",
                tag_mapping_filename="cl_tagger_1_01/tag_mapping.json",
                **kwargs,
            ),
            dependencies=_ONNX_DEPENDENCIES,
            cache_files=("cl_tagger_1_01/model.onnx", "cl_tagger_1_01/tag_mapping.json"),
            param_groups=_tagger_param_groups(include_model=True),
            recommended_vram_gb=2.0,
            homepage=f"https://huggingface.co/{cl_repo}",
        )
    )

    descriptors.extend(
        (
            _transformer_descriptor(
                "blip-large",
                "BLIP Large",
                "Salesforce/blip-image-captioning-large",
                "blip",
                "适合生成简洁英文自然语言 Caption 的经典图像描述模型。",
                prompt=True,
                vram=4.0,
            ),
            _transformer_descriptor(
                "git-large-coco",
                "GIT Large COCO",
                "microsoft/git-large-coco",
                "git",
                "基于 COCO 数据训练的自然语言图像描述模型。",
                prompt=False,
                vram=4.0,
            ),
        )
    )

    blip2_models = (
        ("blip2-opt-2.7b", "BLIP-2 OPT 2.7B", 8.0),
        ("blip2-opt-2.7b-coco", "BLIP-2 OPT 2.7B COCO", 8.0),
        ("blip2-opt-6.7b", "BLIP-2 OPT 6.7B", 16.0),
        ("blip2-opt-6.7b-coco", "BLIP-2 OPT 6.7B COCO", 16.0),
        ("blip2-flan-t5-xl", "BLIP-2 FLAN-T5 XL", 10.0),
        ("blip2-flan-t5-xl-coco", "BLIP-2 FLAN-T5 XL COCO", 10.0),
        ("blip2-flan-t5-xxl", "BLIP-2 FLAN-T5 XXL", 24.0),
    )
    for repo_name, title, vram in blip2_models:
        descriptors.append(
            _transformer_descriptor(
                repo_name,
                title,
                f"Salesforce/{repo_name}",
                "blip2",
                "支持指令提示的 BLIP-2 自然语言 Caption 模型；体积较大，首次使用需下载权重。",
                prompt=True,
                vram=vram,
                experimental=True,
            )
        )

    descriptors.extend(
        (
            _chat_vlm_descriptor(
                "smolvlm2-2.2b",
                "SmolVLM2 2.2B",
                "HuggingFaceTB/SmolVLM2-2.2B-Instruct",
                "smolvlm2",
                "轻量通用视觉语言模型，适合消费级显卡生成自然语言 Caption。",
                languages=("en",),
                vram=6.0,
                min_transformers="4.49.0",
                extra_dependencies=(ModelDependency("num2words", "num2words"),),
                license_name="Apache-2.0",
            ),
            _chat_vlm_descriptor(
                "qwen2.5-vl-7b",
                "Qwen2.5-VL 7B",
                "Qwen/Qwen2.5-VL-7B-Instruct",
                "qwen2.5-vl",
                "高质量通用视觉理解模型，擅长细节描述、中文指令、OCR 与结构化内容。",
                languages=("zh", "en"),
                vram=22.0,
                min_transformers="4.49.0",
                license_name="Apache-2.0",
                pixel_budget=True,
                warnings=("模型体积较大；批次、图像分辨率和输出长度都会显著影响显存。",),
            ),
            _chat_vlm_descriptor(
                "joycaption-beta-one",
                "JoyCaption Beta One",
                "fancyfeast/llama-joycaption-beta-one-hf-llava",
                "joycaption",
                "面向扩散模型训练的视觉语言模型，支持描述、训练 Prompt 与 Booru 标签风格。",
                languages=("en",),
                vram=17.0,
                min_transformers="4.51.0",
                license_name="Llama 3.1 Community License",
                warnings=("使用前请确认 Llama 3.1 Community License 满足你的用途。",),
            ),
            _chat_vlm_descriptor(
                "toriigate-v0.4-2b",
                "ToriiGate v0.4 2B",
                "Minthy/ToriiGate-v0.4-2B",
                "qwen2-vl",
                "面向动漫、角色、服饰和数字绘画数据的生成式 Caption 模型。",
                languages=("en",),
                vram=7.0,
                min_transformers="4.45.0",
                license_name="Apache-2.0",
                pixel_budget=True,
                experimental=True,
                warnings=("社区模型，建议先抽样复核角色名和作品名，再批量写入。",),
            ),
            _chat_vlm_descriptor(
                "llava-onevision-0.5b",
                "LLaVA-OneVision 0.5B",
                "llava-hf/llava-onevision-qwen2-0.5b-ov-hf",
                "llava-onevision",
                "体积较小的通用视觉语言模型，适合快速预览与低显存环境。",
                languages=("en", "zh"),
                vram=4.0,
                min_transformers="4.45.0",
                license_name="Apache-2.0",
                experimental=True,
            ),
            _chat_vlm_descriptor(
                "qwen3-vl-4b",
                "Qwen3-VL 4B",
                "Qwen/Qwen3-VL-4B-Instruct",
                "qwen3-vl",
                "新一代通用视觉语言模型；当前训练环境版本不足时仅展示兼容说明。",
                languages=("zh", "en"),
                vram=12.0,
                min_transformers="4.57.0",
                license_name="Apache-2.0",
                pixel_budget=True,
                experimental=True,
                warnings=("当前项目不会为此模型单独升级 Transformers；可等待统一依赖升级。",),
            ),
        )
    )
    return tuple(descriptors)


def _wd_factory(model_id: str, repo_id: str, revision: Optional[str]) -> ProviderFactory:
    return lambda **kwargs: WDTaggerProvider(model_id, repo_id, revision=revision, **kwargs)


def _transformer_descriptor(
    model_id: str,
    title: str,
    repo_id: str,
    architecture: str,
    description: str,
    *,
    prompt: bool,
    vram: float,
    experimental: bool = False,
) -> ModelDescriptor:
    dependencies = _TRANSFORMERS_DEPENDENCIES
    if architecture == "blip2" and "flan-t5" in repo_id:
        dependencies += (ModelDependency("sentencepiece", "sentencepiece"),)
    return ModelDescriptor(
        id=model_id,
        title=title,
        description=description,
        family=architecture,
        engine="legacy_image_to_text",
        provider="local-transformers",
        repo_id=repo_id,
        output_modes=("caption",),
        default_output_mode="caption",
        capabilities=CaptionModelCapabilities(
            prompt=prompt,
            scores=False,
            categories=False,
            batch=True,
            languages=["en"],
            devices=["cpu", "cuda"],
        ),
        factory=lambda **kwargs: TransformersCaptionProvider(
            model_id,
            repo_id,
            architecture=architecture,
            **kwargs,
        ),
        dependencies=dependencies,
        param_groups=_generation_param_groups(),
        recommended_vram_gb=vram,
        homepage=f"https://huggingface.co/{repo_id}",
        experimental=experimental,
    )


def _chat_vlm_descriptor(
    model_id: str,
    title: str,
    repo_id: str,
    architecture: str,
    description: str,
    *,
    languages: Tuple[str, ...],
    vram: float,
    min_transformers: str,
    license_name: str,
    pixel_budget: bool = False,
    extra_dependencies: Tuple[ModelDependency, ...] = (),
    warnings: Tuple[str, ...] = (),
    experimental: bool = False,
) -> ModelDescriptor:
    return ModelDescriptor(
        id=model_id,
        title=title,
        description=description,
        family=architecture,
        engine="chat_vlm",
        provider="local-transformers",
        repo_id=repo_id,
        output_modes=("caption",),
        default_output_mode="caption",
        capabilities=CaptionModelCapabilities(
            prompt=True,
            scores=False,
            categories=False,
            batch=True,
            languages=list(languages),
            devices=["cpu", "cuda"],
        ),
        factory=lambda **kwargs: ChatVLMCaptionProvider(
            model_id,
            repo_id,
            architecture=architecture,
            **kwargs,
        ),
        dependencies=_TRANSFORMERS_DEPENDENCIES + extra_dependencies,
        param_groups=_chat_vlm_param_groups(pixel_budget=pixel_budget),
        recommended_vram_gb=vram,
        license=license_name,
        homepage=f"https://huggingface.co/{repo_id}",
        min_transformers=min_transformers,
        warnings=warnings,
        experimental=experimental,
    )


def _tagger_capabilities() -> CaptionModelCapabilities:
    return CaptionModelCapabilities(
        prompt=False,
        scores=True,
        categories=True,
        batch=True,
        languages=["booru"],
        devices=["cpu", "cuda"],
    )


def _tagger_param_groups(*, include_model: bool) -> Tuple[CaptionModelParamGroup, ...]:
    params = [
        CaptionModelParam(
            name="threshold",
            label="普通标签阈值",
            description="仅保留置信度达到该值的普通标签。降低阈值会增加标签数量，也会增加误识别。",
            type="number",
            default=0.35,
            min=0,
            max=1,
            step=0.01,
        ),
        CaptionModelParam(
            name="characterThreshold",
            label="角色标签阈值",
            description="角色名称通常更容易误判，因此使用独立阈值。",
            type="number",
            default=0.6,
            min=0,
            max=1,
            step=0.01,
        ),
        CaptionModelParam(
            name="addRatingTag",
            label="写入分级标签",
            description="把 general、sensitive、questionable 或 explicit 中置信度最高的一项写入结果。",
            type="boolean",
            default=False,
            advanced=True,
        ),
    ]
    if include_model:
        params.append(
            CaptionModelParam(
                name="addModelTag",
                label="写入模型标签",
                description="写入 CL Tagger 识别出的生成模型类别标签。",
                type="boolean",
                default=False,
                advanced=True,
            )
        )
    return (
        CaptionModelParamGroup(
            id="recognition",
            title="识别阈值",
            description="阈值只作用于模型返回的标签，不影响额外标签和文本合并。",
            params=params,
        ),
    )


def _generation_param_groups() -> Tuple[CaptionModelParamGroup, ...]:
    return (
        CaptionModelParamGroup(
            id="generation",
            title="生成参数",
            description="控制自然语言 Caption 的长度、搜索范围和随机性。",
            params=[
                CaptionModelParam(
                    name="maxNewTokens",
                    label="最大新增 Token",
                    description="限制模型生成 Caption 的最大长度。",
                    type="integer",
                    default=64,
                    min=4,
                    max=512,
                    step=1,
                ),
                CaptionModelParam(
                    name="numBeams",
                    label="Beam 数量",
                    description="更高的 Beam 数量通常更稳定，但推理更慢且占用更多显存。",
                    type="integer",
                    default=3,
                    min=1,
                    max=10,
                    step=1,
                ),
                CaptionModelParam(
                    name="doSample",
                    label="启用随机采样",
                    description="开启后允许使用温度和 Top-P 生成更多样的描述。",
                    type="boolean",
                    default=False,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="temperature",
                    label="采样温度",
                    description="仅在随机采样开启时生效；越高越多样，也越不稳定。",
                    type="number",
                    default=1.0,
                    min=0.1,
                    max=2.0,
                    step=0.05,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="topP",
                    label="Top-P",
                    description="仅在随机采样开启时生效，限制累计概率质量。",
                    type="number",
                    default=0.9,
                    min=0.1,
                    max=1.0,
                    step=0.01,
                    advanced=True,
                ),
            ],
        ),
    )


def _chat_vlm_param_groups(*, pixel_budget: bool) -> Tuple[CaptionModelParamGroup, ...]:
    groups = [
        CaptionModelParamGroup(
            id="prompt",
            title="描述任务",
            description="可直接使用预设，也可以选择“自定义指令”并编辑提示词。",
            params=[
                CaptionModelParam(
                    name="promptPreset",
                    label="提示预设",
                    description=(
                        "简洁描述适合快速检查；详细描述强调画面信息；训练 Prompt 更适合扩散模型；"
                        "Booru 标签只生成逗号分隔文本，不提供可信置信度。"
                    ),
                    type="choice",
                    default="custom",
                    choices=["custom", "straightforward", "descriptive", "training_prompt", "booru"],
                ),
            ],
        ),
        CaptionModelParamGroup(
            id="generation",
            title="生成参数",
            description="VLM 的批次越大、输入越清晰、输出越长，显存占用通常越高。",
            params=[
                CaptionModelParam(
                    name="maxNewTokens",
                    label="最大新增 Token",
                    description="限制单张图片生成文本的最大长度；训练描述通常使用 96–256。",
                    type="integer",
                    default=192,
                    min=8,
                    max=1024,
                    step=1,
                ),
                CaptionModelParam(
                    name="numBeams",
                    label="Beam 数量",
                    description="1 最快；提高后结果可能更稳定，但会明显增加耗时和显存。",
                    type="integer",
                    default=1,
                    min=1,
                    max=5,
                    step=1,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="doSample",
                    label="启用随机采样",
                    description="开启后同一张图片可产生不同表述；批量训练数据通常建议关闭。",
                    type="boolean",
                    default=False,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="temperature",
                    label="采样温度",
                    description="仅在随机采样开启时生效；数值越高，结果越多样也越不稳定。",
                    type="number",
                    default=0.7,
                    min=0.1,
                    max=2.0,
                    step=0.05,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="topP",
                    label="Top-P",
                    description="仅在随机采样开启时生效，用于限制候选 Token 的累计概率。",
                    type="number",
                    default=0.9,
                    min=0.1,
                    max=1.0,
                    step=0.01,
                    advanced=True,
                ),
                CaptionModelParam(
                    name="repetitionPenalty",
                    label="重复惩罚",
                    description="轻微提高可减少重复短语；过高会破坏正常语句。",
                    type="number",
                    default=1.05,
                    min=1.0,
                    max=1.5,
                    step=0.01,
                    advanced=True,
                ),
            ],
        ),
    ]
    if pixel_budget:
        groups.append(
            CaptionModelParamGroup(
                id="vision",
                title="视觉分辨率",
                description="在送入模型前按像素预算等比缩放，控制细节与显存之间的平衡。",
                params=[
                    CaptionModelParam(
                        name="minPixels",
                        label="最小视觉像素",
                        description="小图会等比放大到接近该像素数；默认约 448×448。",
                        type="integer",
                        default=200_704,
                        min=50_176,
                        max=4_014_080,
                        step=3_136,
                        advanced=True,
                    ),
                    CaptionModelParam(
                        name="maxPixels",
                        label="最大视觉像素",
                        description="大图会等比缩小到不超过该预算；默认约 100 万像素。",
                        type="integer",
                        default=1_003_520,
                        min=50_176,
                        max=4_014_080,
                        step=3_136,
                        advanced=True,
                    ),
                ],
            )
        )
    return tuple(groups)


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _minimum_version_issue(descriptor: ModelDescriptor) -> Optional[str]:
    required = descriptor.min_transformers
    if not required:
        return None
    try:
        installed = version("transformers")
        if Version(installed) < Version(required):
            return f"需要 Transformers >= {required}，当前为 {installed}"
    except PackageNotFoundError:
        return "缺少运行依赖：transformers"
    except InvalidVersion:
        return "无法识别当前 Transformers 版本"
    return None


def _validate_param_value(parameter: CaptionModelParam, value: Any) -> Any:
    label = parameter.label
    if parameter.type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{label} 必须是布尔值")
        return value
    if parameter.type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} 必须是整数")
        normalized: Any = value
    elif parameter.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} 必须是数字")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise ValueError(f"{label} 必须是有限数字")
    elif parameter.type in {"string", "multiline"}:
        if not isinstance(value, str):
            raise ValueError(f"{label} 必须是文本")
        normalized = value
    elif parameter.type == "choice":
        if parameter.choices is None or value not in parameter.choices:
            choices = "、".join(str(item) for item in (parameter.choices or []))
            raise ValueError(f"{label} 必须从以下选项中选择：{choices}")
        normalized = value
    else:  # pragma: no cover - guarded by the Pydantic schema
        raise ValueError(f"{label} 使用了未知参数类型")

    if parameter.type in {"integer", "number"}:
        if parameter.min is not None and normalized < parameter.min:
            raise ValueError(f"{label} 不能小于 {parameter.min:g}")
        if parameter.max is not None and normalized > parameter.max:
            raise ValueError(f"{label} 不能大于 {parameter.max:g}")
    return normalized


def _model_cached(descriptor: ModelDescriptor) -> bool:
    if not descriptor.repo_id:
        return False
    try:
        from huggingface_hub import constants, try_to_load_from_cache

        if descriptor.cache_files:
            for filename in descriptor.cache_files:
                cached = try_to_load_from_cache(
                    descriptor.repo_id,
                    filename,
                    revision=descriptor.revision or "main",
                )
                if not isinstance(cached, str) or not Path(cached).is_file():
                    return False
            return True

        repo_cache = Path(constants.HF_HUB_CACHE) / f"models--{descriptor.repo_id.replace('/', '--')}" / "snapshots"
        if not repo_cache.is_dir():
            return False
        weight_patterns = ("*.safetensors", "pytorch_model*.bin")
        for snapshot in repo_cache.iterdir():
            if not snapshot.is_dir() or not (snapshot / "config.json").is_file():
                continue
            if any(any(snapshot.glob(pattern)) for pattern in weight_patterns):
                return True
        return False
    except (ImportError, OSError, ValueError):
        return False


def _available_devices(descriptor: ModelDescriptor) -> List[str]:
    if descriptor.provider == "local-onnx":
        try:
            import onnxruntime as ort

            providers = ort.get_available_providers()
            devices = ["cpu"] if "CPUExecutionProvider" in providers else []
            if any(provider in providers for provider in _ONNX_GPU_PROVIDERS):
                devices.append("cuda")
            return devices
        except (ImportError, RuntimeError):
            return []
    if descriptor.provider == "local-transformers":
        try:
            import torch

            devices = ["cpu"]
            if torch.cuda.is_available():
                devices.append("cuda")
            return devices
        except (ImportError, RuntimeError):
            return []
    return list(descriptor.capabilities.devices)


_ONNX_DEPENDENCIES = (
    ModelDependency("numpy", "numpy"),
    ModelDependency("PIL", "pillow"),
    ModelDependency("huggingface_hub", "huggingface-hub"),
    ModelDependency("onnxruntime", "onnxruntime/onnxruntime-gpu"),
)
_TRANSFORMERS_DEPENDENCIES = (
    ModelDependency("PIL", "pillow"),
    ModelDependency("torch", "torch"),
    ModelDependency("transformers", "transformers"),
)
_ONNX_GPU_PROVIDERS = {
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "DmlExecutionProvider",
}


@lru_cache(maxsize=1)
def get_caption_model_catalog() -> CaptionModelCatalog:
    return CaptionModelCatalog()
