"""Module to plot all the elements in 3d space.

"""
from logging import getLogger
lg = getLogger('phypno')

from functools import partial
from itertools import chain
from multiprocessing import Pool
from os import remove
from os.path import join, splitext
from subprocess import call
from tempfile import mkdtemp

from numpy import (asarray, count_nonzero, dot, empty, isnan, max, mean, min,
                   NaN, ones)
from numpy.linalg import norm
from visvis import Mesh, gca, figure, solidSphere, CM_JET, screenshot


CHAN_COLOR = (20 / 255., 20 / 255., 20 / 255., 1)
SKIN_COLOR = (239 / 255., 208 / 255., 207 / 255., 0.5)

IMAGE = 'image%09d.jpg'


class Viz3:
    """The 3d visualization, ordinarily it should hold a surface and electrodes

    Attributes
    ----------
    xyz2surf : ndarray
        nVertices X nChan matrix, that explains how channel activity should be
        plotted onto the vertices

    _fig : instance of Figure
        current figure
    _ax : instance of Axes
        current axes
    _surf : instance of phypno.attr.anat.Surf
        surface to be plotted
    _h_surf : instance of visvis.wobjects.polygonalModeling.Mesh
        mesh with the brain surface
    _h_chan : list of visvis.wobjects.polygonalModeling.OrientableMesh
        list of objects used to represent channels
    """
    def __init__(self):
        self.xyz2surf = None

        self._fig = figure()
        self._ax = gca()
        self._ax.wobjects[0].Destroy()  # get rid of axises

        self._surf = None
        self._h_surf = None
        self._h_chan = []

    def add_surf(self, surf, color=SKIN_COLOR, xyz=None, values=None,
                 limits=None, colormap=CM_JET):
        """Add surfaces to the visualization.

        Parameters
        ----------
        surf : instance of phypno.attr.anat.Surf
            surface to be plotted
        color : tuple, optional
            4-element tuple, representing RGB and alpha, between 0 and 1
        xyz : ndarray, optional
            nChan X 3 matrix of the xyz-position of the channels
        values : ndarray, optional
            vector with values for each channel
        limits : tuple of 2 floats, optional
            min and max values to normalize the color
        colormap : ndarray, optional
            matrix for the color coding (such as CM_JET, CM_HOT, ...)

        Notes
        -----
        'color' vs 'xyz' and 'values' are mutally exclusive. You need to
        specify 'xyz' and 'values' if you use those.

        If you specify 'values', then you'll need a matrix called 'xyz2surf'
        that converts from the channel values to the electrodes.
        It takes a few seconds to compute but once it's done, plotting is
        really fast.
        You can pre-compute it (using arbitrary values) and pass it as
        attribute to this class.
        """
        if values is not None and limits is None:
            limits = (min(values), max(values))

        m = Mesh(self._ax, vertices=surf.vert, faces=surf.tri)

        if values is not None:
            if self.xyz2surf is None:
                lg.info('Computing transformation, it will take a while')
                self.xyz2surf = calc_xyz2surf(self._surf, xyz)

            m.SetValues(dot(self.xyz2surf, values))
            m.clim = limits
        else:
            m.faceColor = color
        m.colormap = colormap

        self._surf = surf
        self._h_surf = m
        self.center_surf()

    def add_chan(self, chan, color=(0, 0, 0, 1), values=None, limits=None,
                 colormap=CM_JET):
        """
        Parameters
        ----------
        chan : instance of phypno.attr.Channels
            channels to plot.
        color : tuple, optional
            4-element tuple, representing RGB and alpha, between 0 and 1
        values : ndarray, optional
            vector with values for each electrode
        limits : tuple of 2 floats, optional
            min and max values to normalize the color
        colormap : ndarray, optional
            matrix for the color coding (such as CM_JET, CM_HOT, ...)
        """
        # larger if colors are meaningful
        if values is not None:
            SCALING = 3
        else:
            SCALING = 1.5

        if values is not None and limits is None:
            limits = (min(values), max(values))

        for i, one_chan in enumerate(chan.chan):
            s = solidSphere(list(one_chan.xyz), scaling=SCALING)

            if values is not None:
                _set_value_to_chan(s, values[i])
                s.clim = limits
            else:
                s.faceColor = color
            s.colormap = colormap

            self._h_chan.append(s)

    def update_surf(self, color=None, values=None, limits=None, colormap=None):
        """Change values of the brain surface.

        Parameters
        ----------
        color : tuple, optional
            4-element tuple, representing RGB and alpha, between 0 and 1
        values : ndarray, optional
            vector with values for each channel
        limits : tuple of 2 floats, optional
            min and max values to normalize the color
        colormap : ndarray, optional
            matrix for the color coding (such as CM_JET, CM_HOT, ...)
        """
        m = self._h_surf
        if values is not None:
            m.SetValues(dot(self.xyz2surf, values))

        if limits is not None:
            m.clim = limits

        if colormap is not None:
            m.colormap = colormap

        if color is not None:
            m.faceColor = color

    def update_chan(self, color=None, values=None, limits=None, colormap=None):
        """Change values of the electrodes.

        Parameters
        ----------
        color : tuple, optional
            4-element tuple, representing RGB and alpha, between 0 and 1
        values : ndarray, optional
            vector with values for each channel
        limits : tuple of 2 floats, optional
            min and max values to normalize the color
        colormap : ndarray, optional
            matrix for the color coding (such as CM_JET, CM_HOT, ...)
        """
        for i, s in enumerate(self._h_chan):

            if values is not None:
                _set_value_to_chan(s, values[i])

            if limits is not None:
                s.clim = limits

            if colormap is not None:
                s.colormap = colormap

            if color is not None:
                s.faceColor = color

    def animate_surf(self, all_values, output_file):
        """Create a movie with the changing values onto the surface.

        Parameters
        ----------
        all_values : ndarray
            nTime X nChan matrix, it will loop over time
        output_file : str
            path to file, it can end in '.gif' or in any format used by avconv

        Notes
        -----
        It needs 'avconv' to be installed.
        I cannot modify frame rate in avconv, default is 24. Lots of options
        but I don't know how to use them.
        """
        img_dir = mkdtemp()

        for i, values in enumerate(all_values):
            self.update_surf(values=values)
            self._fig.DrawNow()
            screenshot(join(img_dir, IMAGE % i), self._fig, sf=1)

        if splitext(output_file)[1] == '.gif':
            _make_gif(img_dir, output_file)
        else:
            _make_mp4(img_dir, output_file)

    def animate_chan(self, all_values, output_file):
        """Create a movie with the changing values of the electrodes.

        Parameters
        ----------
        all_values : ndarray
            nTime X nChan matrix, it will loop over time
        output_file : str
            path to file, it can end in '.gif' or in any format used by avconv

        Notes
        -----
        It needs 'avconv' to be installed.
        I cannot modify frame rate in avconv, default is 24. Lots of options
        but I don't know how to use them.
        """
        img_dir = mkdtemp()

        for i, values in enumerate(all_values):
            self.update_chan(values=values)
            self._fig.DrawNow()
            screenshot(join(img_dir, IMAGE % i), self._fig, sf=1)

        if splitext(output_file)[1] == '.gif':
            _make_gif(img_dir, output_file)
        else:
            _make_mp4(img_dir, output_file)

    def rotate(self, output_file, loop='full', step=5):
        """Create rotating images in a temporary folder.

        Parameters
        ----------
        output_file : str
            path to file, it can end in '.gif' or in any format used by avconv
        loop : str, optional
            'full' (complete rotation) or 'hemi' (half rotation) or
            'consistent' (but both hemispheres have the same direction) or
            'patrol' (half rotation back and forth)
        step : int, optional
            distance in degrees between frames
        """
        img_dir = mkdtemp()

        if self._ax.camera.azimuth > 0:  # right hemi
            if loop == 'hemi':
                angles = range(180, 0, -step)
            elif loop == 'full':
                angles = range(180, -180, -step)
            elif loop == 'patrol':
                angles = chain(range(180, 0, -step),
                               range(0, 180, step))
            elif loop == 'consistent':
                angles = range(180, 0, -step)

        else:
            if loop == 'hemi':
                angles = range(-180, 0, step)
            elif loop == 'full':
                angles = range(-180, 180, step)
            elif loop == 'patrol':
                angles = chain(range(-180, 0, step),
                               range(0, -180, -step))
            elif loop == 'consistent':
                angles = range(0, -180, -step)

        for i, ang in enumerate(angles):
            self._ax.camera.azimuth = ang
            self._fig.DrawNow()
            screenshot(join(img_dir, IMAGE % i), self._fig, sf=1)

        if splitext(output_file)[1] == '.gif':
            _make_gif(img_dir, output_file)
        else:
            _make_mp4(img_dir, output_file)

    def center_surf(self):
        """Center the figure by looking at the side of the hemisphere."""
        center_surf = tuple(mean(self._surf.vert, axis=0))
        self._ax.camera.loc = center_surf
        self._ax.camera.elevation = 0
        self._ax.camera.zoom = 0.007

        if center_surf[0] > 0:  # right hemisphere
            self._ax.camera.azimuth = 90
        else:
            self._ax.camera.azimuth = 270


def calc_xyz2surf(surf, xyz, threshold=10):
    """Calculate transformation matrix from xyz values to vertices.

    Parameters
    ----------
    surf : instance of phypno.attr.Surf
        the surface of only one hemisphere.
    xyz : numpy.ndarray
        nChan x 3 matrix, with the locations in x, y, z.
    threshold : float
        distance in mm for a vertex to pick up electrode activity

    Returns
    -------
    numpy.ndarray
        nVertices X xyz.shape[0] matrix

    Notes
    -----
    This function is a helper when plotting onto brain surface, by creating a
    transformation matrix from the values in space (f.e. at each electrode) to
    the position of the vertices (used to show the brain surface).

    There are many ways to move from values to vertices.
    You can also create your own matrix (and skip calc_xyz2surf altogether) and
    pass it as attribute to the main figure.
    Because it's a loop over all the vertices, this function is pretty slow,
    but if you calculate it once, you can reuse it.
    We take advantage of multiprocessing, which speeds it up considerably.
    """
    with Pool() as p:
        xyz2surf = p.map(partial(calc_one_vert, xyz=xyz, thres=threshold),
                         surf.vert)

    xyz2surf = asarray(xyz2surf)
    xyz2surf[isnan(xyz2surf)] = 0

    return xyz2surf


def calc_one_vert(one_vert, xyz=None, thres=10):
    """Calculate how many electrodes influence one vertex.

    Parameters
    ----------
    one_vert : ndarray
        vector of xyz position of a vertex
    xyz : ndarray
        nChan X 3 with the position of all the channels
    threshold : float
        distance in mm for a vertex to pick up electrode activity

    Returns
    -------
    ndarray
        one vector with values for one vertex
    """
    trans = empty(xyz.shape[0])
    for i, one_xyz in enumerate(xyz):
        if norm(one_vert - one_xyz) <= thres:
            trans[i] = 1
        else:
            trans[i] = NaN
    return trans / count_nonzero(~isnan(trans))


def _set_value_to_chan(s, v):
    """Change color for one channel. Each dot is actually a complicated mesh,
    so we need to change the color of all the elements.

    Parameters
    ----------
    s : instance of solidSphere
        the representation of the channel
    v : float
        value to assign to the channel.
    """
    n_vert = s._vertices.shape[0]
    s.SetValues(v * ones((n_vert, 1)))


def _make_gif(img_dir, gif_file):
    """Save the image as rotating gif.

    Parameters
    ----------
    img_dir : path to dir
        directory with all the imags
    gif_file : path to file
        file where you want to save the gif

    Notes
    -----
    It requires ''convert'' from Imagemagick
    """
    call('convert ' + join(img_dir, 'image*.jpg') + ' ' + gif_file,
         shell=True)


def _make_mp4(img_dir, movie_file):
    """Save the image as rotating movie.

    Parameters
    ----------
    img_dir : path to dir
        directory with all the imags
    movie_file : path to file
        file where you want to save the movie

    Notes
    -----
    It requires ''avconv'' from LibAv
    """
    try:
        remove(movie_file)
    except FileNotFoundError:
        pass

    call('avconv -i ' + join(img_dir, IMAGE) +
         ' -tune animation ' + movie_file, shell=True)
