"""Module with helper functions for plotting

"""
from numpy import array, linspace, c_, r_, zeros, arange, ones
from PyQt4.Qt import QImage, QPainter, QBuffer, QIODevice, QByteArray
from PyQt4.QtGui import QApplication
from pyqtgraph import ColorMap


coolwarm = array([[59, 76, 192],
                  [68, 90, 204],
                  [77, 104, 215],
                  [87, 117, 225],
                  [98, 130, 234],
                  [108, 142, 241],
                  [119, 154, 247],
                  [130, 165, 251],
                  [141, 176, 254],
                  [152, 185, 255],
                  [163, 194, 255],
                  [174, 201, 253],
                  [184, 208, 249],
                  [194, 213, 244],
                  [204, 217, 238],
                  [213, 219, 230],
                  [221, 221, 221],
                  [229, 216, 209],
                  [236, 211, 197],
                  [241, 204, 185],
                  [245, 196, 173],
                  [247, 187, 160],
                  [247, 177, 148],
                  [247, 166, 135],
                  [244, 154, 123],
                  [241, 141, 111],
                  [236, 127, 99],
                  [229, 112, 88],
                  [222, 96, 77],
                  [213, 80, 66],
                  [203, 62, 56],
                  [192, 40, 47],
                  [180, 4, 38]])


class Colormap(ColorMap):
    """Create colormap using predefined color scheme.

    Parameters
    ----------
    name : str
        name of the colormap
    limits : tuple of two floats
        min and max values of the colormap

    Notes
    -----
    bwr : blue-white-red diverging
    cool : blue-dominanted sequential
    coolwarm : continuous blue-white-red diverging
       http://www.sandia.gov/~kmorel/documents/ColorMaps/
    jet : old-school Matlab
    hot : red-dominated sequential

    Examples
    --------
    >>> cmap = Colormap('jet')
    >>> from pyqtgraph import GradientWidget
    >>> gradient = GradientWidget()
    >>> gradient.item.setColorMap(cmap)
    >>> gradient.show()
    """
    def __init__(self, name='coolwarm', limits=(0, 1)):
        if name == 'bwr':
            pos = linspace(limits[0], limits[1], 3)
            r = r_[0, 255, 255]
            g = r_[0, 255, 0]
            b = r_[255, 255, 0]
            color = array(c_[r, g, b])

        elif name == 'cool':
            pos = linspace(limits[0], limits[1], 2)
            r = r_[0, 255]
            g = r_[255, 0]
            b = r_[255, 255]
            color = array(c_[r, g, b])

        elif name == 'coolwarm':
            pos = linspace(limits[0], limits[1], coolwarm.shape[0])
            color = coolwarm

        elif name == 'jet':
            pos = linspace(limits[0], limits[1], 66)
            r = r_[zeros(24), arange(0, 255, 15), 255 * ones(17), arange(255, 135, -15)]
            g = r_[zeros(7), arange(0, 255, 15), 255 * ones(17), arange(255, 0, -15), zeros(8)]
            b = r_[arange( 150, 255, 15),  255 * ones(17), arange(255, 0, -15), zeros(25)]
            color = array(c_[r, g, b])

        elif name == 'hot':
            pos = linspace(limits[0], limits[1], 4)
            r = r_[10, 255, 255, 255]
            g = r_[0, 0, 255, 255]
            b = r_[0, 0, 0, 255]
            color = array(c_[r, g, b])

        # add alpha and it's necessary to pass it as int
        color = c_[color, 255 * ones((color.shape[0], 1))].astype(int)
        super().__init__(pos, color)


class Viz():

    @property
    def size(self):
        return self._widget.size().width(), self._widget.size().height()

    @size.setter
    def size(self, newsize):
        self._widget.resize(*newsize)

    def _repr_png_(self):
        """This is used by ipython to plot inline.
        """
        self._widget.hide()
        QApplication.processEvents()

        try:
            self.image = QImage(self._widget.viewRect().size().toSize(),
                                QImage.Format_RGB32)
        except AttributeError:
            self._widget.updateGL()
            self.image = self._widget.grabFrameBuffer()

        painter = QPainter(self.image)
        self._widget.render(painter)

        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.ReadWrite)
        self.image.save(buffer, 'PNG')
        buffer.close()

        return bytes(byte_array)

    def save(self, png_file):
        """Save png to disk.

        Parameters
        ----------
        png_file : path to file
            file to write to

        Notes
        -----
        It relies on _repr_png_, so fix issues there.
        """
        with open(png_file, 'wb') as f:
            f.write(self._repr_png_())