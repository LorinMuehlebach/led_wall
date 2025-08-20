from .base_effect import BaseEffect

#bit ugly to import all files
import importlib
from os.path import dirname, basename, isfile, join
import glob
modules = glob.glob(join(dirname(__file__), "*.py"))
__all__ = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py') and not f.endswith('base_effect.py') and not f.endswith('effect_manager.py')]


def get_effects():
    for module in __all__:
        importlib.import_module(f".{module}", package=__name__)
    return [effect for effect in BaseEffect.__subclasses__()]

def get_effect_class(name) -> type[BaseEffect] | None:
    effects = get_effects()
    for effect in effects:
        if effect.NAME == name:
            return effect
    return None