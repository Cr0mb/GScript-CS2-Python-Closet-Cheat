from __future__ import annotations
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
from .offset_manager import get_offsets

class Offsets:

    def __init__(self, *, force_update: bool=False):
        offsets, _ = get_offsets(force_update=force_update)
        self._ns = offsets
        self.__dict__.update(offsets.__dict__)
