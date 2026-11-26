"""X11 area picker and recording overlay."""
import time

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


TIMER_WIDTH = 132
TIMER_HEIGHT = 34


def timer_position(width, height, region):
    x, y, w, h = region
    bands = [(0, 0, width, y), (0, y + h, width, height - y - h),
             (0, y, x, h), (x + w, y, width - x - w, h)]
    for left, top, wide, high in bands:
        if wide >= TIMER_WIDTH and high >= TIMER_HEIGHT:
            tx = min(max(x + (w - TIMER_WIDTH) // 2, left), left + wide - TIMER_WIDTH)
            ty = min(max(y + (h - TIMER_HEIGHT) // 2, top), top + high - TIMER_HEIGHT)
            if top == 0 and high == y:
                ty = max(top, top + high - TIMER_HEIGHT - 8)
            elif top == y + h:
                ty = min(top + 8, top + high - TIMER_HEIGHT)
            return tx, ty
    return None


def valid_region(width, height, region):
    x, y, w, h = region
    return (min(x, y) >= 0 and min(w, h) >= 2 and x + w <= width
            and y + h <= height and timer_position(width, height, region) is not None)


def label(cr, text, x, baseline, size, color=(1, 1, 1)):
    cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size)
    cr.set_source_rgb(*color)
    cr.move_to(x, baseline)
    cr.show_text(text)


class Overlay:
    def __init__(self, title, width, height, alpha=False):
        self.width, self.height = width, height
        self.window = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.window.set_title(title)
        self.window.set_app_paintable(True)
        self.window.set_keep_above(True)
        self.window.set_accept_focus(False)
        self.window.set_default_size(width, height)
        self.window.move(0, 0)
        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        self.composited = alpha and screen.is_composited() and visual is not None
        if self.composited:
            self.window.set_visual(visual)
        self.window.connect("draw", self.draw)

    def close(self):
        self.window.destroy()
        Gdk.Display.get_default().sync()


class Picker(Overlay):
    def __init__(self, width, height, region):
        super().__init__("Crop Recording — Select area", width, height)
        screen = self.window.get_screen()
        self.desktop = Gdk.pixbuf_get_from_window(screen.get_root_window(), 0, 0, width, height)
        if self.desktop is None:
            self.close()
            raise RuntimeError("Could not capture the desktop preview.")
        display = screen.get_display()
        pointer = display.get_default_seat().get_pointer()
        _, px, py = pointer.get_position()
        self.monitor = display.get_monitor_at_point(px, py).get_geometry()
        self.region = region
        self.anchor = None
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK)
        self.window.connect("button-press-event", self.press)
        self.window.connect("motion-notify-event", self.motion)
        self.window.connect("button-release-event", self.release)
        self.window.show_all()
        self.window.get_window().set_cursor(Gdk.Cursor.new_from_name(display, "crosshair"))

    @property
    def ready(self):
        return (self.anchor is None and self.region is not None
                and valid_region(self.width, self.height, self.region))

    def press(self, _window, event):
        if event.button == 1:
            self.anchor = int(event.x), int(event.y)
            self.motion(_window, event)

    def motion(self, _window, event):
        if self.anchor is not None:
            x, y = self.anchor
            end_x = min(max(0, int(event.x)), self.width)
            end_y = min(max(0, int(event.y)), self.height)
            self.region = min(x, end_x), min(y, end_y), abs(x - end_x), abs(y - end_y)
            self.window.queue_draw()

    def release(self, window, event):
        if event.button == 1 and self.anchor is not None:
            self.motion(window, event)
            self.anchor = None
            self.window.queue_draw()

    def draw(self, _window, cr):
        Gdk.cairo_set_source_pixbuf(cr, self.desktop, 0, 0)
        cr.paint()
        cr.rectangle(0, 0, self.width, self.height)
        if self.region:
            cr.rectangle(*self.region)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.set_source_rgba(0.02, 0.03, 0.06, 0.65)
        cr.fill()
        if self.region and min(self.region[2:]) > 0:
            x, y, w, h = self.region
            cr.rectangle(x, y, w, h)
            cr.set_line_width(2)
            cr.set_source_rgb(0.29, 0.88, 0.77)
            cr.stroke()

        if self.ready:
            heading = f"Area {self.region[2]} × {self.region[3]} pixels"
            detail = "Ctrl+Alt+A to start   ·   Drag to adjust   ·   Esc to cancel"
        elif self.region and self.anchor is None and min(self.region[2:]) >= 2:
            heading = "Leave room for the timer"
            detail = "Select a smaller area to keep the timer visible."
        else:
            heading = "Select a recording area"
            detail = "Drag to select   ·   Ctrl+Alt+A to start   ·   Esc to cancel"
        monitor = self.monitor
        panel_width = min(472, monitor.width)
        px = monitor.x + (monitor.width - panel_width) // 2
        py = monitor.y + min(24, max(0, monitor.height - 70))
        cr.set_source_rgb(0.07, 0.09, 0.13)
        cr.rectangle(px, py, panel_width, 70)
        cr.fill()
        label(cr, heading, px + 16, py + 27, 17)
        label(cr, detail, px + 16, py + 52, 14, (0.82, 0.86, 0.91))
        return True


class RecordingOverlay(Overlay):
    def __init__(self, width, height, region):
        super().__init__("Crop Recording — Recording", width, height, alpha=True)
        self.timer_x, self.timer_y = timer_position(width, height, region)
        self.started = time.monotonic()
        self.elapsed = -1
        self.window.realize()
        window = self.window.get_window()
        timer = cairo.RectangleInt(self.timer_x, self.timer_y, TIMER_WIDTH, TIMER_HEIGHT)
        if self.composited:
            visible = cairo.Region(cairo.RectangleInt(0, 0, width, height))
        else:
            # A stipple keeps the desktop visible on X11 without a compositor.
            visible = cairo.Region([cairo.RectangleInt(0, y, width, 1)
                                    for y in range(0, height, 2)])
            visible.union(cairo.Region(timer))
        visible.subtract(cairo.Region(cairo.RectangleInt(*region)))
        window.shape_combine_region(visible, 0, 0)
        window.input_shape_combine_region(cairo.Region(), 0, 0)
        self.window.show_all()
        window.get_display().sync()

    def update(self):
        elapsed = int(time.monotonic() - self.started)
        if elapsed != self.elapsed:
            self.elapsed = elapsed
            self.window.queue_draw_area(self.timer_x, self.timer_y, TIMER_WIDTH, TIMER_HEIGHT)
            self.window.get_window().raise_()

    def draw(self, _window, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0.02, 0.03, 0.06, 0.62 if self.composited else 1)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        x, y = self.timer_x, self.timer_y
        cr.set_source_rgb(0.07, 0.09, 0.13)
        cr.rectangle(x, y, TIMER_WIDTH, TIMER_HEIGHT)
        cr.fill()
        cr.set_source_rgb(1, 0.34, 0.37)
        cr.arc(x + 15, y + 17, 4, 0, 6.284)
        cr.fill()
        minutes, seconds = divmod(max(0, self.elapsed), 60)
        label(cr, f"REC   {minutes:02d}:{seconds:02d}", x + 26, y + 22, 14)
        return True
