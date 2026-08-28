"""
蜘蛛侠桌宠 (PySide6) —— 多帧动画版

素材(由两段视频抽帧抠图生成,见 build_frames.py):
  assets/idle/###.png   待机循环(米色视频)
  assets/web/###.png    招牌【吐丝】动作(绿幕视频)
  assets/meta.json      画布尺寸 / 脚部锚点

特点:
- 透明无边框、始终置顶的小窗口
- 真·多帧动画:待机自带呼吸/摆动;走路复用待机帧 + 代码驱动的踏步弹跳与前倾
- 招牌动作【吐丝】:播放吐丝动作帧,并从举起的手射出会生长→粘住→回弹的蛛丝
- 自动 AI:屏幕底部随机走动/停留,碰边掉头转身,偶尔自发吐丝
- 交互:
    * 拖动:按住左键拖到任意位置(松手落回地面,拖动时像被拎着一样晃)
    * 单击:吐丝
    * 右键:菜单(吐丝 / 切换朝向 / 回到屏幕中间 / 退出)

运行: python3 pet.py     退出: 右键 -> 退出
"""
import glob
import json
import math
import os
import random
import sys

from PySide6.QtCore import Qt, QTimer, QPoint, QPointF
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QMenu, QWidget

def _base_dir():
    # 运行为 PyInstaller 打包程序时,资源解压/存放在 sys._MEIPASS;
    # 普通脚本运行时用源码所在目录。
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE = _base_dir()
ASSETS = os.path.join(BASE, "assets")

# 窗口在画布四周留出的透明边距(供旋转摆动 + 蛛丝伸展)
MARGIN_SIDE = 90
MARGIN_TOP = 90
MARGIN_BOT = 8

# 播放速度(每渲染帧推进的动画帧数)
IDLE_SPEED = 0.5          # 待机/走路 ≈15fps,舒缓
WEB_STEP = 2              # 吐丝动作抽帧步长(越大越快)
FPS_MS = 33               # 渲染/逻辑帧间隔(~30fps)
WALK_SPEED = 2            # 走路每帧位移(像素)

# 吐丝:手部锚点(占画布比例)与方向(朝右上)
WEB_HAND = (0.86, 0.43)
WEB_DIR = (1.0, -0.62)
WEB_LEN = 92


def load_frames(subdir):
    files = sorted(glob.glob(os.path.join(ASSETS, subdir, "*.png")))
    return [QPixmap(f) for f in files]


class Pet(QWidget):
    def __init__(self):
        super().__init__()
        # 不用 Qt.Tool —— 在 macOS 上 Tool 窗口只有 App 处于前台时才显示。
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        try:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        except AttributeError:
            pass

        # ---- 载入素材 ----
        meta_path = os.path.join(ASSETS, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            self.cw, self.ch = meta["canvas"]
            self.feet_y = meta["feet_y"]
        else:
            self.cw, self.ch, self.feet_y = 183, 202, 190

        self.idle_frames = load_frames("idle")
        self.web_frames = load_frames("web")
        if not self.idle_frames:
            print("[错误] 未找到 assets/idle 帧,请先运行 build_frames.py", file=sys.stderr)
            sys.exit(1)
        if not self.web_frames:
            self.web_frames = self.idle_frames

        # 朝左的镜像缓存
        self._flip_cache = {}

        # 吐丝动作的乒乓播放序列(前进再后退,回到近初始姿势,便于衔接待机)
        n = len(self.web_frames)
        self.web_seq = (list(range(0, n, WEB_STEP))
                        + list(range(n - 1, -1, -WEB_STEP)))

        # 窗口 = 画布 + 边距
        self.resize(self.cw + 2 * MARGIN_SIDE, self.ch + MARGIN_TOP + MARGIN_BOT)

        # ---- 状态 ----
        self.facing_right = True
        self.phase = 0.0
        self.behavior = "idle"        # idle / walk
        self.walk_dir = 1
        self.behavior_ticks = 0

        self.idle_i = 0.0             # 待机/走路动画游标(浮点,乒乓循环)
        self.web_pos = None           # 吐丝进行中: web_seq 的下标;None 表示未吐丝

        self.dragging = False
        self.drag_offset = QPoint()
        self._moved = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(FPS_MS)

        self._move_to_ground_random()
        self._pick_new_behavior()

        g = self._screen_geo()
        print(f"[桌宠] 可用区域 {g.width()}x{g.height()} @({g.left()},{g.top()}) | "
              f"窗口 {self.width()}x{self.height()} @({self.x()},{self.y()}) | "
              f"idle={len(self.idle_frames)}帧 web={len(self.web_frames)}帧",
              file=sys.stderr)

    # ---------- 屏幕 / 位置 ----------
    def _screen_geo(self):
        return QApplication.primaryScreen().availableGeometry()

    def _feet_in_window(self):
        return MARGIN_TOP + self.feet_y

    def _ground_y(self):
        # 让脚部正好落在屏幕可用区底部
        return self._screen_geo().bottom() - self._feet_in_window() + 1

    def _move_to_ground_random(self):
        g = self._screen_geo()
        x = random.randint(g.left(), max(g.left(), g.right() - self.width()))
        self.move(x, self._ground_y())

    # ---------- AI ----------
    def _pick_new_behavior(self):
        if random.random() < 0.5:
            self.behavior = "idle"
            self.behavior_ticks = random.randint(40, 110)
        else:
            self.behavior = "walk"
            self.walk_dir = random.choice([-1, 1])
            self.facing_right = self.walk_dir > 0
            self.behavior_ticks = random.randint(70, 170)

    def _tick(self):
        self.phase += 0.18

        # 待机/走路动画游标推进(乒乓循环)
        self.idle_i += IDLE_SPEED

        # 吐丝动作推进
        if self.web_pos is not None:
            self.web_pos += 1
            if self.web_pos >= len(self.web_seq):
                self.web_pos = None

        if not self.dragging:
            self.behavior_ticks -= 1
            if self.behavior == "walk" and self.web_pos is None:
                g = self._screen_geo()
                new_x = self.x() + self.walk_dir * WALK_SPEED
                if new_x <= g.left():
                    new_x = g.left(); self.walk_dir = 1; self.facing_right = True
                elif new_x >= g.right() - self.width():
                    new_x = g.right() - self.width(); self.walk_dir = -1; self.facing_right = False
                self.move(new_x, self._ground_y())
            if self.behavior_ticks <= 0:
                self._pick_new_behavior()

            # 待机时偶尔自发吐丝
            if (self.web_pos is None and self.behavior == "idle"
                    and random.random() < 0.004):
                self._shoot_web()

        self.update()

    def _shoot_web(self):
        if self.web_pos is None:
            self.web_pos = 0

    # ---------- 帧选择 ----------
    def _pingpong(self, i, n):
        if n <= 1:
            return 0
        period = 2 * n - 2
        k = int(i) % period
        return k if k < n else period - k

    def _current_pixmap(self):
        if self.web_pos is not None:
            idx = self.web_seq[min(self.web_pos, len(self.web_seq) - 1)]
            pm = self.web_frames[idx]
        else:
            idx = self._pingpong(self.idle_i, len(self.idle_frames))
            pm = self.idle_frames[idx]
        if not self.facing_right:
            key = id(pm)
            flipped = self._flip_cache.get(key)
            if flipped is None:
                flipped = pm.transformed(QTransform().scale(-1, 1),
                                         Qt.SmoothTransformation)
                self._flip_cache[key] = flipped
            return flipped
        return pm

    # ---------- 绘制 ----------
    def _motion(self):
        """代码驱动的整体位移/旋转(绕脚部)。帧本身已有肢体动画,
        故待机/吐丝几乎不叠加,走路叠加踏步弹跳与前倾以体现移动感。"""
        if self.dragging:
            return 0.0, math.sin(self.phase * 1.4) * 12.0
        if self.web_pos is not None:
            return 0.0, 0.0
        if self.behavior == "walk":
            step = self.phase * 2.2
            bob = -abs(math.sin(step)) * 7.0
            rock = math.sin(step) * 5.0
            lean = 3.0 if self.facing_right else -3.0
            return bob, rock + lean
        # idle: 让真·帧动画主导,仅极轻微浮动
        return math.sin(self.phase * 0.8) * 1.5, 0.0

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        bob, angle = self._motion()
        pivot_x = MARGIN_SIDE + self.cw / 2.0
        pivot_y = self._feet_in_window()

        t = QTransform()
        t.translate(0, bob)
        t.translate(pivot_x, pivot_y)
        t.rotate(angle)
        t.translate(-pivot_x, -pivot_y)
        p.setWorldTransform(t)

        p.drawPixmap(MARGIN_SIDE, MARGIN_TOP, self._current_pixmap())

        if self.web_pos is not None:
            self._draw_web(p)

        p.end()

    def _hand_anchor(self):
        """举手锚点(窗口坐标)+ 蛛丝单位方向。"""
        fx, fy = WEB_HAND
        if self.facing_right:
            hx = MARGIN_SIDE + fx * self.cw
            ux = WEB_DIR[0]
        else:
            hx = MARGIN_SIDE + (1 - fx) * self.cw
            ux = -WEB_DIR[0]
        hy = MARGIN_TOP + fy * self.ch
        return hx, hy, ux, WEB_DIR[1]

    def _draw_web(self, p):
        ox, oy, dx, dy = self._hand_anchor()
        n = math.hypot(dx, dy)
        ux, uy = dx / n, dy / n
        pxn, pyn = -uy, ux

        t = self.web_pos / max(1, len(self.web_seq) - 1)   # 0..1
        if t < 0.40:
            grow = t / 0.40
            alpha = 255
        elif t < 0.68:
            grow = 1.0
            alpha = 255
        else:
            grow = 1.0 - (t - 0.68) / 0.32 * 0.4
            alpha = int(255 * (1 - (t - 0.68) / 0.32))
        alpha = max(0, min(255, alpha))
        length = WEB_LEN * grow
        tipx, tipy = ox + ux * length, oy + uy * length

        white = QColor(255, 255, 255, alpha)
        blue = QColor(205, 225, 255, alpha)

        for off, col, w in ((-3, blue, 2), (0, white, 3), (3, blue, 2)):
            p.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            sx, sy = ox + pxn * off, oy + pyn * off
            pts = [QPointF(sx, sy)]
            seg = 5
            for i in range(1, seg + 1):
                f = i / seg
                jitter = (2.5 if i % 2 else -2.5) * (1 - f)
                x = sx + (tipx - sx) * f + pxn * jitter
                y = sy + (tipy - sy) * f + pyn * jitter
                pts.append(QPointF(x, y))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])

        if t >= 0.32:
            r = 9 * min(1.0, (t - 0.32) / 0.2)
            p.setPen(QPen(white, 2, Qt.SolidLine, Qt.RoundCap))
            for k in range(6):
                a = math.pi * 2 * k / 6
                p.drawLine(QPointF(tipx, tipy),
                           QPointF(tipx + math.cos(a) * r, tipy + math.sin(a) * r))
            p.setPen(QPen(blue, 1))
            for rr in (r * 0.5, r):
                p.drawEllipse(QPointF(tipx, tipy), rr, rr)

    # ---------- 鼠标交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self._moved = False
            self.drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.dragging and (e.buttons() & Qt.LeftButton):
            self._moved = True
            self.move(e.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.move(self.x(), self._ground_y())
            if not self._moved:
                self._shoot_web()

    def contextMenuEvent(self, e):
        menu = QMenu()
        a_web = QAction("吐丝", self); a_web.triggered.connect(self._shoot_web)
        a_flip = QAction("切换朝向", self); a_flip.triggered.connect(self._flip)
        a_center = QAction("回到屏幕中间", self); a_center.triggered.connect(self._center)
        a_quit = QAction("退出", self); a_quit.triggered.connect(QApplication.quit)
        menu.addAction(a_web); menu.addAction(a_flip); menu.addAction(a_center)
        menu.addSeparator(); menu.addAction(a_quit)
        menu.exec(e.globalPos())

    def _flip(self):
        self.facing_right = not self.facing_right
        self.update()

    def _center(self):
        g = self._screen_geo()
        self.move(g.center().x() - self.width() // 2, self._ground_y())


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    pet = Pet()
    pet.show()
    pet.raise_()
    pet.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
