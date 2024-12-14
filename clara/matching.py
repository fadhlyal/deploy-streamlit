'''
Simulation relation
'''

# clara imports
from .common import debug, equals
from .interpreter import Interpreter, RuntimeErr, UndefValue, isundef
from .model import SPECIAL_VARS, VAR_RET, VAR_IN, VAR_OUT, isprimed, prime


class Matching(object):

    def __init__(self, ignoreio=False, ignoreret=False, verbose=False,
                 debugvar=None, bijective=True):

        self.ignoreio = ignoreio
        self.ignoreret = ignoreret

        self.bijective = bijective
        
        self.verbose = verbose
        self.debugvar = debugvar

    def debug(self, *args):
        if not self.verbose:
            return
        debug(*args)

    def match_mems(self, match, loc, mem1, mem2, V1, V2):

        #V2 = ({var2 for var2 in mem2.keys() if not isprimed(var2)}
        #      - SPECIAL_VARS)

        if self.bijective:
            if len(V1 | SPECIAL_VARS) != len(V2 | SPECIAL_VARS):
                self.debug('Not bijective - different number of variables')
                return False

        # Go through all variables
        for var1 in V1 | SPECIAL_VARS:

            # Ignored vars
            if self.ignoreret and var1 == VAR_RET:
                continue
            if self.ignoreio and var1 in [VAR_IN, VAR_OUT]:
                continue

            # If var1 not matched yet, build a list of potential matches
            if var1 not in match:
                if var1 in SPECIAL_VARS:
                    match[var1] = set([var1])
                else:
                    match[var1] = set(V2)

            # Check list of potential matches
            newmatch = set([])
            varp1 = prime(var1)
            for var2 in match[var1]:
                varp2 = prime(var2)

                if var1.startswith('ind#') != var2.startswith('ind#'):
                    continue

                if var1.startswith('iter#') != var2.startswith('iter#'):
                    continue

                # Get values
                val1 = mem1.get(varp1, UndefValue())
                val2 = mem2.get(varp2, UndefValue())

                # Debug vars
                if self.debugvar == '%s-%s' % (loc, var1):
                    self.debug('VAR %s = %s', var1, val1)
                    self.debug('VAR %s = %s', var2, val2)
                    if isundef(val1) or equals(val1, val2):
                        self.debug('VAR equal')
                    else:
                        self.debug('VAR unequal')
                    self.debug('')
                
                # Check if equal
                if isundef(val1) or equals(val1, val2):
                    newmatch.add(var2)

            # If no match for then done
            if len(newmatch) == 0:
                self.debug("Couldn find match for %s-%s", loc, var1)
                return False
            # Otherwise replace with new matches
            else:
                match[var1] = newmatch

        return True

    def one_to_one(self, match, taken=None):

        if len(match) == 0:
            return {}

        if taken is None:
            taken = set()

        var1, matches = match[0]

        for var2 in matches:
            if var2 in taken:
                continue
            
            newtaken = set(taken)
            newtaken.add(var2)

            m = self.one_to_one(match[1:], newtaken)
            if m is not None:
                m = dict(m)
                m[var1] = var2
                return m

    def match_traces(self, T1, T2, sm, V1, V2):

        # Check number of traces
        if len(T1) != len(T2):
            self.debug('Different number of traces (%d <> %d)',
                       len(T1), len(T2))
            return

        # Go through each trace
        match = {}
        for t1, t2 in zip(T1, T2):

            # Check length of traces
            if len(t1) != len(t2):
                self.debug('Different length of traces (%d <> %d)',
                           len(t1), len(t2))
                return

            for (fnc1, loc1, mem1), (fnc2, loc2, mem2) in zip(t1, t2):

                # Check if valid with struct match
                if fnc1 != fnc2:
                    return
                if sm[fnc1][loc1] != loc2:
                    return

                # Check memories
                if fnc1 not in match:
                    match[fnc1] = {}
                if not self.match_mems(match[fnc1], '%s-%s' % (fnc1, loc1),
                                       mem1, mem2, V1[fnc1], V2[fnc2]):
                    return

        # Debug matches
        for fnc in match:
            for var, m in list(match[fnc].items()):
                self.debug('matches for %s-%s: %s' % (fnc, var, m))

        # Construct one-to-one match
        newmatch = {}
        for fnc in sm:
            newmatch[fnc] = self.one_to_one(list(match.get(fnc, {}).items()))
            if newmatch[fnc] is None:
                self.debug("Couldn't find one-to-one match for '%s'", fnc)
                return
        return (sm, newmatch)

    def match_struct(self, P, Q):

        fncs1 = P.getfncnames()
        fncs2 = Q.getfncnames()

        # Go through all functions
        sm = {}
        
        for fnc2 in fncs2:
            if fnc2 not in fncs1:
                self.debug("Function '%s' not found in P", fnc2)
                return
            
        for fnc1 in fncs1:

            if fnc1 not in fncs2:
                self.debug("Function '%s' not found in Q", fnc1)
                return

            f1 = P.getfnc(fnc1)
            f2 = Q.getfnc(fnc1)

            # Compare structure of two functions
            def build_sm(loc1, loc2):

                # Check if already mapped
                if loc1 in sm[fnc1]:
                    return sm[fnc1][loc1] == loc2

                # Check if loc2 already mapped
                if loc2 in list(sm[fnc1].values()):
                    return False

                # Remember this pair
                sm[fnc1][loc1] = loc2

                # Check number of transitions
                n1 = f1.numtrans(loc1)
                n2 = f2.numtrans(loc2)
                if n1 != n2:
                    return False

                # Done
                if n1 == 0:
                    return True

                # Check True
                nloc1 = f1.trans(loc1, True)
                nloc2 = f2.trans(loc2, True)
                if not build_sm(nloc1, nloc2):
                    return False
                if n1 == 1:
                    return True

                # Check False
                nloc1 = f1.trans(loc1, False)
                nloc2 = f2.trans(loc2, False)
                return build_sm(nloc1, nloc2)

            # Start from initial locations
            sm[fnc1] = {}
            if not build_sm(f1.initloc, f2.initloc):
                return

        return sm
        
    def match_programs(self, P, Q, inter, ins=None, args=None,
                       entryfnc=None, timeout=5):

        # Check inputs and arguments
        assert ins or args, "Inputs or argument required"
        if ins:
            assert isinstance(ins, list), "List of inputs expected"
        if args:
            assert isinstance(args, list), "List of arguments expected"

        if ins and args:
            assert len(ins) == len(args), \
                "Equal number of inputs and arguments expected"

        # Check struct
        sm = self.match_struct(P, Q)
        if sm is None:
            self.debug("No struct match!")
            return

        # Populate ins or args (whichever may be missing)
        if not ins:
            ins = [None for _ in range(len(args))]
        if not args:
            args = [None for _ in range(len(ins))]

        # Create interpreter
        I = inter(timeout=timeout, entryfnc=entryfnc)

        # Init traces
        T1 = []
        T2 = []

        # Go through inputs and arguments
        for i, a in zip(ins, args):

            # Run both programs on each input and arg
            t1 = I.run(P, ins=i, args=a)
            t2 = I.run(Q, ins=i, args=a)

            T1.append(t1)
            # self.debug("P1: %s", t1)
            T2.append(t2)
            # self.debug("P1: %s", t2)

        self.debug("Programs executed, matching traces")

        # Match traces
        V1 = {f: P.getfnc(f).getvars() for f in P.getfncnames()}
        V2 = {f: Q.getfnc(f).getvars() for f in Q.getfncnames()}
        return self.match_traces(T1, T2, sm, V1, V2)
