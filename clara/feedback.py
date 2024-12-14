'''
Feedback generation from repair on multiple specifications
'''

# Python imports
import time
import traceback

from multiprocessing import Pool

# External libs
from zss import Node

# clara imports
from .feedback_repair import RepairFeedback
from .model import Var, isprimed, unprime, prime
from .repair import Repair, Timeout, StructMismatch


class Feedback(object):
    '''
    Feedback result on a single specification
    '''

    STATUS_REPAIRED = 10

    STATUS_STRUCT = 17
    STATUS_TIMEOUT = 18
    STATUS_ERROR = 19

    def __init__(self, impl, spec, inter, timeout=None, verbose=False,
                 ins=None, args=None, ignoreio=False, ignoreret=False,
                 cleanstrings=False,
                 entryfnc=None, allowsuboptimal=True, feedmod=RepairFeedback):
        
        self.impl = impl
        self.spec = spec
        self.timeout = timeout
        self.verbose = verbose
        self.inter = inter
        self.ins = ins
        self.args = args
        self.ignoreio = ignoreio
        self.ignoreret = ignoreret
        self.cleanstrings = cleanstrings
        self.entryfnc = entryfnc
        self.allowsuboptimal = allowsuboptimal
        self.feedmod=feedmod

        self.feedback = []
        self.cost = -1
        self.size = -1
        self.large = False
        self.status = None
        self.error = None

        self.impl_size = None

        self.start = time.time()

    def generate(self):

        # Time spent waiting in pool queue
        if self.timeout:
            self.timeout -= (time.time() - self.start)

        # Create a repair object
        R = Repair(timeout=self.timeout, verbose=self.verbose,
                   allowsuboptimal=self.allowsuboptimal,
                   cleanstrings=self.cleanstrings)

        try:
            # Try generating a repair
            self.results = R.repair(
                self.spec, self.impl, self.inter, ins=self.ins, args=self.args,
                ignoreio=self.ignoreio, ignoreret=self.ignoreret,
                entryfnc=self.entryfnc)

            # Collect result
            self.cost = 0
            self.size = 0
            for _, repairs, _ in list(self.results.values()):
                for rep in repairs:
                    self.cost += rep.cost
                    self.size += 1

            self.impl_size = self.treesize(R.T2)
            self.large = self.islarge()
            
            self.status = self.STATUS_REPAIRED

            # Generate feedback
            txtfeed = self.feedmod(self.impl, self.spec, self.results,
                                   cleanstrings=self.cleanstrings)
            txtfeed.genfeedback()
            self.feedback = list(txtfeed.feedback)

        except StructMismatch:
            # Structural mismatch
            self.status = self.STATUS_STRUCT
            self.error = 'no struct'
            
        except Timeout:
            # Timeout occured
            self.status = self.STATUS_TIMEOUT
            self.error = 'timeout'

    def treesize(self, t):
        '''
        Calculates the total size of the tree
        '''

        size = 0

        def ts(node):
            return 1 + sum(map(ts, Node.get_children(node)))
                
        for loc in t:
            for var, tree in list(t[loc].items()):
                lab = Node.get_label(tree)
                if lab == ('V', var):
                    continue
                size += ts(tree)

        return size

    def islarge(self):
        '''
        Decides if generated repair is large
        (new variable, new statement, swapped statements)
        '''
        
        for fnc, (m, repairs, sm) in list(self.results.items()):
            for rep in repairs:
                
                loc1 = rep.loc1
                var1 = rep.var1
                var2 = rep.var2
                expr1 = rep.expr1
                
                loc2 = sm[loc1]

                # Added/deleted variable
                if var2 == '*':
                    return True
                if var1 == '-':
                    return False

                # Added stmt
                if self.spec.getfnc(fnc).hasexpr(loc1, var1) \
                   and (not self.impl.getfnc(fnc).hasexpr(loc2, var2)):
                    return True

                # Swapped stmts
                #expr1 = self.spec.getfnc(fnc).getexpr(loc1, var1)
                expr2 = self.impl.getfnc(fnc).getexpr(loc2, var2)
                vars1 = expr1.vars()
                vars2 = expr2.vars()

                for var1 in vars1:
                    if isprimed(var1):
                        var1 = unprime(var1)
                        var2m = m[var1]
                        var2mp = prime(var2m)
                        if var2m in vars2 and var2mp not in vars2:
                            return True
                    else:
                        var2m = m[var1]
                        var2mp = prime(var2m)
                        if var2mp in vars2 and var2m not in vars2:
                            return True

        # Nothing found
        return False

    def statusstr(self):
        '''
        String of status
        '''
        if self.status == self.STATUS_REPAIRED:
            return 'repaired'
        elif self.status == self.STATUS_STRUCT:
            return 'struct'
        elif self.status == self.STATUS_TIMEOUT:
            return 'timeout'
        elif self.status == self.STATUS_ERROR:
            return 'error'
        else:
            return 'unknown<%s>' % (self.status,)

    def __repr__(self):
        return '<Feedback status=%s error=%s feedback=%s cost=%s>' % (
            self.statusstr(), self.error, self.feedback, self.cost
        )

    
def run_feedback(f):
    '''
    Helper function that runs a single process
    '''
    try:
        f.generate()
    except Exception as ex:
        f.error = traceback.format_exc()
        f.status = Feedback.STATUS_ERROR
    return f


class FeedGen(object):
    '''
    Feedback generator from multiple specs
    - manages multiple processes
    - selectes one feedback among generated ones
    '''

    def __init__(self, verbose=False, timeout=False, poolsize=None,
                 allowsuboptimal=True, pool=None, feedmod=RepairFeedback):
        self.verbose = verbose
        self.timeout = timeout
        self.poolsize = poolsize
        self.pool = pool
        self.allowsuboptimal = allowsuboptimal
        self.feedmod = feedmod

    def generate(self, impl, specs, inter, ins=None, args=None,
                 entryfnc='main', ignoreio=False, ignoreret=False,
                 cleanstrings=False):

        self.impl = impl
        self.specs = specs

        assert len(self.specs) > 0, 'No specs!'
        
        self.inter = inter
        self.ins = ins
        self.args = args
        self.entryfnc = entryfnc
        self.ignoreio = ignoreio
        self.ignoreret = ignoreret
        self.cleanstrings = cleanstrings

        # Create a pool
        if self.pool is None:
            self.pool = Pool(processes=self.poolsize)

        # Creates list of tasks, for each spec one
        tasks = [
            Feedback(
                impl, spec, inter, timeout=self.timeout, verbose=self.verbose,
                ins=self.ins, args=self.args, ignoreio=self.ignoreio,
                ignoreret=self.ignoreret, entryfnc=self.entryfnc,
                cleanstrings=self.cleanstrings,
                allowsuboptimal=self.allowsuboptimal, feedmod=self.feedmod)
            for spec in specs]
        
        # Process all tasks
        results = self.pool.map(run_feedback, tasks)

        # Go through results
        feedback = None
        feedbacks = []
        for res in results:
            # Immediately return error
            if res.status == Feedback.STATUS_ERROR:
                return res

            # Return or remember timeout results
            # (depending if suboptimal feedback is allowed or not)
            if res.status == Feedback.STATUS_TIMEOUT:
                if self.allowsuboptimal:
                    feedbacks.append(((res.cost, res.spec.name), res))
                else:
                    return res
            
            # Remember struct problem
            elif res.status == Feedback.STATUS_STRUCT:
                feedback = res

            # Remember repaired with cost
            elif res.status == Feedback.STATUS_REPAIRED:
                feedbacks.append(((res.cost, res.spec.name), res))

            else:
                # Should not happen :)
                assert False, 'unknown status: %s' % (res.statusstr(),)

        # Return best repaired if there are any
        if len(feedbacks) > 0:
            feedbacks.sort()
            return feedbacks[0][1]

        # Otherwise return something remembered
        return feedback
