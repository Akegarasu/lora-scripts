import re
from typing import Dict, List, Tuple
from PIL import Image

tag_escape_pattern = re.compile(r'([\\()])')


class Interrogator:
    @staticmethod
    def postprocess_tags(
            tags: Dict[str, List[Tuple[str, float]]],

            threshold=0.35,
            character_threshold=0.6,

            add_rating_tag=False,
            add_model_tag=False,

            additional_tags: List[str] = [],
            exclude_tags: List[str] = [],
            sort_by_alphabetical_order=False,
            add_confident_as_weight=False,
            replace_underscore=False,
            replace_underscore_excludes: List[str] = [],
            escape_tag=False
    ) -> Dict[str, float]:

        ok_tags = {}

        if not add_rating_tag and 'rating' in tags:
            del tags['rating']

        if not add_model_tag and 'model' in tags:
            del tags['model']

        if 'character' in tags:
            for t, c in tags['character']:
                if c >= character_threshold:
                    ok_tags[t] = c

            del tags['character']

        for t in additional_tags:
            ok_tags[t] = 1.0

        for category in tags:
            for t, c in tags[category]:
                if c >= threshold:
                    ok_tags[t] = c

        for e in exclude_tags:
            del ok_tags[e]

        if sort_by_alphabetical_order:
            ok_tags = dict(sorted(ok_tags.items()))
        # sort tag by confidence
        else:
            ok_tags = dict(sorted(ok_tags.items(), key=lambda item: item[1], reverse=True))

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
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Interrogate the given image and return tags with their confidence scores.
        :param image: The input image to be interrogated.
        :return: A dictionary with categories as keys and lists of (tag, confidence)

        categories: "rating", "general", "character", "copyright", "artist", "meta", "quality", "model"
        """

        raise NotImplementedError()
