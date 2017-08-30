from PyQt5.QtWidgets import (QDockWidget,
                             QPushButton,
                             )
from wonambi.scroll_data import MainWindow

from .paths import (gui_file,
                    GUI_PATH,
                    )


def test_scroll_data(qtbot):

    w = MainWindow()
    qtbot.addWidget(w)

    w.grab().save(str(GUI_PATH / 'open_01_start.png'))

    w.info.idx_filename.setStyleSheet("background-color: red;")
    w.grab().save(str(GUI_PATH / 'open_02_open_dataset.png'))
    w.info.idx_filename.setStyleSheet("")

    w.info.open_dataset(str(gui_file))

    new_button = w.channels.layout().itemAt(0).itemAt(0).widget()
    new_button.setStyleSheet("background-color: red;")
    w.grab().save(str(GUI_PATH / 'open_03_loaded.png'))
    new_button.setStyleSheet("")

    channel_make_group(w, png=True)

    # this shows selected channels and the apply button
    button_apply = find_pushbutton(w.channels, 'Apply')
    button_apply.setStyleSheet("background-color: red;")
    w.grab().save(str(GUI_PATH / 'open_05_chan.png'))
    button_apply.setStyleSheet("")

    button_apply.click()
    w.grab().save(str(GUI_PATH / 'open_06_traces.png'))


def channel_make_group(w, png=False):
    dockwidget_chan = w.findChild(QDockWidget, 'Channels')
    dockwidget_chan.raise_()

    w.channels.new_group(test_name='scalp')

    if png:
        w.grab().save(str(GUI_PATH / 'open_04_channel_new.png'))

    chan_tab_i = w.channels.tabs.currentIndex()
    channelsgroup = w.channels.tabs.widget(chan_tab_i)
    channelsgroup.idx_l0.item(0).setSelected(True)
    channelsgroup.idx_l0.item(1).setSelected(True)
    channelsgroup.idx_l0.item(2).setSelected(True)


def find_pushbutton(w, text):
    # workaround, because it doesn't find 'Apply'
    all_child = w.findChildren(QPushButton)
    buttons = [ch for ch in all_child if ch.text() == text]
    if buttons:
        return buttons[0]
