import re
import hashlib

from typing import Dict, Callable, NamedTuple
from pathlib import Path


class Info(NamedTuple):
    path: Path
    output_ext: str


def hash(i: Info, algo='sha1') -> str:
    try:
        hash = hashlib.new(algo)
    except ImportError:
        raise ValueError(f"'{algo}' is invalid hash algorithm")

    # TODO: is okay to hash large image?
    with open(i.path, 'rb') as file:
        hash.update(file.read())

    return hash.hexdigest()


pattern = re.compile(r'\[([\w:]+)\]')

# all function must returns string or raise TypeError or ValueError
# other errors will cause the extension error
available_formats: Dict[str, Callable] = {
    'name': lambda i: i.path.stem,
    'extension': lambda i: i.path.suffix[1:],
    'hash': hash,

    'output_extension': lambda i: i.output_ext
}


def format(match: re.Match, info: Info) -> str:
    matches = match[1].split(':')
    name, args = matches[0], matches[1:]

    if name not in available_formats:
        return match[0]

    return available_formats[name](info, *args)
