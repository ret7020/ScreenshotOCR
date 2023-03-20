#!/usr/bin/env python3

import sys
from PyQt5 import QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QSizePolicy
#from PyQt5.QtWidgets import QGroupBox, QSpinBox, QCheckBox, QGridLayout
from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import QBuffer
import threading
import io
import pytesseract

from PIL import Image

from PyQt5.QtWidgets import QFileDialog
from Xlib import X, display, Xcursorfont


class OCR:
    def __init__(self):
        pass

    def recognize(self, image) -> str:
        return pytesseract.image_to_string(image, lang="rus")


class XSelect:
    def __init__(self, display):
        # X display
        self.d = display

        # Screen
        self.screen = self.d.screen()

        # Draw on the root window (desktop surface)
        self.window = self.screen.root

        # Create font cursor
        font = display.open_font('cursor')
        self.cursor = font.create_glyph_cursor(
            font,
            Xcursorfont.crosshair,
            Xcursorfont.crosshair+1,
            (65535, 65535, 65535),
            (0, 0, 0)
        )

        colormap = self.screen.default_colormap
        color = colormap.alloc_color(0, 0, 0)
        # Xor it because we'll draw with X.GXxor function
        xor_color = color.pixel ^ 0xffffff

        self.gc = self.window.create_gc(
            line_width=1,
            line_style=X.LineSolid,
            fill_style=X.FillOpaqueStippled,
            fill_rule=X.WindingRule,
            cap_style=X.CapButt,
            join_style=X.JoinMiter,
            foreground=xor_color,
            background=self.screen.black_pixel,
            function=X.GXxor,
            graphics_exposures=False,
            subwindow_mode=X.IncludeInferiors,
        )

    def get_mouse_selection(self):
        started = False
        start = dict(x=0, y=0)
        end = dict(x=0, y=0)
        last = None
        drawlimit = 10
        i = 0

        self.window.grab_pointer(
            self.d,
            X.PointerMotionMask | X.ButtonReleaseMask | X.ButtonPressMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            X.NONE,
            self.cursor,
            X.CurrentTime
        )

        self.window.grab_keyboard(self.d,
                                  X.GrabModeAsync,
                                  X.GrabModeAsync,
                                  X.CurrentTime
                                  )

        while True:
            e = self.d.next_event()

            # Window has been destroyed, quit
            if e.type == X.DestroyNotify:
                break

            # Mouse button press
            elif e.type == X.ButtonPress:
                # Left mouse button?
                if e.detail == 1:
                    start = dict(x=e.root_x, y=e.root_y)
                    started = True

                # Right mouse button?
                elif e.detail == 3:
                    return

            # Mouse button release
            elif e.type == X.ButtonRelease:
                end = dict(x=e.root_x, y=e.root_y)
                if last:
                    self.draw_rectangle(start, last)
                break

            # Mouse movement
            elif e.type == X.MotionNotify and started:
                i = i + 1
                if i % drawlimit != 0:
                    continue

                if last:
                    self.draw_rectangle(start, last)
                    last = None

                last = dict(x=e.root_x, y=e.root_y)
                self.draw_rectangle(start, last)

        self.d.ungrab_keyboard(X.CurrentTime)
        self.d.ungrab_pointer(X.CurrentTime)
        self.d.sync()

        coords = self.get_coords(start, end)
        if coords['width'] <= 1 or coords['height'] <= 1:
            return

        return [
            coords['start']['x'],
            coords['start']['y'],
            coords['width'],
            coords['height']
        ]

    def get_coords(self, start, end):
        safe_start = dict(x=0, y=0)
        safe_end = dict(x=0, y=0)

        if start['x'] > end['x']:
            safe_start['x'] = end['x']
            safe_end['x'] = start['x']
        else:
            safe_start['x'] = start['x']
            safe_end['x'] = end['x']

        if start['y'] > end['y']:
            safe_start['y'] = end['y']
            safe_end['y'] = start['y']
        else:
            safe_start['y'] = start['y']
            safe_end['y'] = end['y']

        return {
            'start': {
                'x': safe_start['x'],
                'y': safe_start['y'],
            },
            'end': {
                'x': safe_end['x'],
                'y': safe_end['y'],
            },
            'width': safe_end['x'] - safe_start['x'],
            'height': safe_end['y'] - safe_start['y'],
        }

    def draw_rectangle(self, start, end):
        coords = self.get_coords(start, end)
        self.window.rectangle(self.gc,
                              coords['start']['x'],
                              coords['start']['y'],
                              coords['end']['x'] - coords['start']['x'],
                              coords['end']['y'] - coords['start']['y']
                              )


class Screenshot(QWidget):
    def __init__(self, ocr):
        super(Screenshot, self).__init__()

        self.screenshotLabel = QLabel()
        self.screenshotLabel.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        self.screenshotLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.screenshotLabel.setMinimumSize(240, 160)

        # self.createOptionsGroupBox()
        self.createButtonsLayout()

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(self.screenshotLabel)
        # mainLayout.addWidget(self.optionsGroupBox)
        mainLayout.addLayout(self.buttonsLayout)
        self.setLayout(mainLayout)
        self.area = None
        self.ocr = ocr
        self.setWindowTitle("OCR on screenshot")
        self.resize(300, 200)

    def resizeEvent(self, event):
        scaledSize = self.originalPixmap.size()
        scaledSize.scale(
            self.screenshotLabel.size(),
            QtCore.Qt.KeepAspectRatio
        )
        if not self.screenshotLabel.pixmap() \
                or scaledSize != self.screenshotLabel.pixmap().size():
            self.updateScreenshotLabel()

    def selectArea(self):
        self.hide()

        xs = XSelect(display.Display())
        self.area = xs.get_mouse_selection()

        if self.area:
            xo, yo, x, y = self.area
            self.shootScreen()
        else:
            self.shootScreen()

        self.show()

    def shootScreen(self):

        # Garbage collect any existing image first.
        self.originalPixmap = None
        screen = QApplication.primaryScreen()
        self.originalPixmap = screen.grabWindow(
            QApplication.desktop().winId()
        )
        if self.area is not None:
            qi = self.originalPixmap.toImage()
            qi = qi.copy(
                int(self.area[0]),
                int(self.area[1]),
                int(self.area[2]),
                int(self.area[3])
            )
            self.originalPixmap = None
            self.originalPixmap = QPixmap.fromImage(qi)

        self.updateScreenshotLabel()
        pixmap = self.originalPixmap.scaled(
            self.screenshotLabel.size(), QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        pixmap.save(buffer, "PNG")
        pil_im = Image.open(io.BytesIO(buffer.data()))

        threading.Thread(target=lambda: print(self.ocr.recognize(pil_im))).start()

    def copy(self):
        print("Copy")
        

    def createButtonsLayout(self):
        self.quitScreenshotButton = self.createButton(
            "Quit",
            self.close
        )
        
        self.copyTextButton = self.createButton(
            "Copy text",
            self.copy
        )

        self.buttonsLayout = QHBoxLayout()
        self.buttonsLayout.addStretch()

        self.buttonsLayout.addWidget(self.quitScreenshotButton)
        self.buttonsLayout.addWidget(self.copyTextButton)

    def infoLayout(self):
        self.textLabel = QLabel("Decoding...")
        #optionsGroupBoxLayout = QGridLayout()

    def createButton(self, text, member):
        button = QPushButton(text)
        button.clicked.connect(member)
        return button

    def updateScreenshotLabel(self):
        pixmap = self.originalPixmap.scaled(
            self.screenshotLabel.size(), QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self.screenshotLabel.setPixmap(pixmap)
        # print(pixmap)


if __name__ == '__main__':
    ocr = OCR()
    app = QApplication(sys.argv)
    screenshot = Screenshot(ocr)
    screenshot.selectArea()
    sys.exit(app.exec_())
