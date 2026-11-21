"""Compare a remote VPT .weights file's tensor names/shapes to our model, reading only the zip index (HTTP range)."""
import io, pickle, sys, urllib.request, zipfile, json
import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpt_arena.vpt import WEIGHT_URLS, WEIGHT_ARCH, build_policy, build_idm

class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url = url; self.pos = 0
        r = urllib.request.urlopen(urllib.request.Request(url, method='HEAD')); self.size = int(r.headers['Content-Length'])
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0: return 0
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={self.pos}-{self.pos+n-1}'})
        data = urllib.request.urlopen(req).read(); b[:len(data)] = data; self.pos += len(data); return len(data)

class Shape(pickle.Unpickler):
    def find_class(self, m, n):
        if (m, n) == ('torch._utils', '_rebuild_tensor_v2'):
            return lambda storage, off, size, *a: tuple(size)
        if (m, n) == ('collections', 'OrderedDict'):
            import collections; return collections.OrderedDict
        if m == 'torch' and n.endswith('Storage'):
            return n
        raise pickle.UnpicklingError(f'blocked {m}.{n}')
    def persistent_load(self, pid): return None

for name in sys.argv[1:]:
    zf = zipfile.ZipFile(io.BufferedReader(RangeFile(WEIGHT_URLS[name]), 1 << 16))
    pk = [n for n in zf.namelist() if n.endswith('data.pkl')][0]
    remote = Shape(io.BytesIO(zf.read(pk))).load()
    arch = WEIGHT_ARCH[name]
    model = build_idm(arch) if arch.startswith('idm') else build_policy(arch)
    local = {k: tuple(v.shape) for k, v in model.state_dict().items()}
    ours = {k for k in local if 'diff_obs_process' in k}
    missing = sorted(set(local) - set(remote) - ours); extra = sorted(set(remote) - set(local))
    bad = [k for k in remote if k in local and tuple(remote[k]) != local[k]]
    print(json.dumps(dict(weights=name, remote_tensors=len(remote), model_tensors=len(local) - len(ours),
                          missing=missing[:5], unexpected=extra[:5], shape_mismatch=bad[:5])))
    del model
