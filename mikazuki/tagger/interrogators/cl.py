import json
import os
import re
from collections import OrderedDict
from glob import glob
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from PIL import UnidentifiedImageError
from huggingface_hub import hf_hub_download
from dataclasses import dataclass
from mikazuki.tagger import dbimutils, format
from mikazuki.tagger.interrogators.base import Interrogator


@dataclass
class LabelData:
    names: list[str]
    rating: list[np.int64]
    general: list[np.int64]
    artist: list[np.int64]
    character: list[np.int64]
    copyright: list[np.int64]
    meta: list[np.int64]
    quality: list[np.int64]
    model: list[np.int64]


def pil_ensure_rgb(image: Image.Image) -> Image.Image:
    if image.mode not in ["RGB", "RGBA"]:
        image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    return image


def pil_pad_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width == height:
        return image
    new_size = max(width, height)
    new_image = Image.new(image.mode, (new_size, new_size), (255, 255, 255))  # Use image.mode
    paste_position = ((new_size - width) // 2, (new_size - height) // 2)
    new_image.paste(image, paste_position)
    return new_image


def get_tags(probs, labels: LabelData):
    result = {
        "rating": [],
        "general": [],
        "character": [],
        "copyright": [],
        "artist": [],
        "meta": [],
        "quality": [],
        "model": []
    }
    # Rating (select max)
    if len(labels.rating) > 0:
        valid_indices = labels.rating[labels.rating < len(probs)]
        if len(valid_indices) > 0:
            rating_probs = probs[valid_indices]
            if len(rating_probs) > 0:
                rating_idx_local = np.argmax(rating_probs)
                rating_idx_global = valid_indices[rating_idx_local]
                if rating_idx_global < len(labels.names) and labels.names[rating_idx_global] is not None:
                    rating_name = labels.names[rating_idx_global]
                    rating_conf = float(rating_probs[rating_idx_local])
                    result["rating"].append((rating_name, rating_conf))
                else:
                    print(f"Warning: Invalid global index {rating_idx_global} for rating tag.")
            else:
                print("Warning: rating_probs became empty after filtering.")
        else:
            print("Warning: No valid indices found for rating tags within probs length.")

    # Quality (select max)
    if len(labels.quality) > 0:
        valid_indices = labels.quality[labels.quality < len(probs)]
        if len(valid_indices) > 0:
            quality_probs = probs[valid_indices]
            if len(quality_probs) > 0:
                quality_idx_local = np.argmax(quality_probs)
                quality_idx_global = valid_indices[quality_idx_local]
                if quality_idx_global < len(labels.names) and labels.names[quality_idx_global] is not None:
                    quality_name = labels.names[quality_idx_global]
                    quality_conf = float(quality_probs[quality_idx_local])
                    result["quality"].append((quality_name, quality_conf))
                else:
                    print(f"Warning: Invalid global index {quality_idx_global} for quality tag.")
            else:
                print("Warning: quality_probs became empty after filtering.")
        else:
            print("Warning: No valid indices found for quality tags within probs length.")

    # All tags for each category (no threshold)
    category_map = {
        "general": labels.general,
        "character": labels.character,
        "copyright": labels.copyright,
        "artist": labels.artist,
        "meta": labels.meta,
        "model": labels.model
    }
    for category, indices in category_map.items():
        if len(indices) > 0:
            valid_indices = indices[(indices < len(probs))]
            if len(valid_indices) > 0:
                category_probs = probs[valid_indices]
                for idx_local, idx_global in enumerate(valid_indices):
                    if idx_global < len(labels.names) and labels.names[idx_global] is not None:
                        result[category].append((labels.names[idx_global], float(category_probs[idx_local])))
                    else:
                        print(f"Warning: Invalid global index {idx_global} for {category} tag.")

    # Sort by probability (descending)
    for k in result:
        result[k] = sorted(result[k], key=lambda x: x[1], reverse=True)
    return result


class CLTaggerInterrogator(Interrogator):
    def __init__(
            self,
            name: str,
            model_path='model.onnx',
            tag_mapping_path='tag_mapping.json',
            **kwargs
    ) -> None:
        super().__init__(name)
        self.model_path = model_path
        self.tag_mapping_path = tag_mapping_path
        self.kwargs = kwargs

    def download(self) -> Tuple[os.PathLike, os.PathLike]:
        print(f"Loading {self.name} model file from {self.kwargs['repo_id']}")

        model_path = Path(hf_hub_download(
            **self.kwargs, filename=self.model_path))
        tag_mapping_path = Path(hf_hub_download(
            **self.kwargs, filename=self.tag_mapping_path))
        return model_path, tag_mapping_path

    def load(self) -> None:
        model_path, tag_mapping_path = self.download()

        import torch
        from onnxruntime import InferenceSession

        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        self.model = InferenceSession(str(model_path), providers=providers)

        print(f'Loaded {self.name} model from {model_path}')

        self.tags = self.load_tag_mapping(tag_mapping_path)

    def load_tag_mapping(self, mapping_path):
        # Use the implementation from the original app.py as it was confirmed working
        with open(mapping_path, 'r', encoding='utf-8') as f:
            tag_mapping_data = json.load(f)
        # Check format compatibility (can be dict of dicts or dict with idx_to_tag/tag_to_category)
        if isinstance(tag_mapping_data, dict) and "idx_to_tag" in tag_mapping_data:
            idx_to_tag = {int(k): v for k, v in tag_mapping_data["idx_to_tag"].items()}
            tag_to_category = tag_mapping_data["tag_to_category"]
        elif isinstance(tag_mapping_data, dict):
            # Assuming the dict-of-dicts format from previous tests
            try:
                tag_mapping_data_int_keys = {int(k): v for k, v in tag_mapping_data.items()}
                idx_to_tag = {idx: data['tag'] for idx, data in tag_mapping_data_int_keys.items()}
                tag_to_category = {data['tag']: data['category'] for data in tag_mapping_data_int_keys.values()}
            except (KeyError, ValueError) as e:
                raise ValueError(f"Unsupported tag mapping format (dict): {e}. Expected int keys with 'tag' and 'category'.")
        else:
            raise ValueError("Unsupported tag mapping format: Expected a dictionary.")

        names = [None] * (max(idx_to_tag.keys()) + 1)
        rating, general, artist, character, copyright, meta, quality, model_name = [], [], [], [], [], [], [], []
        for idx, tag in idx_to_tag.items():
            if idx >= len(names):
                names.extend([None] * (idx - len(names) + 1))
            names[idx] = tag
            category = tag_to_category.get(tag, 'Unknown')  # Handle missing category mapping gracefully
            idx_int = int(idx)
            if category == 'Rating':
                rating.append(idx_int)
            elif category == 'General':
                general.append(idx_int)
            elif category == 'Artist':
                artist.append(idx_int)
            elif category == 'Character':
                character.append(idx_int)
            elif category == 'Copyright':
                copyright.append(idx_int)
            elif category == 'Meta':
                meta.append(idx_int)
            elif category == 'Quality':
                quality.append(idx_int)
            elif category == 'Model':
                model_name.append(idx_int)

        return LabelData(names=names, rating=np.array(rating, dtype=np.int64), general=np.array(general, dtype=np.int64), artist=np.array(artist, dtype=np.int64),
                         character=np.array(character, dtype=np.int64), copyright=np.array(copyright, dtype=np.int64), meta=np.array(meta, dtype=np.int64), quality=np.array(quality, dtype=np.int64), model=np.array(model_name, dtype=np.int64)), idx_to_tag, tag_to_category

    def preprocess_image(self, image: Image.Image, target_size=(448, 448)):
        # Adapted from onnx_predict.py's version
        image = pil_ensure_rgb(image)
        image = pil_pad_square(image)
        image_resized = image.resize(target_size, Image.BICUBIC)
        img_array = np.array(image_resized, dtype=np.float32) / 255.0
        img_array = img_array.transpose(2, 0, 1)  # HWC -> CHW
        # Assuming model expects RGB based on original code, no BGR conversion here
        img_array = img_array[::-1, :, :]  # BGR conversion if needed - UNCOMMENTED based on user feedback
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
        std = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
        img_array = (img_array - mean) / std
        img_array = np.expand_dims(img_array, axis=0)  # Add batch dimension
        return image, img_array

    def interrogate(
            self,
            image: Image
    ) -> dict[str, list]:

        # init model
        if not hasattr(self, 'model') or self.model is None:
            self.load()

        input_name = self.model.get_inputs()[0].name
        output_name = self.model.get_outputs()[0].name

        original_pil_image, input_tensor = self.preprocess_image(image)
        input_tensor = input_tensor.astype(np.float32)

        outputs = self.model.run([output_name], {input_name: input_tensor})[0]

        if np.isnan(outputs).any() or np.isinf(outputs).any():
            print("Warning: NaN or Inf detected in model output. Clamping...")
            outputs = np.nan_to_num(outputs, nan=0.0, posinf=1.0, neginf=0.0)  # Clamp to 0-1 range

        # Apply sigmoid (outputs are likely logits)
        # Use a stable sigmoid implementation
        def stable_sigmoid(x):
            return 1 / (1 + np.exp(-np.clip(x, -30, 30)))  # Clip to avoid overflow
        probs = stable_sigmoid(outputs[0])  # Assuming batch size 1

        predictions = get_tags(probs, self.tags[0])  # g_labels_data
        # output_tags = []
        # if predictions.get("rating"): output_tags.append(predictions["rating"][0][0].replace("_", " "))
        # if predictions.get("quality"): output_tags.append(predictions["quality"][0][0].replace("_", " "))
        # # Add other categories, respecting order and filtering meta if needed
        # for category in ["artist", "character", "copyright", "general", "meta", "model"]:
        #     tags_in_category = predictions.get(category, [])
        #     for tag, prob in tags_in_category:
        #         # Basic meta tag filtering for text output
        #         if category == "meta" and any(p in tag.lower() for p in ['id', 'commentary', 'request', 'mismatch']):
        #             continue
        #         output_tags.append(tag.replace("_", " "))
        # output_text = ", ".join(output_tags)

        print(predictions)
        return predictions