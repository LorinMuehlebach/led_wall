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
    
    #sort the effects by name
    all_effects = [effect for effect in BaseEffect.__subclasses__()]
    sorted_effects = sorted(all_effects, key=lambda e: e.NAME)
    #move single_color to the front
    for i, effect in enumerate(sorted_effects):
        if effect.__name__ == "SingleColor":
            sorted_effects.insert(0, sorted_effects.pop(i))
            break
    return sorted_effects

def get_effect_class(name) -> type[BaseEffect] | None:
    effects = get_effects()
    for effect in effects:
        if effect.__name__ == name:
            return effect
    return None