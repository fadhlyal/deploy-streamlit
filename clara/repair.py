'''
Repair algorithm
'''

# Python imports
import sys
import time

# External libs
from zss import Node, simple_distance as tree_distance

# clara imports
from .common import debug, equals
from .interpreter import RuntimeErr, isundef
from .model import isprimed, unprime, prime
from .model import SPECIAL_VARS, VAR_IN, VAR_OUT, VAR_RET
from .model import Var, Const, Op
from .matching import Matching


class StructMismatch(Exception):
    pass


class Timeout(Exception):
    pass


def unprimes(x):
    return unprime(x) if isprimed(x) else x


def label_dist(m):

    def f(l1, l2):
        if not l1:
            return 0 if (not l2) else 1
        if not l2:
            return 0 if (not l1) else 1

        (t1, v1) = l1
        (t2, v2) = l2

        if t1 != t2:
            return 1

        if t2 == 'V':
            if isprimed(v2):
                v2 = prime(m.get(unprime(v2), 'X'))
            else:
                v2 = m.get(v2, 'X')

        return 0 if v1 == v2 else 1
    
    return f

class RepairResult(object):

    def __init__(self):
        self.loc1 = None
        self.var1 = None
        self.var2 = None
        self.cost = None
        self.order = None
        self.expr1 = None
        self.expr1_orig = None

    def __repr__(self):
        return '%s-%s %s (%s)' % (self.loc1, self.var1, self.var2,
                                  self.cost)

class Repair(object):

    def __init__(self, timeout=60, verbose=False, solver=None,
                 allowsuboptimal=True, cleanstrings=False):
        self.starttime = None
        self.timeout = timeout
        self.verbose = verbose
        self.cleanstrings = cleanstrings

        if solver is None:
            from .ilp import Solver
            solver = Solver
        self.solver = solver(verbose=verbose, allowsuboptimal=allowsuboptimal)

    def lefttime(self):
        if not self.timeout:
            return 365 * (24 * 3600)  # A year
        return self.timeout - (time.time() - self.starttime)
                   
    def debug(self, msg, *args):
        if not self.verbose:
            return
        debug(msg, *args)

    def gettrace(self, P, inter, ins, args, entryfnc):

        # Check inputs and arguments
        assert ins or args, "Inputs or argument required"
        if ins:
            assert isinstance(ins, list), "List of inputs expected"
        if args:
            assert isinstance(args, list), "List of arguments expected"

        if ins and args:
            assert len(ins) == len(args), \
                "Equal number of inputs and arguments expected"

        # Populate ins or args (whichever may be missing)
        if not ins:
            ins = [None for _ in range(len(args))]
        if not args:
            args = [None for _ in range(len(ins))]

        I = inter(entryfnc=entryfnc)
        T = {}
        for i, a in zip(ins, args):
            t = I.run(P, ins=i, args=a)

            # Split trace w.r.t. fncs and locs
            for (fnc, loc, mem) in t:
                if fnc not in T:
                    T[fnc] = {}
                if loc not in T[fnc]:
                    T[fnc][loc] = []
                T[fnc][loc].append(mem)

        return T
    
    def repair(self, P, Q, inter, ins=None, args=None, entryfnc=None,
               ignoreio=False, ignoreret=False):

        self.starttime = time.time()

        self.vignore = set()
        if ignoreio:
            self.vignore |= set([VAR_IN, VAR_OUT])

        # (1) Check struct match
        M = Matching(verbose=self.verbose)
        self.sm = M.match_struct(P, Q)
        if self.sm is None:
            raise StructMismatch('')

        # (2) Obtain trace of P
        self.trace = self.gettrace(P, inter, ins, args, entryfnc)

        # (3) Repair each fnc sepearately
        self.inter = inter()
        results = {}
        for fnc1 in P.getfncs():
            fnc2 = Q.getfnc(fnc1.name)
            results[fnc1.name] = (self.repair_fnc(fnc1, fnc2) +
                                  (self.sm[fnc1.name],))

        self.debug('total time: %.3f', round(time.time() - self.starttime, 3))

        return results

    def filter_potential(self, P):
        for loc1 in P:
            for var1 in P[loc1]:
                totalcost = 0
                newp = []
                for (m, cost, order, _) in sorted(P[loc1][var1],
                                                  key=lambda x: x[1]):
                    totalcost += cost
                    
                if totalcost == 0:
                    self.debug('removing %s-%s from P, due to total cost 0',
                               loc1, var1)
                    P[loc1][var1] = []

    def repair_fnc(self, f1, f2):

        # Remember params mapping
        self.pmap = {p1: p2 for (p1, p2) in zip(f1.getparamnames(),
                                                f2.getparamnames())}

        P = {}
        pgenstart = time.time()
        # (1) Generate "potential" sets
        self.V1 = (f1.getvars() | SPECIAL_VARS | set(['-'])) - self.vignore
        self.V2 = (f2.getvars() | SPECIAL_VARS | set(['*'])) - self.vignore
        self.getexprs(f1, f2)
        for loc1 in f1.locs():
            loc2 = self.sm[f1.name][loc1]
            P[loc1] = {}
            for var1 in self.V1 | set(['-']):
                self.debug('Generating P for %s-%s', loc1, var1)
                tptime = time.time()
                P[loc1][var1] = list(self.potential(f1, f2, loc1, var1, loc2))
                if self.verbose:
                    assert var1 == '-' or len(P[loc1][var1]) > 0, \
                        '%s,%s' % (loc1, var1)
                    for (m, cost, order, _) in P[loc1][var1]:
                        self.debug('P %s-%s-%s %s %s %s',
                                   f1.name, loc1, var1, cost, m, order)
                    self.debug('P for %s-%s generated in %.3fs',
                               loc1, var1, round(time.time() - tptime, 3))
        self.filter_potential(P)
        self.pgentime = time.time() - pgenstart

        # (2) Give "potential" sets to a solver
        solvertime = self.lefttime()
        res = self.solver.solve(self.V1 | set(['-']), self.V2 | set(['*']), P,
                                timeout=solvertime)
        # Retreive expressions used in repair
        ress = []
        for rep in res[1]:
            (loc1, var1, var2, cost, order, idx) = rep
            repobj = RepairResult()
            repobj.loc1 = loc1
            repobj.var1 = var1
            repobj.var2 = var2
            repobj.cost = cost
            repobj.order = order
            if idx is None:
                repobj.expr1 = self.E1[loc1][var1]
            else:
                repobj.expr1 = self.ER[loc1][var1][idx][0]
                repobj.expr1_orig = self.ER[loc1][var1][idx][1]
            ress.append(repobj)
        res = (res[0], ress)
            
        self.debug('PGEN time: %.3f' % round(self.pgentime, 3))
        self.debug('mapping: %s', res[0])
        self.debug('repairs: %s', res[1])
        return res

    def getexprs(self, f1, f2):

        self.E1 = {}
        self.T1 = {}
        for loc1 in f1.locs():
            self.E1[loc1] = {}
            self.T1[loc1] = {}
            for var1 in self.V1:
                self.E1[loc1][var1] = f1.getexpr(loc1, var1)
                self.T1[loc1][var1] = self.totree(self.E1[loc1][var1])
                if self.verbose:
                    self.debug('T1 %s-%s-%s := %s', f1.name, loc1, var1,
                               self.treetostr(self.T1[loc1][var1]))

        self.E2 = {}
        self.T2 = {}
        for loc2 in f2.locs():
            self.E2[loc2] = {}
            self.T2[loc2] = {}
            for var2 in self.V2:
                self.E2[loc2][var2] = f2.getexpr(loc2, var2)
                self.T2[loc2][var2] = self.totree(self.E2[loc2][var2])
                if self.verbose:
                    self.debug('T2 %s-%s-%s := %s', f2.name, loc2, var2,
                               self.treetostr(self.T2[loc2][var2]))

        hasrep = hasattr(f1, 'repair_exprs')
        self.ER = {}
        self.TR = {}
        for loc1 in f1.locs():
            self.ER[loc1] = {}
            self.TR[loc1] = {}
            for var1 in self.V1:
                if (hasrep and loc1 in f1.repair_exprs
                    and var1 in f1.repair_exprs[loc1]):
                    
                    self.ER[loc1][var1] = []
                    self.TR[loc1][var1] = []
                    for expr in f1.repair_exprs[loc1][var1]:
                        self.ER[loc1][var1].append((expr, expr.src))
                        self.TR[loc1][var1].append(self.totree(expr))
                else:
                    self.ER[loc1][var1] = [(self.E1[loc1][var1], None)]
                    self.TR[loc1][var1] = [self.T1[loc1][var1]]

    def totree(self, e):
        if isinstance(e, Var):
            return Node(('V', str(e)))
        if isinstance(e, Const):
            return Node(('C', str(e)))
        if isinstance(e, Op):
            name = e.name
            if name == 'AssAdd':
                name = 'Ass'
            n = Node(('O', name))
            for arg in e.args:
                n.addkid(self.totree(arg))
            return n

    def treetostr(self, node):
        l = Node.get_label(node)
        t = None
        if isinstance(l, tuple):
            t, l = l
        if t == 'O':
            return '%s(%s)' % (l, ', '.join(
                map(self.treetostr, Node.get_children(node))))
        return l

    def distance(self, t1, t2, m):
        return tree_distance(t1, t2, label_dist=label_dist(m))

    def one_to_ones(self, S1, S2, m1, m2, taken=None):

        if self.lefttime() < 0:
            raise Timeout()

        if taken is None:
            taken = set()

        if len(S1) == 0 or len(S2) == len(taken):
            yield []
            return

        s1, SS1 = S1[0], S1[1:]

        for s2 in S2:

            if s2 in taken:
                continue
                
            if s1 == m1 and s2 != m2:
                continue

            if s2 != '*' and s2 == m2 and s1 != m1:
                continue

            if (s1 in SPECIAL_VARS or s2 in SPECIAL_VARS) and s1 != s2:
                continue

            if s2 != '*':
                if s1.startswith('ind#') != s2.startswith('ind#'):
                    continue

                if s1.startswith('iter#') != s2.startswith('iter#'):
                    continue

            if ((s1 in self.pmap or s2 in list(self.pmap.keys()))
                and s2 != self.pmap.get(s1)):
                continue

            if s2 == '*':
                newtaken = taken
            else:
                newtaken = set(taken)
                newtaken.add(s2)

            for m in self.one_to_ones(SS1, S2, m1, m2, newtaken):
                m = list(m)
                m.append((s1, s2))
                yield m

    def getorder(self, var, expr, m):
        if var == '*' or var in SPECIAL_VARS:
            return []
        vars = expr.vars()
        order = []
        for var2 in vars:
            if isprimed(var2):
                var2 = unprime(var2)
                var2 = m[var2]
                if var2 == '*':
                    continue
                if var == var2:
                    return None
                order.append((var2, var))
            else:
                var2 = m[var2]
                if var2 == '*':
                    continue
                if var != var2 and var2 != '*':
                    order.append((var, var2))
        order.sort()
        return order

    def potential(self, f1, f2, loc1, var1, loc2):

        varp1 = prime(var1)
        expr1 = self.E1[loc1][var1]
        isid = (isinstance(expr1, Var) and expr1.name == var1
                and expr1.primed == False)
        tree1 = self.T1[loc1][var1]
        vars1 = list(set(map(unprimes, expr1.vars())) | set([var1]))
        vars1.sort()
        
        V1 = list(self.V1 - set(['-']))
        V1.sort()
        V2 = list(self.V2)
        V2.sort()
        
        for var2 in V2:

            sofar = set()

            # Special vars can be only mapped to special vars
            if (var1 in SPECIAL_VARS or var2 in SPECIAL_VARS) and var1 != var2:
                continue

            # other special variables
            if var2 != '*':
                if var1.startswith('ind#') != var2.startswith('ind#'):
                    continue
                if var1.startswith('iter#') != var2.startswith('iter#'):
                    continue

            # Params can only be mapped to params
            if ((var1 in self.pmap or var2 in list(self.pmap.keys()))
                and var2 != self.pmap.get(var1)):
                continue

            # Cannot delete new variable
            if var1 == '-' and var2 == '*':
                continue

            expr2 = self.E2[loc2][var2]
            tree2 = self.T2[loc2][var2]
            vars2 = list(set(map(unprimes, expr2.vars())) | set([var2]))
            vars2.sort()

            # (0) Deletes are special
            if var1 == '-':
                delexpr = Var(var2)
                deltree = self.totree(delexpr)
                delcost = self.distance(tree2, deltree, {var2: var2})
                if delcost:
                    yield ([(var1, var2)], delcost, (), None)
                continue

            # (1) Generate corrects (if not new variable)
            if var2 != '*':
                for m in self.one_to_ones(vars2, V1, var2, var1):
                    m = [(s2, s1) for (s1, s2) in m]
                    ok = True
                    for mem1 in self.trace.get(f1.name, {}).get(loc1, []):
                        val1 = mem1.get(varp1)
                        
                        if isundef(val1) and (var1 != VAR_RET):
                            continue
                        
                        if isinstance(val1, str) and self.cleanstrings:
                            val1 = val1.strip()
                            
                        mem2 = {v2: mem1.get(v1) for (v1, v2) in m}
                        mem2.update({prime(v2): mem1.get(prime(v1))
                                     for (v1, v2) in m})
                        try:
                            val2 = self.inter.execute(expr2, mem2)
                            if isinstance(val2, str) and self.cleanstrings:
                                val2 = val2.strip()

                            if not equals(val2, val1):
                                ok = False
                                break
                        except RuntimeErr:
                            ok = False
                            break
                    if ok:
                        order = self.getorder(var2, expr2,
                                              {v: v for v in vars2})
                        if order is None:
                            assert False, 'order error %s %s' % (var2, expr2)
                        ms = list(m)
                        ms.sort()
                        sofar.add((tuple(ms), tuple(order)))
                        yield (m, 0, set(order), None)

            # (2) Generate repairs
            tmprepairs = {}
            #for rexpr, rtree in zip([self.E1[loc1][var1]], [self.T1[loc1][var1]]):
            for idx, ((rexpr, _), rtree) in enumerate(zip(self.ER[loc1][var1], self.TR[loc1][var1])):
                
                risid = (isinstance(rexpr, Var) and rexpr.name == var1
                        and rexpr.primed == False)
                rvars = list(set(map(unprimes, rexpr.vars())) | set([var1]))
                
                for m in self.one_to_ones(rvars, V2, var1, var2):
                    order = self.getorder(var2, rexpr, dict(m))
                    
                    if order is None:
                        self.debug(
                            'skipping repair %s := %s (%s) because impossible order',
                            var1, expr1, m)
                        continue
                    
                    if risid and var2 == '*':
                        cost = 0
                    else:
                        cost = self.distance(tree2, rtree, dict(m))
                    
                    # Account for *declaring* a new variable
                    if var2 == '*' and loc1 == 1:
                        cost += 1
                
                    ms = list(m)
                    ms.sort()

                    tms = tuple(ms)
                    torder = tuple(order)
                
                    if (tms, torder) in sofar:
                        continue

                    # From each 'm'-'order' pair we first remember all pairs
                    # and later yield only the one with the smallest cost
                    # since other ones have no sense
                    tmp = (tms, torder)
                    if tmp not in tmprepairs:
                        tmprepairs[tmp] = []
                    tmprepairs[tmp].append((cost, (m, cost, set(order), idx)))

                    #yield (m, cost, set(order))
                
            for treps in list(tmprepairs.values()):
                treps.sort()
                #print treps[0][1]
                yield treps[0][1]
