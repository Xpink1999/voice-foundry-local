import importlib

def resolve(spec):
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)

def build_engines(config):
    return {name: resolve(item["adapter"])(dict(config, engine_config=item)) for name, item in config["engines"].items()}
