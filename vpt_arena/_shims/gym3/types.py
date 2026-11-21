"""Minimal stand-in for gym3.types, covering only what VPT's lib/ uses.

gym3 itself pulls in rendering deps (glfw, moderngl, imageio) the model code
never needs.
"""


class ValType:
    pass


class Discrete(ValType):
    def __init__(self, n, dtype_name="int64"):
        self.n = n
        self.dtype_name = dtype_name


class Real(ValType):
    def __init__(self, dtype_name="float32"):
        self.dtype_name = dtype_name


class TensorType(ValType):
    def __init__(self, eltype, shape):
        self.eltype = eltype
        self.shape = tuple(shape)

    @property
    def size(self):
        n = 1
        for s in self.shape:
            n *= s
        return n


class DictType(ValType):
    def __init__(self, **spaces):
        self._spaces = dict(spaces)

    def __getitem__(self, k):
        return self._spaces[k]

    def __contains__(self, k):
        return k in self._spaces

    def __len__(self):
        return len(self._spaces)

    def __iter__(self):
        return iter(self._spaces)

    def keys(self):
        return self._spaces.keys()

    def values(self):
        return self._spaces.values()

    def items(self):
        return self._spaces.items()
