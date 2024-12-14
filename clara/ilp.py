'''
ILP solver
'''

# Python imports
import time

# clara imports
from .common import debug
from .model import SPECIAL_VARS
from .pylpsolve import LpModel, EQ, LE, GE, TIMEOUT, SUBOPTIMAL, NUMFAILURE
from .repair import Timeout


class Solver(object):

    def __init__(self, verbose=None, timeout=None, allowsuboptimal=True):
        self.verbose = verbose
        self.timeout = timeout
        self.allowsuboptimal = allowsuboptimal

    def lefttime(self):
        if self.timeout is None:
            return 365 * (24 * 3600)  # A year :)
        return self.timeout - (time.time() - self.starttime)

    def varstodict(self):
        self.M1 = {}  # Map from V1 -> ints
        self.R1 = {}  # Map from ints -> V1
        for var1 in self.V1:
            self.M1[var1] = len(self.M1)
            self.R1[self.M1[var1]] = var1

        self.M2 = {}  # Map from V2 -> ints
        self.R2 = {}  # Map from ints -> V2
        for var2 in self.V2:
            self.M2[var2] = len(self.M2)
            self.R2[self.M2[var2]] = var2

        self.N1 = len(self.M1)
        self.N2 = len(self.M2)
        self.N = self.N1 * self.N2  # Number of variables

    def varstoint(self, var1, var2):
        return self.M1[var1] * self.N2 + self.M2[var2]

    def inttovars(self, n):
        return (self.R1[n // self.N2], self.R2[n % self.N2])

    def encode_onetoone(self):

        for var1 in self.V1:
            if var1 == '-':
                continue
            cv = {}
            for var2 in self.V2:
                v = self.varstoint(var1, var2)
                # Special vars are mapped to themselves
                if (var1 in SPECIAL_VARS) or (var2 in SPECIAL_VARS):
                    x = 1 if var1 == var2 else 0
                    self.C.append(({v: 1}, EQ, x))
                    continue
                cv[v] = 1
            # Eeach var1 is mapped to exactly one var2
            if cv:
                self.C.append((cv, EQ, 1))

        for var2 in self.V2:
            if var2 == '*':
                continue
            if var2 in SPECIAL_VARS:
                continue
            cv = {}
            for var1 in self.V1:
                if var1 in SPECIAL_VARS:
                    continue
                v = self.varstoint(var1, var2)
                cv[v] = 1
            # Each var2 is mapped to exactly one var1
            if cv:
                self.C.append((cv, EQ, 1))

    def conflicting_orders(self, o1, o2):
        for (u1, u2) in o1:
            if (u2, u1) in o2:
                return True
        for (u1, u2) in o2:
            if (u2, u1) in o1:
                return True
        return False

    def encode_P(self):
        maxcost = 0.0
        self.R = {}
        for loc1 in self.P:
            for var1 in self.P[loc1]:
                RV = {}  # All repairs for (loc1,var1)
                for m, cost, order, idx in self.P[loc1][var1]:
                    maxcost = max(maxcost, cost)
                    ri = self.N  # Variable denoting this repair
                    self.N += 1
                    var2 = var1 if var1 in SPECIAL_VARS else None
                    for (u1, u2) in m:
                        if u1 == var1:
                            var2 = u2
                        if var1 == '-':
                            # -ri + (u1,u2) == 0
                            # r1 <=> (u1,u2) (repair ri iff match(u1,u2))
                            self.C.append(({ri: -1, self.varstoint(u1, u2): 1},
                                           EQ, 0))
                        else:
                            # -ri + (u1,u2) >= 0
                            # ri => (u1,u2) (repair ri implies match (u1,u2))
                            self.C.append(({ri: -1, self.varstoint(u1, u2): 1},
                                           GE, 0))
                    RV[ri] = 1
                    if cost > 0:
                        self.O[ri] = float(cost)  # cost of r1
                    # Remember repair ri
                    self.R[ri] = (loc1, var1, var2, cost, order, idx)
                if len(RV) and var1 != '-':
                    # sum ri >= 1
                    # At least one ri for (loc1,var) should be chosen
                    self.C.append((RV, EQ, 1))

    def build_model(self):
        # Init model
        self.LP = LpModel(cols=self.N)
        if not self.verbose:
            self.LP.setverbose(1)

        # Bound variables
        for i in range(1, self.N + 1):
            self.LP.setint(i, 1)
            self.LP.setupbo(i, 1.0)

        # Set objective function
        self.LP.setobjfnex(self.O)

        # Add constrains
        self.LP.setaddrowmode(1)
        for (left, op, right) in self.C:
            self.LP.addconstraintex(left, op, right)
        self.LP.setaddrowmode(0)

    def solve_model(self, scaling=0):

        scalings = [4, 0, 1, 2, 3, 7]
        if self.verbose:
            debug('setting scaling=%d', scalings[scaling])
        self.LP.setscaling(scalings[scaling] | 64 | 128)

        self.LP.setbbrule(1)

        lefttime = max(0, int(self.lefttime()))
        if lefttime == 0:
            raise Timeout()
        if self.verbose:
            debug('solver timeout: %s', lefttime)
        self.LP.settimeout(lefttime)
        
        result = self.LP.solve()
        if result == 0:
            return
        elif result == SUBOPTIMAL:
            if self.verbose:
                debug('suboptimal solution!')
            if self.allowsuboptimal:
                return
            else:
                raise Timeout()
        elif result == TIMEOUT:
            raise Timeout()
        elif result == NUMFAILURE:
            if (scaling + 1) < len(scalings):
                return self.solve_model(scaling + 1)
        assert False, 'unexpected result: %s' % (result,)

    def add_conflicts(self, C):
        self.LP.setaddrowmode(1)
        for (r1, r2) in C:
            self.LP.addconstraintex({r1: 1, r2: 2}, LE, 1)
        self.LP.setaddrowmode(0)
        
    def decode_model(self):
        model = self.LP.getvariables()
        mapping = {}
        repairs = []
        orders = {}
        for i, v in enumerate(model):
            if v < 0.1:
                continue
            if i < self.N1 * self.N2:  # Variable mapping
                var1, var2 = self.inttovars(i)
                if var1 != '-':
                    assert var1 not in mapping, "%s already mapped" % (var1,)
                if var2 != '*':
                    assert var2 not in list(mapping.values()), \
                        "%s already mapped" % (var2,)
                mapping[var1] = var2
            else:
                (loc1, var1, var2, cost, order, idx) = r = self.R[i]
                if loc1 not in orders:
                    orders[loc1] = []
                orders[loc1].append((i, order))
                if cost == 0:
                    continue
                if var1 != '-':
                    assert mapping[var1] == var2, "mapping error"
                repairs.append(r)

        conflicts = []
        for loc in orders:
            for i, (r1, order1) in enumerate(orders[loc]):
                for r2, order2 in orders[loc][i + 1:]:
                    if self.conflicting_orders(order1, order2):
                        if self.verbose:
                            debug('found conflicting orders %s and %s',
                                  order1, order2)
                        conflicts.append((r1, r2))
        if conflicts:
            self.add_conflicts(conflicts)
            return None
        else:
            if self.verbose:
                debug('no ordering conflicts found')

        return mapping, repairs

    def solve(self, V1, V2, P, timeout=None):
        
        if timeout:
            self.timeout = timeout
        self.starttime = time.time()
            
        self.V1 = V1
        self.V2 = V2
        self.P = P

        self.varstodict()

        self.C = []  # Constraints
        self.O = {}  # Objective fnc

        otostart = time.time()
        self.encode_onetoone()
        self.ototime = time.time() - otostart
        
        if self.lefttime() <= 0:
            raise Timeout()

        pstart = time.time()
        self.encode_P()
        self.ptime = time.time() - pstart
        if self.lefttime() <= 0:
            raise Timeout()

        mstart = time.time()
        self.build_model()
        self.mtime = time.time() - mstart
        if self.lefttime() <= 0:
            raise Timeout()

        sstart = time.time()
        solve_rounds = 0
        result = None
        while result is None:
            self.solve_model()
            result = self.decode_model()
            solve_rounds += 1
        self.stime = time.time() - sstart

        if self.verbose:
            debug('OTO time: %.3f', round(self.ototime, 3))
            debug('P time: %.3f', round(self.ptime, 3))
            debug('M time: %.3f', round(self.mtime, 3))
            debug('S time: %.3f', round(self.stime, 3))
            debug('S rounds: %d', solve_rounds)
        
        return result

    def decodevar(self, n):
        if n < self.N1 * self.N2:
            return '%s~%s' % self.inttovars(n)
        else:
            return 'r%d' % (n,)

    def printM(self):
        for left, op, right in self.C:
            left = ['%s*%s' % (y, self.decodevar(x))
                    for (x, y) in list(left.items())]
            if op == EQ:
                op = '='
            elif op == GE:
                op = '>='
            elif op == LE:
                op = '<='
            print('%s %s %s' % (' + '.join(left), op, right))

        print()
        print('Objective: ')
        print(' + '.join('%s*%s' % (y, self.decodevar(x))
                         for (x, y) in list(self.O.items())))
