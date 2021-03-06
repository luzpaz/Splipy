# -*- coding: utf-8 -*-

"""Handy utilities for creating curves."""

from math import pi, cos, sin, sqrt, ceil
from splipy import Curve, BSplineBasis
from splipy.utils import flip_and_move_plane_geometry
import numpy as np

__all__ = ['line', 'polygon', 'n_gon', 'circle', 'circle_segment', 'interpolate',
           'least_square_fit', 'cubic_curve']

FREE=1
NATURAL=2
HERMITE=3
PERIODIC=4
TANGENT=5
TANGENTNATURAL=6
UNIFORM=8

def line(a, b):
    """Create a line between two points.

    :param point-like a: Start point
    :param point-like b: End point
    :return: Linear curve from *a* to *b*
    :rtype: Curve
    """
    return Curve(controlpoints=[a, b])


def polygon(*points):
    """polygon(points...)

    Create a linear interpolation between input points.

    :param [point-like] points: The points to interpolate
    :return: Linear curve through the input points
    :rtype: Curve
    """
    if len(points) == 1:
        points = points[0]

    # establish knot vector based on eucledian length between points
    knot = [0, 0]
    prevPt = points[0]
    for pt in points[1:]:
        dist = 0
        for (x0, x1) in zip(prevPt, pt):  # loop over (x,y) and maybe z-coordinate
            dist += (x1 - x0)**2
        knot.append(knot[-1] + sqrt(dist))
        prevPt = pt
    knot.append(knot[-1])

    return Curve(BSplineBasis(2, knot), points)


def n_gon(n=5, r=1, center=(0,0,0), normal=(0,0,1)):
    """n_gon([n=5], [r=1])

    Create a regular polygon of *n* equal sides centered at the origin.

    :param int n: Number of sides and vertices
    :param float r: Radius
    :param point-like center: local origin
    :param vector-like normal: local normal
    :return: A linear, periodic, 2D curve
    :rtype: Curve
    :raises ValueError: If radius is not positive
    :raises ValueError: If *n* < 3
    """
    if r <= 0:
        raise ValueError('radius needs to be positive')
    if n < 3:
        raise ValueError('regular polygons need at least 3 sides')

    cp = []
    dt = 2 * pi / n
    knot = [-1]
    for i in range(n):
        cp.append([r * cos(i * dt), r * sin(i * dt)])
        knot.append(i)
    knot += [n, n+1]
    basis = BSplineBasis(2, knot, 0)

    result =  Curve(basis, cp)
    return flip_and_move_plane_geometry(result, center, normal)

def circle(r=1, center=(0,0,0), normal=(0,0,1)):
    """circle([r=1])

    Create a circle.

    :param float r: Radius
    :param point-like center: local origin
    :param vector-like normal: local normal
    :return: A periodic, quadratic rational curve
    :rtype: Curve
    :raises ValueError: If radius is not positive
    """
    if r <= 0:
        raise ValueError('radius needs to be positive')

    w = 1.0 / sqrt(2)
    controlpoints = [[r, 0, 1],
                     [r*w, r*w, w],
                     [0, r, 1],
                     [-r*w, r*w, w],
                     [-r, 0, 1],
                     [-r*w, -r*w, w],
                     [0, -r, 1],
                     [r*w, -r*w, w]]
    knot = np.array([-1, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5]) / 4.0 * 2 * pi

    result = Curve(BSplineBasis(3, knot, 0), controlpoints, True)
    return flip_and_move_plane_geometry(result, center, normal)

def circle_segment(theta, r=1, center=(0,0,0), normal=(0,0,1)):
    """circle_segment(theta, [r=1])

    Create a circle segment starting paralell to the rotated x-axis.

    :param float theta: Angle in radians
    :param float r: Radius
    :return: A quadratic rational curve
    :rtype: Curve
    :raises ValueError: If radiusis not positive
    :raises ValueError: If theta is not in the range *[-2pi, 2pi]*
    """
    # error test input
    if abs(theta) > 2 * pi:
        raise ValueError('theta needs to be in range [-2pi,2pi]')
    if r <= 0:
        raise ValueError('radius needs to be positive')

    # build knot vector
    knot_spans = int(ceil(theta / (2 * pi / 3)))
    knot = [0]
    for i in range(knot_spans + 1):
        knot += [i] * 2
    knot += [knot_spans]  # knot vector [0,0,0,1,1,2,2,..,n,n,n]
    knot = np.array(knot) / float(knot[-1]) * theta  # set parametic space to [0,theta]

    n = (knot_spans - 1) * 2 + 3  # number of control points needed
    cp = []
    t = 0  # current angle
    dt = float(theta) / knot_spans / 2  # angle step

    # build control points
    for i in range(n):
        w = 1 - (i % 2) * (1 - cos(dt))  # weights = 1 and cos(dt) every other i
        x = r * cos(t)
        y = r * sin(t)
        cp += [[x, y, w]]
        t += dt

    result = Curve(BSplineBasis(3, knot), cp, True)
    return flip_and_move_plane_geometry(result, center, normal)

def interpolate(x, basis, t=None):
    """Perform general spline interpolation on a provided basis.

    :param matrix-like x: Matrix *X[i,j]* of interpolation points *xi* with
        components *j*
    :param BSplineBasis basis: Basis on which to interpolate
    :param array-like   t    : parametric values at interpolation points, defaults
                               to greville points if not provided
    :return: Interpolated curve
    :rtype: Curve
    """
    # wrap x into a numpy matrix
    x = np.matrix(x)

    # evaluate all basis functions in the interpolation points
    if t is None:
        t = basis.greville()
    N = basis.evaluate(t)

    # solve interpolation problem
    controlpoints = np.linalg.solve(N, x)

    return Curve(basis, controlpoints)

def least_square_fit(x, basis, t):
    """Perform a least-square fit of a point cloud onto a spline basis

    :param matrix-like x: Matrix *X[i,j]* of interpolation points *xi* with
        components *j*. The number of points must be equal to or larger than
        the number of basis functions in *basis*
    :param BSplineBasis basis: Basis on which to interpolate
    :param array-like   t    : parametric values at evaluation points
    :return: Approximated curve
    :rtype: Curve
    """
    # wrap x into a numpy matrix
    x = np.matrix(x)

    # evaluate all basis functions at evaluation points
    N = basis.evaluate(t)

    # solve interpolation problem
    controlpoints,_,_,_ = np.linalg.lstsq(N, x)

    return Curve(basis, controlpoints)


def cubic_curve(x, boundary=FREE, t=None, tangents=None):
    """Perform cubic spline interpolation on a provided basis.

    :param matrix-like x: Matrix *X[i,j]* of interpolation points *xi* with
        components *j*
    :param int boundary: FREE, NATURAL, HERMITE, PERIODIC, TANGENT or TANGENTNATURAL
    :param array-like t: parametric values at interpolation points, defaults
        to euclidian distance between evaluation points
    :param matrix-like tangents: In case of HERMITE or TANGENT boundary
        condtions, one must supply tangent information (two points for TANGENT,
        n points for HERMITE)
    :return: Interpolated curve
    :rtype: Curve
    """
    n = len(x)
    if t is None:
        t = [0]
        for (x0,x1) in zip(x[:-1,:], x[1:,:]):
            # eucledian distance between two consecutive points 
            dist = np.linalg.norm(np.array(x1)-np.array(x0))
            t.append(t[i-1]+dist)

    # modify knot vector for chosen boundary conditions
    knot = [t[0]]*3 + list(t) + [t[-1]]*3
    if boundary == FREE:
        del knot[-5]
        del knot[4]
    elif boundary == HERMITE:
        knot = sorted(knot + t[1:-1])

    # create the interpolation basis and interpolation matrix on this
    if boundary == PERIODIC:
        knot[0]  = t[-3] - t[-1]
        knot[1]  = t[-2] - t[-1]
        knot[-2] = t[-1] + t[1]
        knot[-1] = t[-1] + t[2]
        basis = BSplineBasis(4, knot, 1)
    else:
        basis = BSplineBasis(4, knot)
    N = basis(t)  # left-hand-side matrix

    # add derivative boundary conditions if applicable
    if boundary==TANGENT or boundary==HERMITE or boundary==TANGENTNATURAL:
        if boundary == TANGENT:
            dn = basis([t[0], t[-1]], d=1)
            N  = np.resize(N, (N.shape[0]+2, N.shape[1]))
            x  = np.resize(x, (x.shape[0]+2, x.shape[1]))
            x[n:,:] = tangents 
        elif boundary == TANGENTNATURAL:
            dn = basis(t[0], d=1)
            N  = np.resize(N, (N.shape[0]+1, N.shape[1]))
            x  = np.resize(x, (x.shape[0]+1, x.shape[1]))
        elif boundary == HERMITE:
            dn = getBasis(t, d=1)
            N  = np.resize(N, (N.shape[0]+n, N.shape[1]))
            x  = np.resize(x, (x.shape[0]+n, x.shape[1]))
            x[n:,:] = tangents 
        N[n:,:] = dn

    # add double derivative boundary conditions if applicable
    if boundary == NATURAL or boundary == TANGENTNATURAL:
        if boundary == NATURAL:
            ddn  = basis([t[0], t[-1]], d=2)
            new  = 2
        elif boundary == TANGENTNATURAL:
            ddn  = basis(t[-1], d=2)
            new  = 1
        N  = np.resize(N, (N.shape[0]+new, N.shape[1]))
        x  = np.resize(x, (x.shape[0]+new, x.shape[1]))
        N[-new:,:] = ddn
        x[-new:,:] = 0

    # solve system to get controlpoints
    cp = np.linalg.solve(N,x)

    # wrap it all into a curve and return
    return Curve(basis, cp)

