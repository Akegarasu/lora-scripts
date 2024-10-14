import logging
import sys
import threading
from typing import *
import json
import struct

import torch
from torchvision import transforms
from diffusers import EulerAncestralDiscreteScheduler
import diffusers.schedulers.scheduling_euler_ancestral_discrete
from diffusers.schedulers.scheduling_euler_ancestral_discrete import EulerAncestralDiscreteSchedulerOutput
import cv2
from PIL import Image
import numpy as np


def fire_in_thread(f, *args, **kwargs):
    threading.Thread(target=f, args=args, kwargs=kwargs).start()


def add_logging_arguments(parser):
    parser.add_argument(
        "--console_log_level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level, default is INFO / ログレベルを設定する。デフォルトはINFO",
    )
    parser.add_argument(
        "--console_log_file",
        type=str,
        default=None,
        help="Log to a file instead of stderr / 標準エラー出力ではなくファイルにログを出力する",
    )
    parser.add_argument("--console_log_simple", action="store_true", help="Simple log output / シンプルなログ出力")


def setup_logging(args=None, log_level=None, reset=False):
    if logging.root.handlers:
        if reset:
            # remove all handlers
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
        else:
            return

    # log_level can be set by the caller or by the args, the caller has priority. If not set, use INFO
    if log_level is None and args is not None:
        log_level = args.console_log_level
    if log_level is None:
        log_level = "INFO"
    log_level = getattr(logging, log_level)

    msg_init = None
    if args is not None and args.console_log_file:
        handler = logging.FileHandler(args.console_log_file, mode="w")
    else:
        handler = None
        if not args or not args.console_log_simple:
            try:
                from rich.logging import RichHandler
                from rich.console import Console
                from rich.logging import RichHandler

                handler = RichHandler(console=Console(stderr=True))
            except ImportError:
                # print("rich is not installed, using basic logging")
                msg_init = "rich is not installed, using basic logging"

        if handler is None:
            handler = logging.StreamHandler(sys.stdout)  # same as print
            handler.propagate = False

    formatter = logging.Formatter(
        fmt="%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.root.setLevel(log_level)
    logging.root.addHandler(handler)

    if msg_init is not None:
        logger = logging.getLogger(__name__)
        logger.info(msg_init)


def str_to_dtype(s: Optional[str], default_dtype: Optional[torch.dtype] = None) -> torch.dtype:
    """
    Convert a string to a torch.dtype

    Args:
        s: string representation of the dtype
        default_dtype: default dtype to return if s is None

    Returns:
        torch.dtype: the corresponding torch.dtype

    Raises:
        ValueError: if the dtype is not supported

    Examples:
        >>> str_to_dtype("float32")
        torch.float32
        >>> str_to_dtype("fp32")
        torch.float32
        >>> str_to_dtype("float16")
        torch.float16
        >>> str_to_dtype("fp16")
        torch.float16
        >>> str_to_dtype("bfloat16")
        torch.bfloat16
        >>> str_to_dtype("bf16")
        torch.bfloat16
        >>> str_to_dtype("fp8")
        torch.float8_e4m3fn
        >>> str_to_dtype("fp8_e4m3fn")
        torch.float8_e4m3fn
        >>> str_to_dtype("fp8_e4m3fnuz")
        torch.float8_e4m3fnuz
        >>> str_to_dtype("fp8_e5m2")
        torch.float8_e5m2
        >>> str_to_dtype("fp8_e5m2fnuz")
        torch.float8_e5m2fnuz
    """
    if s is None:
        return default_dtype
    if s in ["bf16", "bfloat16"]:
        return torch.bfloat16
    elif s in ["fp16", "float16"]:
        return torch.float16
    elif s in ["fp32", "float32", "float"]:
        return torch.float32
    elif s in ["fp8_e4m3fn", "e4m3fn", "float8_e4m3fn"]:
        return torch.float8_e4m3fn
    elif s in ["fp8_e4m3fnuz", "e4m3fnuz", "float8_e4m3fnuz"]:
        return torch.float8_e4m3fnuz
    elif s in ["fp8_e5m2", "e5m2", "float8_e5m2"]:
        return torch.float8_e5m2
    elif s in ["fp8_e5m2fnuz", "e5m2fnuz", "float8_e5m2fnuz"]:
        return torch.float8_e5m2fnuz
    elif s in ["fp8", "float8"]:
        return torch.float8_e4m3fn  # default fp8
    else:
        raise ValueError(f"Unsupported dtype: {s}")


def mem_eff_save_file(tensors: Dict[str, torch.Tensor], filename: str, metadata: Dict[str, Any] = None):
    """
    memory efficient save file
    """

    _TYPES = {
        torch.float64: "F64",
        torch.float32: "F32",
        torch.float16: "F16",
        torch.bfloat16: "BF16",
        torch.int64: "I64",
        torch.int32: "I32",
        torch.int16: "I16",
        torch.int8: "I8",
        torch.uint8: "U8",
        torch.bool: "BOOL",
        getattr(torch, "float8_e5m2", None): "F8_E5M2",
        getattr(torch, "float8_e4m3fn", None): "F8_E4M3",
    }
    _ALIGN = 256

    def validate_metadata(metadata: Dict[str, Any]) -> Dict[str, str]:
        validated = {}
        for key, value in metadata.items():
            if not isinstance(key, str):
                raise ValueError(f"Metadata key must be a string, got {type(key)}")
            if not isinstance(value, str):
                print(f"Warning: Metadata value for key '{key}' is not a string. Converting to string.")
                validated[key] = str(value)
            else:
                validated[key] = value
        return validated

    print(f"Using memory efficient save file: {filename}")

    header = {}
    offset = 0
    if metadata:
        header["__metadata__"] = validate_metadata(metadata)
    for k, v in tensors.items():
        if v.numel() == 0:  # empty tensor
            header[k] = {"dtype": _TYPES[v.dtype], "shape": list(v.shape), "data_offsets": [offset, offset]}
        else:
            size = v.numel() * v.element_size()
            header[k] = {"dtype": _TYPES[v.dtype], "shape": list(v.shape), "data_offsets": [offset, offset + size]}
            offset += size

    hjson = json.dumps(header).encode("utf-8")
    hjson += b" " * (-(len(hjson) + 8) % _ALIGN)

    with open(filename, "wb") as f:
        f.write(struct.pack("<Q", len(hjson)))
        f.write(hjson)

        for k, v in tensors.items():
            if v.numel() == 0:
                continue
            if v.is_cuda:
                # Direct GPU to disk save
                with torch.cuda.device(v.device):
                    if v.dim() == 0:  # if scalar, need to add a dimension to work with view
                        v = v.unsqueeze(0)
                    tensor_bytes = v.contiguous().view(torch.uint8)
                    tensor_bytes.cpu().numpy().tofile(f)
            else:
                # CPU tensor save
                if v.dim() == 0:  # if scalar, need to add a dimension to work with view
                    v = v.unsqueeze(0)
                v.contiguous().view(torch.uint8).numpy().tofile(f)


class MemoryEfficientSafeOpen:
    # does not support metadata loading
    def __init__(self, filename):
        self.filename = filename
        self.header, self.header_size = self._read_header()
        self.file = open(filename, "rb")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.close()

    def keys(self):
        return [k for k in self.header.keys() if k != "__metadata__"]

    def get_tensor(self, key):
        if key not in self.header:
            raise KeyError(f"Tensor '{key}' not found in the file")

        metadata = self.header[key]
        offset_start, offset_end = metadata["data_offsets"]

        if offset_start == offset_end:
            tensor_bytes = None
        else:
            # adjust offset by header size
            self.file.seek(self.header_size + 8 + offset_start)
            tensor_bytes = self.file.read(offset_end - offset_start)

        return self._deserialize_tensor(tensor_bytes, metadata)

    def _read_header(self):
        with open(self.filename, "rb") as f:
            header_size = struct.unpack("<Q", f.read(8))[0]
            header_json = f.read(header_size).decode("utf-8")
            return json.loads(header_json), header_size

    def _deserialize_tensor(self, tensor_bytes, metadata):
        dtype = self._get_torch_dtype(metadata["dtype"])
        shape = metadata["shape"]

        if tensor_bytes is None:
            byte_tensor = torch.empty(0, dtype=torch.uint8)
        else:
            tensor_bytes = bytearray(tensor_bytes)  # make it writable
            byte_tensor = torch.frombuffer(tensor_bytes, dtype=torch.uint8)

        # process float8 types
        if metadata["dtype"] in ["F8_E5M2", "F8_E4M3"]:
            return self._convert_float8(byte_tensor, metadata["dtype"], shape)

        # convert to the target dtype and reshape
        return byte_tensor.view(dtype).reshape(shape)

    @staticmethod
    def _get_torch_dtype(dtype_str):
        dtype_map = {
            "F64": torch.float64,
            "F32": torch.float32,
            "F16": torch.float16,
            "BF16": torch.bfloat16,
            "I64": torch.int64,
            "I32": torch.int32,
            "I16": torch.int16,
            "I8": torch.int8,
            "U8": torch.uint8,
            "BOOL": torch.bool,
        }
        # add float8 types if available
        if hasattr(torch, "float8_e5m2"):
            dtype_map["F8_E5M2"] = torch.float8_e5m2
        if hasattr(torch, "float8_e4m3fn"):
            dtype_map["F8_E4M3"] = torch.float8_e4m3fn
        return dtype_map.get(dtype_str)

    @staticmethod
    def _convert_float8(byte_tensor, dtype_str, shape):
        if dtype_str == "F8_E5M2" and hasattr(torch, "float8_e5m2"):
            return byte_tensor.view(torch.float8_e5m2).reshape(shape)
        elif dtype_str == "F8_E4M3" and hasattr(torch, "float8_e4m3fn"):
            return byte_tensor.view(torch.float8_e4m3fn).reshape(shape)
        else:
            # # convert to float16 if float8 is not supported
            # print(f"Warning: {dtype_str} is not supported in this PyTorch version. Converting to float16.")
            # return byte_tensor.view(torch.uint8).to(torch.float16).reshape(shape)
            raise ValueError(f"Unsupported float8 type: {dtype_str} (upgrade PyTorch to support float8 types)")

def pil_resize(image, size, interpolation=Image.LANCZOS):
    has_alpha = image.shape[2] == 4 if len(image.shape) == 3 else False

    if has_alpha:
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA))
    else:
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    resized_pil = pil_image.resize(size, interpolation)

    # Convert back to cv2 format
    if has_alpha:
        resized_cv2 = cv2.cvtColor(np.array(resized_pil), cv2.COLOR_RGBA2BGRA)
    else:
        resized_cv2 = cv2.cvtColor(np.array(resized_pil), cv2.COLOR_RGB2BGR)

    return resized_cv2


# TODO make inf_utils.py


# region Gradual Latent hires fix


class GradualLatent:
    def __init__(
        self,
        ratio,
        start_timesteps,
        every_n_steps,
        ratio_step,
        s_noise=1.0,
        gaussian_blur_ksize=None,
        gaussian_blur_sigma=0.5,
        gaussian_blur_strength=0.5,
        unsharp_target_x=True,
    ):
        self.ratio = ratio
        self.start_timesteps = start_timesteps
        self.every_n_steps = every_n_steps
        self.ratio_step = ratio_step
        self.s_noise = s_noise
        self.gaussian_blur_ksize = gaussian_blur_ksize
        self.gaussian_blur_sigma = gaussian_blur_sigma
        self.gaussian_blur_strength = gaussian_blur_strength
        self.unsharp_target_x = unsharp_target_x

    def __str__(self) -> str:
        return (
            f"GradualLatent(ratio={self.ratio}, start_timesteps={self.start_timesteps}, "
            + f"every_n_steps={self.every_n_steps}, ratio_step={self.ratio_step}, s_noise={self.s_noise}, "
            + f"gaussian_blur_ksize={self.gaussian_blur_ksize}, gaussian_blur_sigma={self.gaussian_blur_sigma}, gaussian_blur_strength={self.gaussian_blur_strength}, "
            + f"unsharp_target_x={self.unsharp_target_x})"
        )

    def apply_unshark_mask(self, x: torch.Tensor):
        if self.gaussian_blur_ksize is None:
            return x
        blurred = transforms.functional.gaussian_blur(x, self.gaussian_blur_ksize, self.gaussian_blur_sigma)
        # mask = torch.sigmoid((x - blurred) * self.gaussian_blur_strength)
        mask = (x - blurred) * self.gaussian_blur_strength
        sharpened = x + mask
        return sharpened

    def interpolate(self, x: torch.Tensor, resized_size, unsharp=True):
        org_dtype = x.dtype
        if org_dtype == torch.bfloat16:
            x = x.float()

        x = torch.nn.functional.interpolate(x, size=resized_size, mode="bicubic", align_corners=False).to(dtype=org_dtype)

        # apply unsharp mask / アンシャープマスクを適用する
        if unsharp and self.gaussian_blur_ksize:
            x = self.apply_unshark_mask(x)

        return x


class EulerAncestralDiscreteSchedulerGL(EulerAncestralDiscreteScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resized_size = None
        self.gradual_latent = None

    def set_gradual_latent_params(self, size, gradual_latent: GradualLatent):
        self.resized_size = size
        self.gradual_latent = gradual_latent

    def step(
        self,
        model_output: torch.FloatTensor,
        timestep: Union[float, torch.FloatTensor],
        sample: torch.FloatTensor,
        generator: Optional[torch.Generator] = None,
        return_dict: bool = True,
    ) -> Union[EulerAncestralDiscreteSchedulerOutput, Tuple]:
        """
        Predict the sample from the previous timestep by reversing the SDE. This function propagates the diffusion
        process from the learned model outputs (most often the predicted noise).

        Args:
            model_output (`torch.FloatTensor`):
                The direct output from learned diffusion model.
            timestep (`float`):
                The current discrete timestep in the diffusion chain.
            sample (`torch.FloatTensor`):
                A current instance of a sample created by the diffusion process.
            generator (`torch.Generator`, *optional*):
                A random number generator.
            return_dict (`bool`):
                Whether or not to return a
                [`~schedulers.scheduling_euler_ancestral_discrete.EulerAncestralDiscreteSchedulerOutput`] or tuple.

        Returns:
            [`~schedulers.scheduling_euler_ancestral_discrete.EulerAncestralDiscreteSchedulerOutput`] or `tuple`:
                If return_dict is `True`,
                [`~schedulers.scheduling_euler_ancestral_discrete.EulerAncestralDiscreteSchedulerOutput`] is returned,
                otherwise a tuple is returned where the first element is the sample tensor.

        """

        if isinstance(timestep, int) or isinstance(timestep, torch.IntTensor) or isinstance(timestep, torch.LongTensor):
            raise ValueError(
                (
                    "Passing integer indices (e.g. from `enumerate(timesteps)`) as timesteps to"
                    " `EulerDiscreteScheduler.step()` is not supported. Make sure to pass"
                    " one of the `scheduler.timesteps` as a timestep."
                ),
            )

        if not self.is_scale_input_called:
            # logger.warning(
            print(
                "The `scale_model_input` function should be called before `step` to ensure correct denoising. "
                "See `StableDiffusionPipeline` for a usage example."
            )

        if self.step_index is None:
            self._init_step_index(timestep)

        sigma = self.sigmas[self.step_index]

        # 1. compute predicted original sample (x_0) from sigma-scaled predicted noise
        if self.config.prediction_type == "epsilon":
            pred_original_sample = sample - sigma * model_output
        elif self.config.prediction_type == "v_prediction":
            # * c_out + input * c_skip
            pred_original_sample = model_output * (-sigma / (sigma**2 + 1) ** 0.5) + (sample / (sigma**2 + 1))
        elif self.config.prediction_type == "sample":
            raise NotImplementedError("prediction_type not implemented yet: sample")
        else:
            raise ValueError(f"prediction_type given as {self.config.prediction_type} must be one of `epsilon`, or `v_prediction`")

        sigma_from = self.sigmas[self.step_index]
        sigma_to = self.sigmas[self.step_index + 1]
        sigma_up = (sigma_to**2 * (sigma_from**2 - sigma_to**2) / sigma_from**2) ** 0.5
        sigma_down = (sigma_to**2 - sigma_up**2) ** 0.5

        # 2. Convert to an ODE derivative
        derivative = (sample - pred_original_sample) / sigma

        dt = sigma_down - sigma

        device = model_output.device
        if self.resized_size is None:
            prev_sample = sample + derivative * dt

            noise = diffusers.schedulers.scheduling_euler_ancestral_discrete.randn_tensor(
                model_output.shape, dtype=model_output.dtype, device=device, generator=generator
            )
            s_noise = 1.0
        else:
            print("resized_size", self.resized_size, "model_output.shape", model_output.shape, "sample.shape", sample.shape)
            s_noise = self.gradual_latent.s_noise

            if self.gradual_latent.unsharp_target_x:
                prev_sample = sample + derivative * dt
                prev_sample = self.gradual_latent.interpolate(prev_sample, self.resized_size)
            else:
                sample = self.gradual_latent.interpolate(sample, self.resized_size)
                derivative = self.gradual_latent.interpolate(derivative, self.resized_size, unsharp=False)
                prev_sample = sample + derivative * dt

            noise = diffusers.schedulers.scheduling_euler_ancestral_discrete.randn_tensor(
                (model_output.shape[0], model_output.shape[1], self.resized_size[0], self.resized_size[1]),
                dtype=model_output.dtype,
                device=device,
                generator=generator,
            )

        prev_sample = prev_sample + noise * sigma_up * s_noise

        # upon completion increase step index by one
        self._step_index += 1

        if not return_dict:
            return (prev_sample,)

        return EulerAncestralDiscreteSchedulerOutput(prev_sample=prev_sample, pred_original_sample=pred_original_sample)


# endregion
