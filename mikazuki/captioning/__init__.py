def get_caption_model_catalog():
    from .catalog import get_caption_model_catalog as factory

    return factory()


def get_caption_model_manager():
    from .adapters import get_caption_model_manager as factory

    return factory()


def get_caption_dataset_registry():
    from .datasets import get_caption_dataset_registry as factory

    return factory()


def get_caption_runner():
    from .runner import get_caption_runner as factory

    return factory()


def get_caption_store():
    from .store import get_caption_store as factory

    return factory()

__all__ = [
    "get_caption_dataset_registry",
    "get_caption_model_catalog",
    "get_caption_model_manager",
    "get_caption_runner",
    "get_caption_store",
]
