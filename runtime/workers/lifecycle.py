import multiprocessing
import importlib
import re

from runtime.workers.process_worker import process_entrypoint

_FACTORIES = {}


def register_composition_factory(name, factory):
    if not name or not callable(factory):
        raise ValueError("Invalid composition factory")
    _FACTORIES[name] = factory


def get_composition_factory(name):
    if name in _FACTORIES:
        return _FACTORIES[name]
    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_.]{0,190}:[A-Za-z_][A-Za-z0-9_]{0,63}", name
    ):
        raise ValueError("Unknown composition reference")
    module_name, attribute = name.split(":", 1)
    factory = getattr(importlib.import_module(module_name), attribute, None)
    if not callable(factory):
        raise ValueError("Unknown composition reference")
    return factory


def start_process(configuration, composition_name):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=1)
    process = context.Process(
        target=process_entrypoint,
        args=(configuration, composition_name, queue),
        daemon=False,
    )
    process.start()
    return process, queue
