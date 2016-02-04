# -*- coding: utf-8 -*-

import numpy as np
import copy
from operator import attrgetter, methodcaller
from itertools import product
from GeoMod import BSplineBasis
from GeoMod.Utils import *

__all__ = ['SplineObject']


def rotation_matrix(theta, axis):
    axis = axis / np.sqrt(np.dot(axis, axis))
    a = np.cos(theta / 2)
    b, c, d = -axis*np.sin(theta / 2)
    return np.matrix([[a*a+b*b-c*c-d*d, 2*(b*c-a*d),     2*(b*d+a*c)],
                      [2*(b*c+a*d),     a*a+c*c-b*b-d*d, 2*(c*d-a*b)],
                      [2*(b*d-a*c),     2*(c*d+a*b),     a*a+d*d-b*b-c*c]])


class SplineObject(object):
    """SplineObject()

    Master class for spline objects with arbitrary dimensions.

    This class should be subclassed instead of used directly.

    All SplineObjects support basic arithmetic operators, which are interpreted
    as translation and scaling. In-place operators (e.g. ``+=``) mutate the
    object, while infix operators (e.g. ``+``) create new objects.
    """

    def __init__(self, bases=None, controlpoints=None, rational=False):
        """__init__([bases=None], [controlpoints=None], [rational=False])

        Construct a spline object with the given bases and control points.

        The default is to create a linear one-element mapping from and to the
        unit (hyper)cube.

        :param [BSplineBasis] bases: The basis of each parameter direction
        :param array-like controlpoints: An *n1* × *n2* × ... × *d* matrix of
            control points
        :param bool rational: Whether the object is rational (in which case the
            control points are interpreted as pre-multiplied with the weight,
            which is the last coordinate)
        """
        bases = [(b if b else BSplineBasis()) for b in bases]
        self.bases = bases
        if controlpoints is None:
            # `product' produces tuples in row-major format (the last input varies quickest)
            # We want them in column-major format, so we reverse the basis orders, and then
            # also reverse the output tuples
            controlpoints = [c[::-1] for c in product(*(b.greville() for b in bases[::-1]))]

            # Minimum two dimensions
            if len(controlpoints[0]) == 1:
                controlpoints = [tuple(list(c) + [0.0]) for c in controlpoints]

        controlpoints = np.array(controlpoints)
        self.dimension = controlpoints.shape[-1] - rational
        self.rational = rational

        # Reshape the array so that it's not just flat
        cp_shape = tuple([b.num_functions() for b in bases[::-1]] + [self.dimension + rational])
        controlpoints = np.reshape(controlpoints, cp_shape)

        # Compensate for numpy's row-major ordering
        # cps = cps.transpose((n-1,n-2,...,0,n))
        spec = tuple(list(range(len(bases)))[::-1] + [len(bases)])
        self.controlpoints = controlpoints.transpose(spec)

    def _validate_domain(self, *params):
        """Check whether the given evaluation parameters are valid.

        :raises ValueError: If the parameters are outside the domain"""
        for b, p in zip(self.bases, params):
            if b.periodic < 0:
                if min(p) < b.start() or b.end() < max(p):
                    raise ValueError('Evaluation outside parametric domain')

    def evaluate(self, *params):
        """evaluate(u, v, ...)

        Evaluate the object at given parametric values.

        This function returns an *n1* × *n2* × ... × *dim* array, where *ni* is
        the number of evaluation points in direction *i*, and *dim* is the
        physical dimension of the object.

        If there is only one evaluation point, a vector of length *dim* is
        returned instead.

        :param u,v,...: Parametric coordinates in which to evaluate
        :type u,v,...: float or [float]
        :return: Geometry coordinates
        :rtype: numpy.array
        """
        params = [ensure_listlike(p) for p in params]

        self._validate_domain(*params)

        # Evaluate the derivatives of the corresponding bases at the corresponding points
        # and build the result array
        Ns = [b.evaluate(p) for b, p in zip(self.bases, params)]
        idx = len(self.bases) - 1
        result = self.controlpoints
        for N in Ns[::-1]:
            result = np.tensordot(N, result, axes=(1, idx))

        # For rational objects, we divide out the weights, which are stored in the
        # last coordinate
        if self.rational:
            for i in range(self.dimension):
                result[..., i] /= result[..., -1]
            result = np.delete(result, self.dimension, -1)

        # Squeeze the singleton dimensions if we only have one point
        if all(s == 1 for s in result.shape[:-1]):
            result = result.reshape(self.dimension)

        return result

    def evaluate_derivative(self, *params, **kwargs):
        """evaluate_derivative(u, v, ..., [d=(1,1,...)])

        Evaluate the derivative of the object at the given parametric values.

        This function returns an *n1* × *n2* × ... × *dim* array, where *ni* is
        the number of evaluation points in direction *i*, and *dim* is the
        physical dimension of the object.

        If there is only one evaluation point, a vector of length *dim* is
        returned instead.

        Examples:

        .. code:: python

           # Tangent of curve at single point
           curve.evaluate_derivative(1.0)

           # Double derivative of curve at single point:
           curve.evaluate_derivative(1.0, d=2)

           # Third derivative of curve at several points:
           curve.evaluate_derivative([0.0, 1.0, 2.0], d=3)

           # Tangents of surface:
           surface.evaluate_derivative(0.5, 0.7, d=(1,0))
           surface.evaluate_derivative(0.5, 0.7, d=(0,1))

           # Cross-derivative of surface:
           surface.evaluate_derivative(0.5, 0.7, d=(1,1))

        :param u,v,...: Parametric coordinates in which to evaluate
        :type u,v,...: float or [float]
        :param (int) d: Order of derivative to compute
        :return: Derivatives
        :rtype: numpy.array
        """
        params = [ensure_listlike(p) for p in params]

        derivs = kwargs.get('d', [1] * len(self.bases))
        derivs = ensure_listlike(derivs)

        self._validate_domain(*params)

        # Evaluate the derivatives of the corresponding bases at the corresponding points
        # and build the result array
        dNs = [b.evaluate(p, d) for b, p, d in zip(self.bases, params, derivs)]
        idx = len(self.bases) - 1
        result = self.controlpoints
        for dN in dNs[::-1]:
            result = np.tensordot(dN, result, axes=(1, idx))

        # For rational curves, we need to use the quotient rule
        # (n/W)' = (n' W - n W') / W^2 = n'/W - nW'/W^2
        # * n'(i) = result[..., i]
        # * W'(i) = result[..., -1]
        # We evaluate in the regular way to compute n and W.
        if self.rational:
            if sum(derivs) > 1:
                raise RuntimeError('Rational derivative not implemented for order %i' % sum(derivs))
            Ns = [b.evaluate(p) for b, p in zip(self.bases, params)]
            non_derivative = self.controlpoints
            for N in Ns[::-1]:
                non_derivative = np.tensordot(N, non_derivative, axes=(1, idx))
            W = non_derivative[..., -1]  # W
            Wd = result[..., -1]         # W'
            for i in range(self.dimension):
                result[..., i] = result[..., i] / W - non_derivative[..., i] * Wd / W / W;
            result = np.delete(result, self.dimension, 1)

        # Squeeze the singleton dimensions if we only have one point
        if all(s == 1 for s in result.shape[:-1]):
            result = result.reshape(self.dimension)

        return result

    def start(self, direction=None):
        """start([direction=None])

        Return the start of the parametric domain.

        If `direction` is given, returns the start of that direction, as a
        float. If it is not given, returns the start of all directions, as a
        tuple.

        :param int direction: Direction in which to get the start.
        :raises ValueError: For invalid direction
        """
        if direction is None:
            return tuple(b.start() for b in self.bases)
        direction = check_direction(direction, self.pardim)
        return self.bases[direction].start()

    def end(self, direction=None):
        """end([direction=None])

        Return the end of the parametric domain.

        If `direction` is given, returns the end of that direction, as a float.
        If it is not given, returns the end of all directions, as a tuple.

        :param int direction: Direction in which to get the end.
        :raises ValueError: For invalid direction
        """
        if direction is None:
            return tuple(b.end() for b in self.bases)
        direction = check_direction(direction, self.pardim)
        return self.bases[direction].end()

    def order(self, direction=None):
        """order([direction=None])

        Return polynomial order (degree + 1).

        If `direction` is given, returns the order of that direction, as an
        int. If it is not given, returns the order of all directions, as a
        tuple.

        :param int direction: Direction in which to get the order.
        :raises ValueError: For invalid direction
        """
        if direction is None:
            return tuple(b.order for b in self.bases)
        direction = check_direction(direction, self.pardim)
        return self.bases[direction].order

    def knots(self, direction=None, with_multiplicities=False):
        """knots([direction=None], [with_multiplicities=False])

        Return knots.

        If `direction` is given, returns the knots in that direction, as a
        list. If it is not given, returns the knots of all directions, as a
        tuple.

        :param int direction: Direction in which to get the knots.
        :param bool with_multiplicities: If true, return knots with
            multiplicities (i.e. repeated).
        :raises ValueError: For invalid direction
        """
        getter = attrgetter('knots') if with_multiplicities else methodcaller('knot_spans')
        if direction is None:
            return tuple(getter(b) for b in self.bases)
        direction = check_direction(direction, self.pardim)
        return getter(self.bases[direction])

    def reverse(self, direction=0):
        """reverse([direction=0])

        Swap the direction of a parameter by making it go in the reverse
        direction. The parametric domain remains unchanged.

        :param int direction: The direction to flip.
        """
        direction = check_direction(direction, self.pardim)
        self.bases[direction].reverse()

        # This creates the following slice programmatically
        # array[:, :, :, ..., ::-1,]
        # index=direction -----^
        # :    => slice(None, None, None)
        # ::-1 => slice(None, None, -1)
        direction = check_direction(direction, self.pardim)
        slices = [slice(None, None, None) for _ in range(direction)] + [slice(None, None, -1)]
        self.controlpoints = self.controlpoints[tuple(slices)]

    def swap(self, dir1=0, dir2=1):
        """Swaps two parameter directions.

        This function silently passes for curves.

        :param direction dir1: The first direction (default u)
        :param direction dir2: The second direction (default v)
        """
        if self.pardim == 1:
            return

        dir1 = check_direction(dir1, self.pardim)
        dir2 = check_direction(dir2, self.pardim)

        # Reorder control points
        new_directions = list(range(self.pardim + 1))
        new_directions[dir1] = dir2
        new_directions[dir2] = dir1
        self.controlpoints = self.controlpoints.transpose(new_directions)

        # Swap knot vectors
        self.bases[dir1], self.bases[dir2] = self.bases[dir2], self.bases[dir1]

    def insert_knot(self, knot, direction=0):
        """Insert a new knot into the spline.

        :param int direction: The direction to insert in
        :param knot: The new knot(s) to insert
        :type knot: float or [float]
        :raises ValueError: For invalid direction
        """
        shape  = self.controlpoints.shape

        # for single-value input, wrap it into a list
        knot = ensure_listlike(knot)

        direction = check_direction(direction, self.pardim)

        transpose_fix = [[], [(0,1)], [(0,1,2), (1,0,2)], [(0,1,2,3),(1,0,2,3),(1,2,0,3)]]
        C = np.matrix(np.identity(shape[direction]))
        for k in knot:
            C = self.bases[direction].insert_knot(k) * C
        self.controlpoints = np.tensordot(C, self.controlpoints, axes=(1, direction))
        self.controlpoints = self.controlpoints.transpose(transpose_fix[self.pardim][direction])

    def refine(self, n):
        """Enrich the spline space by inserting *n* knots into each existing
        knot span.

        :param int n: The number of new knots to insert into each span
        """
        (knots1, knots2, knots3) = self.knots()  # excluding multiple knots
        pardir = 0
        for knot in self.knots():
            new_knots = []
            for (k0, k1) in zip(knot[:-1], knot[1:]):
                element_knots = np.linspace(k0, k1, n + 2)
                new_knots += list(element_knots[1:-1])
            self.insert_knot(new_knots, pardir)
            pardir += 1

    def reparam(self, *args, **kwargs):
        """reparam([u, v, ...], [direction=None])

        Redefine the parametric domain. This function accepts two calling
        conventions:

        `reparametrize(u, v, ...)` reparametrizes each direction to the domains
        given by the tuples *u*, *v*, etc. It is equivalent to calling
        `reparametrize(u[0], u[1])` on each basis. The default domain for
        directions not given is (0,1). In particular, if no arguments are
        given, the new parametric domain will be the unit (hyper)cube.

        `reparametrize(u, direction=d)` reparametrizes just the direction given
        by *d* and leaves the others untouched.

        :param tuple u, v, ...: New parametric domains, default to (0,1)
        :param int direction: The direction to reparametrize
        """
        if 'direction' not in kwargs:
            # Pad the args with (0, 1) for the extra directions
            args = list(args) + [(0, 1)] * (len(self.bases) - len(args))
            for b, (start, end) in zip(self.bases, args):
                b.reparam(start, end)
        else:
            direction = kwargs['direction']
            direction = check_direction(direction, self.pardim)
            if len(args) == 0:
                self.bases[direction].reparam(0,1)
            else:
                start, end = args[0]
                self.bases[direction].reparam(start, end)

    def translate(self, x):
        """Translate (i.e. move) the object by a given distance.

        :param point-like x: The vector to translate by.
        """
        # 3D rational example: create a 4x4 translation matrix
        #
        #  |xw|      |  1   0   0  x1 |   |xw|
        #  |yw|   =  |  0   1   0  x2 | * |yw|
        #  |zw|      |  0   0   1  x3 |   |zw|
        #  | w|_new  |  0   0   0   1 |   | w|_old
        #
        #  PS: we even need a rational representation for non-rational splines
        #      in order to formulate translation as a matrix-matrix product
        dim = self.dimension
        rat = self.rational
        n = len(self)  # number of control points
        if len(x) > dim:  # typical case: requesting movement in z-direction for 2D geometries
            self.set_dimension(len(x))
            dim = self.dimension

        # set up the translation matrix
        translation_matrix = np.matrix(np.identity(dim + 1))
        for i in range(dim):
            translation_matrix[i, -1] = x[i]

        # wrap out the controlpoints to a matrix (down from n-D tensor)
        if not self.rational:
            cp = np.matrix(np.ones((n, dim + 1)))  # pad with weights=1
            cp[:, :-1] = np.reshape(self.controlpoints, (n, dim))
        else:
            cp = np.matrix(np.reshape(self.controlpoints, (n, dim + rat)))

        # do the actual scaling by matrix-matrix multiplication
        cp = cp * translation_matrix.T  # right-mult, so we need transpose

        # store results
        if self.rational:
            self.controlpoints = np.reshape(np.array(cp), self.controlpoints.shape)
        else:
            self.controlpoints = np.reshape(np.array(cp[:, :-1]), self.controlpoints.shape)

        return self

    def scale(self, *args):
        """scale(sx, [sy, sz, ...])

        Scale, or magnify the object by a given amount.

        In case of one input argument, the scaling is uniform.

        :param args: Scaling factors, possibly different in each direction.
        :type args: point-like or float
        """
        # 3D rational example: create a 4x4 scaling matrix
        #
        #  |xw|      |  sx    0    0   0 |   |xw|
        #  |yw|   =  |   0   sy    0   0 | * |yw|
        #  |zw|      |   0    0   sz   0 |   |zw|
        #  | w|_new  |   0    0    0   1 |   | w|_old
        #
        dim = self.dimension
        rat = self.rational
        n = len(self)  # number of control points
        s = ensure_flatlist(args)
        s = ensure_listlike(s, dups=3)

        # set up the scaling matrix
        scale_matrix = np.matrix(np.identity(dim + rat))
        for i in range(dim):
            scale_matrix[i, i] = s[i]

        # wrap out the controlpoints to a matrix (down from n-D tensor)
        cp = np.matrix(np.reshape(self.controlpoints, (n, dim + rat)))

        # do the actual scaling by matrix-matrix multiplication
        cp = cp * scale_matrix

        # store results
        self.controlpoints = np.reshape(np.array(cp), self.controlpoints.shape)

        return self

    def rotate(self, theta, normal=(0, 0, 1)):
        """rotate(theta, [normal=(0,0,1)])

        Rotate the object around an axis.

        :param float theta: Angle to rotate about, measured in radians
        :param point-like normal: The normal axis (if 3D) to rotate about
        :raises RuntimeError: If the physical dimension is not 2 or 3
        """
        # 2D rational example: create a 3x3 rotation matrix
        #
        #  |xw|     | cos(t)  -sin(t)   0 |   |xw|
        #  |yw|   = | sin(t)   cos(t)   0 | * |yw|
        #  | w|_new |   0        0      1 |   | w|_old
        #

        dim = self.dimension
        rat = self.rational
        n = len(self)  # number of control points
        if not (normal[0] == 0 and normal[1] == 0):  # rotating a 2D geometry out of the xy-plane
            self.set_dimension(3)
            dim = self.dimension

        # set up the rotation matrix
        if dim == 2:
            R = np.matrix([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]
                           ]).T  # we do right-multiplication, so we need a transpose
        elif dim == 3:
            normal = np.array(normal)
            R = rotation_matrix(theta, normal)
        else:
            raise RuntimeError('rotation undefined for geometries other than 2D and 3D')

        rot_matrix = np.matrix(np.identity(dim + rat))
        rot_matrix[0:dim, 0:dim] = R

        # wrap out the controlpoints to a matrix (down from n-D tensor)
        cp = np.matrix(np.reshape(self.controlpoints, (n, dim + rat)))

        # do the actual rotation by matrix-matrix multiplication
        cp = cp * rot_matrix

        # store results
        self.controlpoints = np.reshape(np.array(cp), self.controlpoints.shape)

        return self

    def mirror(self, normal):
        """Mirror the object around a plane through the origin.

        :param point-like normal: The plane normal to mirror about.
        :raises RuntimeError: If the physical dimension is not 2 or 3
        """
        # 3D rational example: create a 4x4 reflection matrix
        #
        #  normal = [a,b,c]
        #
        #  |xw|     |  1-2a^2   -2ab    -2ac   0 |   |xw|
        #  |yw|   = |   -2ab   1-2b^2   -2bc   0 | * |yw|
        #  |zw|   = |   -2ac    -2bc   1-2c^2  0 | * |zw|
        #  | w|_new |    0       0         0   1 |   | w|_old
        #
        #  PS: A reflection about a line is not a linear transformation; it is
        #      an affine transformation.

        dim = self.dimension
        rat = self.rational
        n = len(self)  # number of control points

        if dim != 3:
            raise RuntimeError('reflection undefined for geometries other than 3D')

        # fixup the input normal to right form
        normal = np.array(normal)
        normal = normal / np.sqrt(np.dot(normal, normal))  # normalize it

        # set up the reflection matrix
        reflection_matrix = np.matrix(np.identity(dim + rat))
        reflection_matrix[0:dim, 0:dim] -= 2 * np.outer(normal, normal)

        # wrap out the controlpoints to a matrix (down from n-D tensor)
        cp = np.matrix(np.reshape(self.controlpoints, (n, dim + rat)))

        # do the actual rotation by matrix-matrix multiplication
        cp = cp * reflection_matrix

        # store results
        self.controlpoints = np.reshape(np.array(cp), self.controlpoints.shape)

        return self

    def project(self, plane):
        """Projects the geometry onto a plane or axis.

        - `project('xy')` will project the object onto the *xy* plane, setting
          all *z* components to zero.
        - `project('y')` will project the object onto the *y* axis, setting all
          *x* and *z* components to zero.

        :param string plane: Any combination of 'x', 'y' and 'z'
        """
        keep = [False] * 3
        for s in plane:
            if s == 'x' or s == 'X':
                keep[0] = True
            if s == 'y' or s == 'Y':
                keep[1] = True
            if s == 'z' or s == 'Z':
                keep[2] = True

        dim = self.dimension
        for i in range(dim):
            if not keep[i]:
                self.controlpoints[..., i] = 0

        return self

    def bounding_box(self):
        """Gets the bounding box of a spline object, computed from the
        control-point values. Could be inaccurate for rational splines.

        Returns the minima and maxima for each direction:
        [xmin, xmax, ymin, ymax, ...]

        :return: Bounding box
        :rtype: [float]
        """
        dim = self.dimension

        result = []
        for i in range(dim):
            result.append(np.min(self.controlpoints[..., i]))
            result.append(np.max(self.controlpoints[..., i]))
        return result

    def center(self):
        """Gets the center of the domain
        
        For curves this will return :math:`(\\tilde{x}, \\tilde{y},...)`, where

        .. math:: \\tilde{x} = \\frac{1}{L} \int_{t_0}^{t_1} x(t) \; dt 

        and :math:`L=t_1-t_0` is the length of the parametric domain :math:`[t_0,t_1]`.

        For surfaces this will return :math:`(\\tilde{x}, \\tilde{y},...)`, where

        .. math:: \\tilde{x} = \\frac{1}{A} \int_{v_0}^{v_1} \int_{u_0}^{u_1} x(u,v) \; du \; dv

        and :math:`A=(u_1-u_0)(v_1-v_0)` is the area of the parametric domain :math:`[u_0,u_1]\\times[v_0,v_1]`.

        .. warning:: For rational splines, this will return center in projective coordinates (including weight)
        """

        # compute integration of basis functions
        Ns = [b.integrate(b.start(), b.end()) for b in self.bases]

        # compute parametric size
        par_size = np.prod([t1-t0 for (t0,t1) in zip(self.start(), self.end())])

        # multiply basis functions with control points
        idx = self.pardim - 1
        result = self.controlpoints
        for N in Ns[::-1]:
            result = np.tensordot(N, result, axes=(0, idx))

        return result / par_size

    def set_dimension(self, new_dim):
        """Sets the physical dimension of the object. If increased, the new
        components are set to zero.

        :param int new_dim: New dimension.
        """
        dim = self.dimension
        shape = self.controlpoints.shape
        while new_dim > dim:
            self.controlpoints = np.insert(self.controlpoints, dim, np.zeros(shape[:-1]), self.pardim)
            dim += 1
        while new_dim < dim:
            np.insert(self.controlpoints, dim, self.pardim)
            dim -= 1
        self.dimension = new_dim

        return self

    def force_rational(self):
        """Force a rational representation of the object.

        The weights of a non-rational object will be set to 1.
        """
        if not self.rational:
            dim = self.dimension
            shape = self.controlpoints.shape
            self.controlpoints = np.insert(self.controlpoints, dim, np.ones(shape[:-1]), self.pardim)
            self.rational = 1

        return self

    @property
    def pardim(self):
        """The number of parametric dimensions: 1 for curves, 2 for surfaces, 3
        for volumes, etc.
        """
        return len(self.controlpoints.shape)-1

    def clone(self):
        """Clone the object."""
        return copy.deepcopy(self)

    __call__ = evaluate

    def __len__(self):
        """Return the number of control points (basis functions) for the object."""
        n = 1
        for b in self.bases:
            n *= b.num_functions()
        return n

    def _unravel_flat_index(self, i):
        """Unravels a flat index i to multi-indexes.

        :param i: Flat index
        :type i: int or slice
        :rtype: Tuple of np.array
        :raises IndexError: If the index is out of bounds
        """
        # i is int => make sure we deal with negative i properly
        # i is slice => use i.indices to compute the actual indices
        total = len(self)
        if isinstance(i, int):
            indexes = [i] if i >= 0 else [total + i]
        else:
            indexes = list(range(*i.indices(total)))

        # Convert to multi-indexes
        try:
            unraveled = np.unravel_index(indexes, self.controlpoints.shape[:-1], order='F')
        except ValueError:
            raise IndexError

        return unraveled

    def __getitem__(self, i):
        """Get the control point at a given index.

        Indexing is in column-major order. Examples of supported indexing
        modes:

        .. code:: python

           # Flat indexing with an int
           obj[4]

           # Flat indexing from the end
           obj[-1]

           # Flat indexing with a slice
           obj[2:5]

           # Multi-indexing with ints, negative ints and slices
           obj[0,-1,:]

        :rtype: numpy.array
        """
        if isinstance(i, tuple):
            return self.controlpoints[i]

        unraveled = self._unravel_flat_index(i)

        # Singleton dimensions should be squeezed if the input was an int
        if isinstance(i, int):
            return self.controlpoints[unraveled][0]
        return self.controlpoints[unraveled]

    def __setitem__(self, i, cp):
        """Set the control points at given indices.

        This function supports the same indexing modes as
        :func:`SplineObject.__getitem__`

        :param int i: Index or indices
        :param numpy.array cp: New control point(s)
        """
        if isinstance(i, tuple):
            self.controlpoints[i] = cp
            return

        unraveled = self._unravel_flat_index(i)
        self.controlpoints[unraveled] = cp

    @property
    def shape(self):
        """The dimensions of the control point array."""
        return self.controlpoints.shape[:-1]

    def __iadd__(self, x):
        self.translate(x)
        return self

    def __isub__(self, x):
        self.translate(-np.array(x))  # can't do -x if x is a list, so we rewrap it here
        return self

    def __imul__(self, x):
        self.scale(x)
        return self

    def __itruediv__(self, x):
        self.scale(1.0 / x)
        return self

    __ifloordiv__ = __itruediv__  # integer division (should not distinguish)
    __idiv__ = __itruediv__  # python2 compatibility

    def __add__(self, x):
        new_obj = copy.deepcopy(self)
        new_obj += x
        return new_obj

    def __sub__(self, x):
        new_obj = copy.deepcopy(self)
        new_obj -= x
        return new_obj

    def __mul__(self, x):
        new_obj = copy.deepcopy(self)
        new_obj *= x
        return new_obj

    def __div__(self, x):
        new_obj = copy.deepcopy(self)
        new_obj /= x
        return new_obj

    @classmethod
    def make_splines_compatible(cls, spline1, spline2):
        """Ensure that two splines are compatible.

        This will manipulate one or both to ensure that they are both rational
        or nonrational, and that they lie in the same physical space.

        :param SplineObject spline1: The first spline
        :param SplineObject spline2: The second spline
        """
        # make both rational (if needed)
        if spline1.rational:
            spline2.force_rational()
        elif spline2.rational:
            spline1.force_rational()

        # make both in the same geometric space
        if spline1.dimension > spline2.dimension:
            spline2.set_dimension(spline1.dimension)
        else:
            spline1.set_dimension(spline2.dimension)

    @classmethod
    def make_splines_identical(cls, spline1, spline2):
        """Ensure that two splines have identical discretization.

        This will first make them compatible (see
        :func:`GeoMod.SplineObject.make_curves_compatible`), reparametrize them, and
        possibly raise the order and insert knots as required.

        :param SplineObject spline1: The first spline
        :param SplineObject spline2: The second spline
        """
        # make sure that rational/dimension is the same
        SplineObject.make_splines_compatible(spline1, spline2)

        # make both have knot vectors in domain (0,1)
        spline1.reparam()
        spline2.reparam()

        # make sure both have the same order
        p1 = spline1.order()
        p2 = spline2.order()
        p  = tuple(max(q,r) for (q,r) in zip(p1,p2))
        raise1 = tuple(max(q-r,0) for (q,r) in zip(p,p1))
        raise2 = tuple(max(q-r,0) for (q,r) in zip(p,p2))

        spline1.raise_order( *raise1 )
        spline2.raise_order( *raise2 )

        # make sure both have the same knot vectors
        for i in range(spline1.pardim):
            knot1 = spline1.knots(direction=i, with_multiplicities=True)
            knot2 = spline2.knots(direction=i, with_multiplicities=True)
            i1 = 0
            i2 = 0
            while i1 < len(knot1) and i2 < len(knot2):
                if abs(knot1[i1] - knot2[i2]) < spline1.bases[i].tol:
                    i1 += 1
                    i2 += 1
                elif knot1[i1] < knot2[i2]:
                    spline2.insert_knot(knot1[i1], direction=i)
                    i1 += 1
                else:
                    spline1.insert_knot(knot2[i2], direction=i)
                    i2 += 1

