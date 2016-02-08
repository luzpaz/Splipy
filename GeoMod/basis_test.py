# -*- coding: utf-8 -*-

from GeoMod import BSplineBasis
import numpy as np
import unittest

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


class TestBasis(unittest.TestCase):
    def test_get_continuity(self):
        b = BSplineBasis(4, [0, 0, 0, 0, .3, 1, 1, 1.134, 1.134, 1.134, 2, 2, 2, 2])
        self.assertEqual(b.continuity(.3), 2)
        self.assertEqual(b.continuity(1), 1)
        self.assertEqual(b.continuity(1.134), 0)
        self.assertEqual(b.continuity(0), -1)
        self.assertEqual(b.continuity(2), -1)
        self.assertEqual(b.continuity(.4), np.inf)

    def test_errors(self):
        with self.assertRaises(ValueError):
            BSplineBasis(4, [1, 2, 3])
        with self.assertRaises(ValueError):
            BSplineBasis(4, [1, 2, 4, 8], periodic=1)
        with self.assertRaises(ValueError):
            BSplineBasis(4, [1, 2, 3, 7, 8], periodic=2)

    def test_greville(self):
        b = BSplineBasis(4, [0, 0, 0, 0, 1, 2, 3, 3, 3, 3])
        self.assertAlmostEqual(b.greville(0), 0.0)
        self.assertAlmostEqual(b.greville(1), 1.0 / 3.0)
        self.assertAlmostEqual(b.greville(2), 1.0)
        self.assertAlmostEqual(b.greville(), [0.0, 1.0/3.0, 1.0, 2.0, 8.0/3.0, 3.0])

    def test_raise_order(self):
        with self.assertRaises(ValueError):
            BSplineBasis().raise_order(-1)

    def test_write_g2(self):
        buf = StringIO()
        BSplineBasis(3, [0,0,0,1,2,3,3,3]).write_g2(buf)
        self.assertEqual(buf.getvalue().strip(),
                         '5 3\n0.000000 0.000000 0.000000 1.000000 2.000000 '
                         '3.000000 3.000000 3.000000')

    def test_getitem(self):
        b = BSplineBasis(3, [0,0,0,1,2,2,2])
        self.assertEqual(b[0], 0.0)
        self.assertEqual(b[1], 0.0)
        self.assertEqual(b[3], 1.0)

    def test_repr(self):
        self.assertEqual(repr(BSplineBasis()), 'p=2, [ 0.  0.  1.  1.]')
        self.assertEqual(repr(BSplineBasis(periodic=0)), 'p=2, [-1.  0.  1.  2.], C0-periodic')

    def test_roll(self):
        b = BSplineBasis(4, [-2, -1, -1, 0, 2, 4, 6.5, 7, 8, 8, 9, 11, 13, 15.5], periodic=2)
        b.roll(3)
        self.assertEqual(len(b.knots), 14)
        self.assertAlmostEqual(b.knots[0], 0)
        self.assertAlmostEqual(b.knots[1], 2)
        self.assertAlmostEqual(b.knots[2], 4)
        self.assertAlmostEqual(b.knots[3], 6.5)
        self.assertAlmostEqual(b.knots[4], 7)
        self.assertAlmostEqual(b.knots[5], 8)
        self.assertAlmostEqual(b.knots[6], 8)
        self.assertAlmostEqual(b.knots[7], 9)
        self.assertAlmostEqual(b.knots[8], 11)
        self.assertAlmostEqual(b.knots[9], 13)
        self.assertAlmostEqual(b.knots[10], 15.5)
        self.assertAlmostEqual(b.knots[11], 16)
        self.assertAlmostEqual(b.knots[12], 17)
        self.assertAlmostEqual(b.knots[13], 17)

    def test_integrate(self):
        # create the linear functions x(t) = [1-t, t] on t=[0,1]
        b = BSplineBasis()
        self.assertAlmostEqual(b.integrate(0,1)[0], 0.5)
        self.assertAlmostEqual(b.integrate(0,1)[1], 0.5)
        self.assertAlmostEqual(b.integrate(.25,.5)[0], 5.0/32)
        self.assertAlmostEqual(b.integrate(.25,.5)[1], 3.0/32)

        # create the quadratic functions x(t) = [(1-t)^2, 2t(1-t), t^2] on t=[0,1]
        b = BSplineBasis(3)
        self.assertAlmostEqual(b.integrate(0,1)[0], 1.0/3)
        self.assertAlmostEqual(b.integrate(0,1)[1], 1.0/3)
        self.assertAlmostEqual(b.integrate(0,1)[2], 1.0/3)
        self.assertAlmostEqual(b.integrate(.25,.5)[0], 19.0/192)
        self.assertAlmostEqual(b.integrate(.25,.5)[1], 11.0/96)
        self.assertAlmostEqual(b.integrate(.25,.5)[2], 7.0/192)

        # create periodic quadratic functions on [0,3]. This is 3 functions, which are all
        # translated versions of the one below:
        #        | 1/2 t^2          t=[0,1]
        # N[3] = { -t^2 + 3t - 3/2  t=[1,2]
        #        | 1/2 (3-t)^2      t=[2,3]
        b = BSplineBasis(3, [-2,-1,0,1,2,3,4,5], periodic=1)
        self.assertEqual(len(b.integrate(0,3)), 3) # returns 3 functions
        self.assertAlmostEqual(b.integrate(0,3)[0], 1)
        self.assertAlmostEqual(b.integrate(0,3)[1], 1)
        self.assertAlmostEqual(b.integrate(0,3)[2], 1)
        self.assertAlmostEqual(b.integrate(0,1)[0], 1.0/6)
        self.assertAlmostEqual(b.integrate(0,1)[1], 2.0/3)
        self.assertAlmostEqual(b.integrate(0,1)[2], 1.0/6)
        self.assertAlmostEqual(b.integrate(0,2)[0], 2.0/6)
        self.assertAlmostEqual(b.integrate(0,2)[1], 5.0/6)
        self.assertAlmostEqual(b.integrate(0,2)[2], 5.0/6)

if __name__ == '__main__':
    unittest.main()
