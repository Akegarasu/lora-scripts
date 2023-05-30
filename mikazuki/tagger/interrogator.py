# from https://github.com/toriato/stable-diffusion-webui-wd14-tagger
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

from mikazuki.tagger import dbimutils, format

tag_escape_pattern = re.compile(r'([\\()])')


class Interrogator:
    @staticmethod
    def postprocess_tags(
            tags: Dict[str, float],

            threshold=0.35,
            additional_tags: List[str] = [],
            exclude_tags: List[str] = [],
            sort_by_alphabetical_order=False,
            add_confident_as_weight=False,
            replace_underscore=False,
            replace_underscore_excludes: List[str] = [],
            escape_tag=False
    ) -> Dict[str, float]:
        for t in additional_tags:
            tags[t] = 1.0

        # those lines are totally not "pythonic" but looks better to me
        tags = {
            t: c

            # sort by tag name or confident
            for t, c in sorted(
                tags.items(),
                key=lambda i: i[0 if sort_by_alphabetical_order else 1],
                reverse=not sort_by_alphabetical_order
            )

            # filter tags
            if (
                    c >= threshold
                    and t not in exclude_tags
            )
        }

        new_tags = []
        for tag in list(tags):
            new_tag = tag

            if replace_underscore and tag not in replace_underscore_excludes:
                new_tag = new_tag.replace('_', ' ')

            if escape_tag:
                new_tag = tag_escape_pattern.sub(r'\\\1', new_tag)

            if add_confident_as_weight:
                new_tag = f'({new_tag}:{tags[tag]})'

            new_tags.append((new_tag, tags[tag]))
        tags = dict(new_tags)

        return tags

    def __init__(self, name: str) -> None:
        self.name = name

    def load(self):
        raise NotImplementedError()

    def unload(self) -> bool:
        unloaded = False

        if hasattr(self, 'model') and self.model is not None:
            del self.model
            unloaded = True
            print(f'Unloaded {self.name}')

        if hasattr(self, 'tags'):
            del self.tags

        return unloaded

    def interrogate(
            self,
            image: Image
    ) -> Tuple[
        Dict[str, float],  # rating confidents
        Dict[str, float]  # tag confidents
    ]:
        raise NotImplementedError()


class WaifuDiffusionInterrogator(Interrogator):
    def __init__(
            self,
            name: str,
            model_path='model.onnx',
            tags_path='selected_tags.csv',
            **kwargs
    ) -> None:
        super().__init__(name)
        self.model_path = model_path
        self.tags_path = tags_path
        self.kwargs = kwargs

    def download(self) -> Tuple[os.PathLike, os.PathLike]:
        print(f"Loading {self.name} model file from {self.kwargs['repo_id']}")

        model_path = Path(hf_hub_download(
            **self.kwargs, filename=self.model_path))
        tags_path = Path(hf_hub_download(
            **self.kwargs, filename=self.tags_path))
        return model_path, tags_path

    def load(self) -> None:
        model_path, tags_path = self.download()

        # only one of these packages should be installed at a time in any one environment
        # https://onnxruntime.ai/docs/get-started/with-python.html#install-onnx-runtime
        # TODO: remove old package when the environment changes?
        from mikazuki.utils import is_installed, run_pip
        if not is_installed('onnxruntime'):
            package = os.environ.get(
                'ONNXRUNTIME_PACKAGE',
                'onnxruntime-gpu'
            )

            run_pip(f'install {package}', 'onnxruntime')

        # Load torch to load cuda libs built in torch for onnxruntime, do not delete this.
        import torch
        from onnxruntime import InferenceSession

        # https://onnxruntime.ai/docs/execution-providers/
        # https://github.com/toriato/stable-diffusion-webui-wd14-tagger/commit/e4ec460122cf674bbf984df30cdb10b4370c1224#r92654958
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        self.model = InferenceSession(str(model_path), providers=providers)

        print(f'Loaded {self.name} model from {model_path}')

        self.tags = pd.read_csv(tags_path)

    def interrogate(
            self,
            image: Image
    ) -> Tuple[
        Dict[str, float],  # rating confidents
        Dict[str, float]  # tag confidents
    ]:
        # init model
        if not hasattr(self, 'model') or self.model is None:
            self.load()

        # code for converting the image and running the model is taken from the link below
        # thanks, SmilingWolf!
        # https://huggingface.co/spaces/SmilingWolf/wd-v1-4-tags/blob/main/app.py

        # convert an image to fit the model
        _, height, _, _ = self.model.get_inputs()[0].shape

        # alpha to white
        image = image.convert('RGBA')
        new_image = Image.new('RGBA', image.size, 'WHITE')
        new_image.paste(image, mask=image)
        image = new_image.convert('RGB')
        image = np.asarray(image)

        # PIL RGB to OpenCV BGR
        image = image[:, :, ::-1]

        image = dbimutils.make_square(image, height)
        image = dbimutils.smart_resize(image, height)
        image = image.astype(np.float32)
        image = np.expand_dims(image, 0)

        # evaluate model
        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        confidents = self.model.run([label_name], {input_name: image})[0]

        tags = self.tags[:][['name']]
        tags['confidents'] = confidents[0]

        # first 4 items are for rating (general, sensitive, questionable, explicit)
        ratings = dict(tags[:4].values)

        # rest are regular tags
        tags = dict(tags[4:].values)

        return ratings, tags


available_interrogators = {
    'wd14-convnextv2-v2': WaifuDiffusionInterrogator(
        'wd14-convnextv2-v2', repo_id='SmilingWolf/wd-v1-4-convnextv2-tagger-v2',
        revision='v2.0'
    ),
    'wd14-swinv2-v2': WaifuDiffusionInterrogator(
        'wd14-swinv2-v2', repo_id='SmilingWolf/wd-v1-4-swinv2-tagger-v2',
        revision='v2.0'
    ),
    'wd14-vit-v2': WaifuDiffusionInterrogator(
        'wd14-vit-v2', repo_id='SmilingWolf/wd-v1-4-vit-tagger-v2',
        revision='v2.0'
    ),
}


def split_str(s: str, separator=',') -> List[str]:
    return [x.strip() for x in s.split(separator) if x]


def on_interrogate(
        image: Image,
        batch_input_glob: str,
        batch_input_recursive: bool,
        batch_output_dir: str,
        batch_output_filename_format: str,
        batch_output_action_on_conflict: str,
        batch_remove_duplicated_tag: bool,
        batch_output_save_json: bool,

        interrogator: Interrogator,
        threshold: float,
        additional_tags: str,
        exclude_tags: str,
        sort_by_alphabetical_order: bool,
        add_confident_as_weight: bool,
        replace_underscore: bool,
        replace_underscore_excludes: str,
        escape_tag: bool,

        unload_model_after_running: bool
):
    postprocess_opts = (
        threshold,
        split_str(additional_tags),
        split_str(exclude_tags),
        sort_by_alphabetical_order,
        add_confident_as_weight,
        replace_underscore,
        split_str(replace_underscore_excludes),
        escape_tag
    )

    # batch process
    batch_input_glob = batch_input_glob.strip()
    batch_output_dir = batch_output_dir.strip()
    batch_output_filename_format = batch_output_filename_format.strip()

    if batch_input_glob != '':
        # if there is no glob pattern, insert it automatically
        if not batch_input_glob.endswith('*'):
            if not batch_input_glob.endswith(os.sep):
                batch_input_glob += os.sep
            batch_input_glob += '*'

        # get root directory of input glob pattern
        base_dir = batch_input_glob.replace('?', '*')
        base_dir = base_dir.split(os.sep + '*').pop(0)

        # check the input directory path
        if not os.path.isdir(base_dir):
            print('input path is not a directory / 输入的路径不是文件夹，终止识别')
            return 'input path is not a directory'

        # this line is moved here because some reason
        # PIL.Image.registered_extensions() returns only PNG if you call too early
        supported_extensions = [
            e
            for e, f in Image.registered_extensions().items()
            if f in Image.OPEN
        ]

        paths = [
            Path(p)
            for p in glob(batch_input_glob, recursive=batch_input_recursive)
            if '.' + p.split('.').pop().lower() in supported_extensions
        ]

        print(f'found {len(paths)} image(s)')

        for path in paths:
            try:
                image = Image.open(path)
            except UnidentifiedImageError:
                # just in case, user has mysterious file...
                print(f'${path} is not supported image type')
                continue

            # guess the output path
            base_dir_last = Path(base_dir).parts[-1]
            base_dir_last_idx = path.parts.index(base_dir_last)
            output_dir = Path(
                batch_output_dir) if batch_output_dir else Path(base_dir)
            output_dir = output_dir.joinpath(
                *path.parts[base_dir_last_idx + 1:]).parent

            output_dir.mkdir(0o777, True, True)

            # format output filename
            format_info = format.Info(path, 'txt')

            try:
                formatted_output_filename = format.pattern.sub(
                    lambda m: format.format(m, format_info),
                    batch_output_filename_format
                )
            except (TypeError, ValueError) as error:
                return str(error)

            output_path = output_dir.joinpath(
                formatted_output_filename
            )

            output = []

            if output_path.is_file():
                output.append(output_path.read_text(errors='ignore').strip())

                if batch_output_action_on_conflict == 'ignore':
                    print(f'skipping {path}')
                    continue

            ratings, tags = interrogator.interrogate(image)
            processed_tags = Interrogator.postprocess_tags(
                tags,
                *postprocess_opts
            )

            # TODO: switch for less print
            print(
                f'found {len(processed_tags)} tags out of {len(tags)} from {path}'
            )

            plain_tags = ', '.join(processed_tags)

            if batch_output_action_on_conflict == 'copy':
                output = [plain_tags]
            elif batch_output_action_on_conflict == 'prepend':
                output.insert(0, plain_tags)
            else:
                output.append(plain_tags)

            if batch_remove_duplicated_tag:
                output_path.write_text(
                    ', '.join(
                        OrderedDict.fromkeys(
                            map(str.strip, ','.join(output).split(','))
                        )
                    ),
                    encoding='utf-8'
                )
            else:
                output_path.write_text(
                    ', '.join(output),
                    encoding='utf-8'
                )

            if batch_output_save_json:
                output_path.with_suffix('.json').write_text(
                    json.dumps([ratings, tags])
                )

        print('all done / 识别完成')

    if unload_model_after_running:
        interrogator.unload()

    return 'Succeed'
