"""paddleocr bat IR optim bang switch_ir_optim(True) -> phai bi ep thanh False (tranh SIGILL tren CI)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H


class Cfg:
    def __init__(self):
        self.ir = None

    def switch_ir_optim(self, x=True):
        self.ir = x


assert H._force_paddle_no_ir(Cfg) is True
c = Cfg(); c.switch_ir_optim(True)
assert c.ir is False
H._force_paddle_no_ir(Cfg)                      # goi 2 lan khong boc 2 lop
c = Cfg(); c.switch_ir_optim(True); assert c.ir is False
assert H._force_paddle_no_ir(object()) is False  # khong co switch_ir_optim: khong lam vo
print("OK")
