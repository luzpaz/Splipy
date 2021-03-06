# -*- coding: utf-8 -*-

from splipy import BSplineBasis, Curve, SplineObject
from splipy.utils import ensure_listlike, check_direction, sections
from bisect import bisect_left
from itertools import chain
import numpy as np

__all__ = ['Surface']


class Surface(SplineObject):
    """Surface()

    Represents a surface: an object with a two-dimensional parameter space."""

    _intended_pardim = 2

    def __init__(self, basis1=None, basis2=None, controlpoints=None, rational=False, **kwargs):
        """__init__([basis1=None], [basis2=None], [controlpoints=None], [rational=False])

        Construct a surface with the given basis and control points.

        The default is to create a linear one-element mapping from and to the
        unit square.

        :param BSplineBasis basis1: The basis of the first parameter direction
        :param BSplineBasis basis2: The basis of the second parameter direction
        :param array-like controlpoints: An *n1* × *n2* × *d* matrix of control points
        :param bool rational: Whether the surface is rational (in which case the
            control points are interpreted as pre-multiplied with the weight,
            which is the last coordinate)
        """
        super(Surface, self).__init__([basis1, basis2], controlpoints, rational, **kwargs)

    def normal(self, u, v):
        """Evaluate the normal of the surface at given parametric values.

        This is equal to the cross-product between tangents. The return value
        is **not** normalized.

        :param u: Parametric coordinate(s) in the first direction
        :type u: float or [float]
        :param v: Parametric coordinate(s) in the second direction
        :type v: float or [float]
        :return: Normal array *X[i,j,k]* of component *xj* evaluated at *(u[i], v[j])*
        :rtype: numpy.array
        :raises RuntimeError: If the physical dimension is not 2 or 3
        """
        if self.dimension == 2:
            try:
                result = np.zeros((len(u), len(v), 3))
                result[:, :, 2] = 1
                return result
            except TypeError:  # single valued input u, fails on len(u)
                return np.array([0, 0, 1])
        elif self.dimension == 3:
            (du, dv) = self.tangent(u, v)
            result = np.zeros(du.shape)
            # the cross product of the tangent is the normal
            if len(du.shape) == 1:
                result[0] = du[1] * dv[2] - du[2] * dv[1]
                result[1] = du[2] * dv[0] - du[0] * dv[2]
                result[2] = du[0] * dv[1] - du[1] * dv[0]
            else:  # grid evaluation
                result[:, :, 0] = du[:, :, 1] * dv[:, :, 2] - du[:, :, 2] * dv[:, :, 1]
                result[:, :, 1] = du[:, :, 2] * dv[:, :, 0] - du[:, :, 0] * dv[:, :, 2]
                result[:, :, 2] = du[:, :, 0] * dv[:, :, 1] - du[:, :, 1] * dv[:, :, 0]
            return result
        else:
            raise RuntimeError('Normal evaluation only defined for 2D and 3D geometries')

    def area(self):
        """ Computes the area of the surface in geometric space """
        # fetch integration points
        (x1,w1) = np.polynomial.legendre.leggauss(self.order(0)+1)
        (x2,w2) = np.polynomial.legendre.leggauss(self.order(1)+1)
        # map points to parametric coordinates (and update the weights)
        (knots1,knots2) = self.knots()
        u  = np.array([ (x1+1)/2*(t1-t0)+t0 for t0,t1 in zip(knots1[:-1], knots1[1:]) ])
        w1 = np.array([     w1/2*(t1-t0)    for t0,t1 in zip(knots1[:-1], knots1[1:]) ])
        v  = np.array([ (x2+1)/2*(t1-t0)+t0 for t0,t1 in zip(knots2[:-1], knots2[1:]) ])
        w2 = np.array([     w2/2*(t1-t0)    for t0,t1 in zip(knots2[:-1], knots2[1:]) ])

        # wrap everything to vectors
        u = np.ndarray.flatten(u)
        v = np.ndarray.flatten(v)
        w1 = np.ndarray.flatten(w1)
        w2 = np.ndarray.flatten(w2)

        # compute all quantities of interest (i.e. the jacobian)
        du = self.derivative(u,v, d=(1,0))
        dv = self.derivative(u,v, d=(0,1))
        J  = np.cross(du,dv)

        if self.dimension == 3:
            J = np.sqrt(np.sum(J**2, axis=2))
        else:
            J = np.abs(J)
        return w1.dot(J).dot(w2)

    def edges(self):
        """Return the four edge curves in (parametric) order: umin, umax, vmin, vmax

        :return: Edge curves
        :rtype: (Curve)
        """
        return tuple(self.section(*args) for args in sections(2, 1))

    def const_par_curve(self, knot, direction):
        """Get a Curve representation of the parametric line of some constant 
        knot value."""
        direction = check_direction(direction, 2)
        
        # clone basis since we need to augment this by knot insertion
        b    = self.bases[direction].clone()

        # compute mapping matrix C which is the knotinsertion operator
        mult = min(b.continuity(knot), b.order-1)
        C    = np.matrix(np.identity(self.shape[direction]))
        for i in range(mult):
            C = b.insert_knot(knot) * C

        # at this point we have a C0 basis, find the right interpolating index
        i  = max(bisect_left(b.knots, knot) - 1,0) 

        # compute the controlpoints and return Curve
        cp = np.tensordot(C[i,:], self.controlpoints, axes=(1, direction))
        return Curve(self.bases[1-direction], cp, self.rational)

    def split(self, knots, direction):
        """Split a surface into two or more separate representations with C0
        continuity between them.

        :param int direction: The parametric direction to split in
        :param knots: The splitting points
        :type knots: float or [float]
        :return: The new surfaces
        :rtype: [Surface]
        """
        # for single-value input, wrap it into a list
        knots = ensure_listlike(knots)
        # error test input
        direction = check_direction(direction, 2)

        p = self.order()
        results = []
        splitting_surf = self.clone()
        basis = self.bases
        # insert knots to produce C{-1} at all splitting points
        for k in knots:
            continuity = basis[direction].continuity(k)
            if continuity == np.inf:
                continuity = p[direction] - 1
            splitting_surf.insert_knot([k] * (continuity + 1), direction)

        b = splitting_surf.bases[direction]
        if b.periodic > -1:
            mu = bisect_left(b.knots, knots[0])
            b.roll(mu)
            splitting_surf.controlpoints = np.roll(splitting_surf.controlpoints, -mu, direction)
            b.knots = b.knots[:-b.periodic-1]
            b.periodic = -1
            if len(knots) > 1:
                return splitting_surf.split(knots[1:], direction)
            else:
                return splitting_surf


        # everything is available now, just have to find the right index range
        # in the knot vector and controlpoints to store in each separate curve
        # piece
        last_cp_i = 0
        last_knot_i = 0
        (n1, n2, dim) = splitting_surf.controlpoints.shape
        if direction == 0:
            for k in knots:
                mu = bisect_left(splitting_surf.bases[0].knots, k)
                n_cp = mu - last_knot_i
                basis = BSplineBasis(p[0], splitting_surf.bases[0].knots[last_knot_i:mu + p[0]])
                cp = splitting_surf.controlpoints[last_cp_i:last_cp_i + n_cp, :, :]
                cp = np.reshape(cp.transpose((1, 0, 2)), (n_cp * n2, dim))

                results.append(Surface(basis, self.bases[1], cp, self.rational))
                last_knot_i = mu
                last_cp_i += n_cp

            # with n splitting points, we're getting n+1 pieces. Add the final one:
            basis = BSplineBasis(p[0], splitting_surf.bases[0].knots[last_knot_i:])
            n_cp = basis.num_functions()
            cp = splitting_surf.controlpoints[last_cp_i:, :, :]
            cp = np.reshape(cp.transpose((1, 0, 2)), (n_cp * n2, dim))
            results.append(Surface(basis, self.bases[1], cp, self.rational))
        else:
            for k in knots:
                mu = bisect_left(splitting_surf.bases[1].knots, k)
                n_cp = mu - last_knot_i
                basis = BSplineBasis(p[1], splitting_surf.bases[1].knots[last_knot_i:mu + p[1]])
                cp = splitting_surf.controlpoints[:, last_cp_i:last_cp_i + n_cp, :]
                cp = np.reshape(cp.transpose((1, 0, 2)), (n_cp * n1, dim))

                results.append(Surface(self.bases[0], basis, cp, self.rational))
                last_knot_i = mu
                last_cp_i += n_cp
            # with n splitting points, we're getting n+1 pieces. Add the final one:
            basis = BSplineBasis(p[1], splitting_surf.bases[1].knots[last_knot_i:])
            n_cp = basis.num_functions()
            cp = splitting_surf.controlpoints[:, last_cp_i:, :]
            cp = np.reshape(cp.transpose((1, 0, 2)), (n_cp * n1, dim))
            results.append(Surface(self.bases[0], basis, cp, self.rational))

        return results

    def rebuild(self, p, n):
        """Creates an approximation to this surface by resampling it using
        uniform knot vectors of order *p* with *n* control points.

        :param int p: Polynomial discretization order
        :param int n: Number of control points
        :return: A new approximate surface
        :rtype: Surface
        """
        p = ensure_listlike(p, dups=2)
        n = ensure_listlike(n, dups=2)

        old_basis = self.bases
        basis = []
        u = []
        N = []
        # establish uniform open knot vectors
        for i in range(2):
            knot = [0] * p[i] + list(range(1, n[i] - p[i] + 1)) + [n[i] - p[i] + 1] * p[i]
            basis.append(BSplineBasis(p[i], knot))

            # make these span the same parametric domain as the old ones
            basis[i].normalize()
            t0 = old_basis[i].start()
            t1 = old_basis[i].end()
            basis[i] *= (t1 - t0)
            basis[i] += t0

            # fetch evaluation points and evaluate basis functions
            u.append(basis[i].greville())
            N.append(basis[i].evaluate(u[i]))

        # find interpolation points as evaluation of existing surface
        x = self.evaluate(u[0], u[1])

        # solve interpolation problem
        cp = np.tensordot(np.linalg.inv(N[1]), x, axes=(1, 1))
        cp = np.tensordot(np.linalg.inv(N[0]), cp, axes=(1, 1))

        # re-order controlpoints so they match up with Surface constructor
        cp = cp.transpose((1, 0, 2))
        cp = cp.reshape(n[0] * n[1], cp.shape[2])

        # return new resampled curve
        return Surface(basis[0], basis[1], cp)

    def __repr__(self):
        result = str(self.bases[0]) + '\n' + str(self.bases[1]) + '\n'
        # print legacy controlpoint enumeration
        n1, n2, n3 = self.controlpoints.shape
        for j in range(n2):
            for i in range(n1):
                result += str(self.controlpoints[i, j, :]) + '\n'
        return result

