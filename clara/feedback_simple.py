'''
Generating simple, but not raw textual feedback from repair
'''

import re

from .model import VAR_OUT, VAR_IN, VAR_COND, VAR_RET, Var, Op, Const
from .model import isprimed, unprime, prime

# TODO: Maybe add importance to feedback, so only
# a limited number of feedback messages would be shown

class RemoveMsg(Exception): pass

class SimpleFeedback(object):

    def __init__(self, impl, spec, result, cleanstrings=False):
        self.impl = impl
        self.spec = spec
        self.result = result
        self.feedback = []
        self.cleanstrings = cleanstrings

        self.compops = set(['<=', '<', '>', '>=', '==', '!='])
        self.arithops = set(['+', '-', '*', '/', '%'])
        self.logicops = set(['&&', '||'])
        self.unops = set(['+', '-', '!'])
        self.funcs = set(['floor', 'ceil', 'pow', 'abs', 'sqrt', 'log2', 'log10', 'log', 'exp'])

        self.ops = self.compops | self.arithops | self.logicops

        self.opdefs = [
            ('comparison', self.compops),
            ('arithmetic', self.arithops),
            ('logical', self.logicops),
        ]

        self.line = None

    def add(self, msg, *args, **kwargs):
        if args:
            msg %= args
        line = self.line or 99
        order = kwargs.get('order', 99) * 100 + line
        #msg = '%s (order=%s)' % (msg, order)
        self.feedback.append((order, msg))

    def filter_swap(self):

        # Find non-swapping msg
        have = False
        for _, msg in self.feedback:
            if 'changing the order' not in msg:
                have = True
                break

        # If non-exist it's OK
        if not have:
            return

        # If some exist, then remove swap msgs
        toremove = []
        for order, msg in self.feedback:
            if 'changing the order' in msg:
                toremove.append((order, msg))
        for item in toremove:
            try:
                self.feedback.remove(item)
            except ValueError:
                pass

    def filter_n(self, num):
        self.feedback.sort()
        self.feedback = self.feedback[:num]
        self.feedback = [x[1] for x in self.feedback]

    def genfeedback(self):
        self.genfeedback_internal()
        self.filter_swap()
        self.filter_n(3)
        # cost = 0
        # for _, (_, repairs, _) in self.result.items():
        #     for (_, _, _, c, _) in repairs:
        #         cost += c
        # self.add('Cost: %d', cost)

    def genfeedback_internal(self):

        #self.add(self.spec.name)
        
        # Iterate all functions
        # fname - function name
        # mapping - one-to-one mapping of variables
        # repairs - list of repairs
        # sm - structural matching betweeb locations of programs
        for fname, (mapping, repairs, sm) in list(self.result.items()):

            # Remember deleted and added variables
            deleted = set()
            added = set()

            # Remember input feedback
            infeed = False

            # Remember all vars in impl.
            vars2 = set(mapping.values())

            # Copy mapping with converting '*' into a 'new_' variable
            nmapping = {k: '$new_%s' % (k,)
                        if v == '*' else v for (k, v) in list(mapping.items())}

            # Go through all repairs
            # loc1 - location from the spec.
            # var1 - variable from the spec.
            # var2 - variable from the impl.
            # cost - cost of the repair
            for rep in repairs:

                loc1 = rep.loc1
                var1 = rep.var1
                var2 = rep.var2
                cost = rep.cost
                expr1 = rep.expr1

                # Get functions and loc2
                fnc1 = self.spec.getfnc(fname)
                fnc2 = self.impl.getfnc(fname)
                loc2 = sm[loc1]

                # Remember current var and loc
                self.cvar = var2
                self.cloc = loc2

                # Get exprs (spec. and impl.)
                #expr1 = fnc1.getexpr(loc1, var1)
                expr2 = fnc2.getexpr(loc2, var2)

                # Location of the expression
                if expr2.line:
                    # Either line
                    locdesc = 'at line %s' % (expr2.line,)
                    self.line = expr2.line
                else:
                    # Or location description
                    locdesc = fnc2.getlocdesc(loc2)
                    tmpline = re.findall('line (\d+)', locdesc)
                    if tmpline:
                        self.line = int(tmpline[0])
                    else:
                        self.line = None

                # Delete feedback
                if var1 == '-':
                    if not var2 in deleted:
                        self.add("Remove variable '%s' and assignments to it",
                                 var2)
                        deleted.add(var2)
                    continue

                # Rewrite expr1 (from spec.) with variables of impl.
                expr1org = expr1.copy()
                expr1 = expr1.replace_vars(nmapping)

                mod1 = self.ismod(var1, expr1org)
                mod2 = self.ismod(var2, expr2)

                # Ignore return statements
                if var1 == VAR_RET:
                    continue

                # '*' means adding a new variable (and also statement)
                if var2 == '*':
                    added.add(var1)
                    continue

                # Input
                if var1 == VAR_IN:
                    if (not infeed) and mod1 and not mod2: # Read input
                        self.add("Read some input with 'scanf' %s", locdesc, order=15)
                        infeed = True
                    continue

                # Condition
                if var1 == VAR_COND:
                    self.add("Change %s%s", fnc2.getlocdesc(loc2),
                             self.hint(expr1, expr2), order=30)
                    continue

                # Output
                if var1 == VAR_OUT:
                    # Distinguish between adding, modification, or removal
                    if mod1 and not mod2: # Add
                        self.add(
                            "Add a 'printf' (output) statement %s", locdesc, order=40)
                        
                    elif mod1 and mod2: # Modification
                        try:
                            self.add(
                                "Change the 'printf' (output) statement %s%s", locdesc,
                                self.hint(expr1, expr2, out=True), order=50)
                        except RemoveMsg:
                            continue

                    elif not mod1 and mod2: # Removal
                        self.add(
                            "Remove the 'printf' (output) statement %s", locdesc, order=70)

                    else:
                        assert False, 'should not happen'

                    continue

                # Regular variable and as above distinguish between
                # add., mod. and rem., and additionally reading input

                if self.isin(expr1):
                    if not self.isin(expr2):
                        self.add(
                            "Use 'scanf' to read an input to the variable '%s' %s",
                            var2, locdesc, order=15)
                        infeed = True
                        for i, (_, feed) in enumerate(self.feedback):
                            if feed.startswith('Read some input'):
                                self.feedback.pop(i)
                                break
                    continue
                
                if mod1 and not mod2: # Add
                    self.add("Assign a value to the variable '%s' %s",
                             var2, locdesc, order=40)
                    
                elif mod1 and mod2: # Mod
                    #self.add("%% %s=%s (%s) %s=%s (%s)", var1, expr1org, mod1, var2, expr2, mod2)
                    try:
                        self.add(
                            "Change the assigned value(s) to the variable '%s' %s%s",
                            var2, locdesc, self.hint(expr1, expr2), order=50)
                    except RemoveMsg:
                        continue
                    
                elif not mod1 and mod2: # Rem
                    self.add("Remove the assignment(s) to the variable '%s'%s",
                             var2, locdesc, order=80)
                else:
                    assert False, 'should not happen'
                
            # Report number of variables to add
            numnew = len(added)
            if numnew > 0:
                if numnew == 1:
                    self.add("You will need to declare and use a new variable in the beginning of the function '%s'",
                             fname, order=10)
                else:
                    self.add("You will need to declare and use some new variables in the beginning of the function '%s'",
                             fname, order=10)

    def hint(self, expr1, expr2, out=False):
        if out:
            h = self.getouthint(expr1, expr2)
        else:
            h = self.gethint(expr1, expr2, True)
            
        if h:
            h = ': %s' % (h,)
        else:
            h = ''

        #h += ' (repair: %s)' % (expr1,)

        return h

    def getouthint(self, expr1, expr2):
        if (isinstance(expr1, Op) and expr1.name == 'StrAppend' and
            isinstance(expr2, Op) and expr2.name == 'StrAppend'):
            expr1 = expr1.args[1]
            expr2 = expr2.args[1]

            if (isinstance(expr1, Op) and expr1.name == 'StrFormat' and
                isinstance(expr2, Op) and expr2.name == 'StrFormat'):

                if (isinstance(expr2.args[0], Const)
                    and expr2.args[0].value != '?'):
                    if (expr1.args[0].value != expr2.args[0].value):
                        return "change the format string %s" % (expr2.args[0].value,)
                else:
                    return 'add the format string; e.g., printf("...");'

                if len(expr1.args) != len(expr2.args):
                    return "wrong number of arguments to 'printf'"

                for arg1, arg2 in zip(expr1.args[1:], expr2.args[1:]):
                    h = self.gethint(arg1, arg2, first=True)
                    if h:
                        return h

        elif isinstance(expr1, Op) and expr1.name == 'ite':
            h = self.ite_hint(expr1, expr2)
            if h:
                return h

        t = self.gettemplate(expr1, expr2, outer=True)
        if t:
            return self.templatetext(t)

    def gethint(self, expr1, expr2, first=False):
        '''
        Tries to generate some useful hints
        '''

        #  Output
        if self.isout(expr1):
            return self.getouthint(expr1, expr2)

        # Constant
        if isinstance(expr1, Const):
            if isinstance(expr2, Const):    
                if expr1.value != expr2.value:
                    return "use the constant '%s' intead of '%s'" % (
                        expr1.value, expr2.value,)
                else:
                    return
            elif isinstance(expr2, Var):
                return "use some constant instead of the variable '%s'" % (expr2.name,)
            
            else:
                if first:
                    return 'use a just constant'
                else:
                    return

        # Check for changing an order of statement
        vars1 = expr1.vars()
        vars2 = expr2.vars()
        for var1 in vars1:
            if isprimed(var1):
                if unprime(var1) in vars2:
                    return "try changing the order of statements by moving it after the assignment to '%s', or vice-versa" % (unprime(var1),)
            else:
                if prime(var1) in vars2:
                    return "try changing the order of statements by moving it before the assignment to '%s', or vice-versa" % (var1,)

        # Different variable name
        if isinstance(expr1, Var):
            if isinstance(expr2, Var):
                if expr1.name != expr2.name:
                    if expr1.name.startswith('$new'):
                        return "use a different variable instead of '%s'" % (
                            expr2.name,)
                    else:
                        return "use the variable '%s', instead of '%s'" % (
                            expr1.name, expr2.name,)
                else:
                    return
            else:
                if isinstance(expr2, Const):
                    return "replace the constant '%s' by some variable" % (expr2.value,)
                
                if first:
                    return 'use just a variable'
                else:
                    return

        # Operation comparison
        if isinstance(expr1, Op):

            if isinstance(expr2, Op):
                
                # Operators
                for opname, ops in self.opdefs:
                    if expr1.name in ops and len(expr1.args) == 2:
                        if expr2.name in ops and len(expr2.args) == 2:

                            same1 = self.issame(expr1.args[0], expr2.args[0])
                            same2 = self.issame(expr1.args[1], expr2.args[1])
                
                            # Different operators
                            if same1 and same2 and expr1.name != expr2.name:
                                return "use a different %s operator instead of '%s'" % (
                                    opname, expr2.name,)
                            
                            # Different right side
                            if same1 and expr1.name == expr2.name:
                                h = self.gethint(expr1.args[1], expr2.args[1])
                                if h:
                                    return h

                            # Different left side
                            if same2 and expr1.name == expr2.name:
                                h = self.gethint(expr1.args[0], expr2.args[0])
                                if h:
                                    return h
                                
                            # if first and expr1.name == expr2.name:
                            #     h1 = self.gethint(expr1.args[0], expr2.args[0])
                            #     h2 = self.gethint(expr1.args[1], expr2.args[1])
                            #     if h1 and h2:
                            #         return '%s and %s' % (h1, h2)

            if first and expr1.name == 'ite':
                h = self.ite_hint(expr1, expr2)
                if h:
                    return h

        # Nothing else to do, except to generate a template
        if first:
            t = self.gettemplate(expr1, expr2, outer=True)
            if t:
                return self.templatetext(t)

    def ite_hint(self, expr1, expr2):
        '''
        Hints when expr1 is if-then-else
        '''

        #print expr2, isinstance(expr2, Op) and expr2.name == 'ite'

        if isinstance(expr2, Op) and expr2.name == 'ite':
            samecond = self.issame(expr1.args[0], expr2.args[0])
            sameT = self.issame(expr1.args[1], expr2.args[1])
            sameF = self.issame(expr1.args[2], expr2.args[2])
            
            if sameT and sameF and not samecond:
                h = self.gethint(expr1.args[0], expr2.args[0], first=True)
                if h:
                    return '%s in the condition of the if-then-else' % (h,)

            if samecond and sameF and not sameT:
                h = self.gethint(expr1.args[1], expr2.args[1], first=True)
                if h:
                    return h

            if samecond and sameT and not sameF:
                h = self.gethint(expr1.args[2], expr2.args[2], first=True)
                if h:
                    return h
        else:
            if not self.hasite(expr2):
                return 'use an if-then-else to make a conditional assignment/output'

    def ismod(self, var, expr):
        '''
        Checks if expr is modified
        '''

        return not (isinstance(expr, Var) and expr.name == var
                    and expr.primed == False)

    def isin(self, expr):
        '''
        Checks if expr is reading of the input
        '''

        return (isinstance(expr, Op) and 
            (expr.name == 'ListHead' or (expr.name == 'ArrayAssign'
                                         and self.isin(expr.args[2]))))

    def isout(self, expr):
        '''
        Check if expr is an output
        '''

        return isinstance(expr, Op) and expr.name == 'StrAppend'
            

    def hasite(self, expr):
        '''
        Check if an expression has a ITE node
        '''
        
        if isinstance(expr, Const) or isinstance(expr, Var):
            return False

        if isinstance(expr, Op):
            if expr.name == 'ite':
                return True
            
            for arg in expr.args:
                if self.hasite(arg):
                    return True

            return False

    def issame(self, expr1, expr2):
        '''
        Checks if two expressions are the same
        '''
        
        if isinstance(expr1, Const):
            if isinstance(expr2, Const):
                if expr1.value == expr2.value:
                    return True
                elif (self.cleanstrings
                      and expr1.value.replace(' ', '')
                      == expr2.value.replace(' ', '')):
                    return True
                else:
                    return False
            else:
                return False

        if isinstance(expr1, Var):
            if (isinstance(expr2, Var) and expr1.name == expr2.name
                and expr1.primed == expr2.primed):
                return True
            else:
                return False

        if isinstance(expr1, Op):
            if (not isinstance(expr2, Op) or expr1.name != expr2.name
                or len(expr1.args) != len(expr2.args)):
                return False
        
            for arg1, arg2 in zip(expr1.args, expr2.args):
                if not self.issame(arg1, arg2):
                    return False

            return True

    def templatetext(self, t):
        if t is None:
            return

        if 'CONSTANT' in t or 'VAR' in t or '_' in t:
            return 'use template "%s"' % (t,)
        else:
            return 'use "%s"' % (t,)

    def gettemplate(self, expr1, expr2, outer=False, num=10):
        '''
        Generates a template out of a (correct) expression
        '''

        if isinstance(expr1, Const):
            if isinstance(expr2, Const):
                return expr1.value
            else:
                return 'CONSTANT'
            
        if isinstance(expr1, Var):
            if isinstance(expr2, Var):
                return expr1.name
            else:
                return 'VARIABLE'

        if isinstance(expr2, Const):
            return self.gettemplate(expr1, Op('xxx'), outer=outer)

        if isinstance(expr2, Var):
            return self.gettemplate(expr1, Op('xxx'), outer=outer)

        if expr2 is None:
            return '_'

        # Operators
        for _, ops in self.opdefs:
            if expr1.name in ops and len(expr1.args) == 2:

                if (expr1.name == expr2.name
                    and len(expr1.args) == len(expr2.args)):
                    
                    t1 = self.gettemplate(expr1.args[0], expr2.args[0])
                    t2 = self.gettemplate(expr1.args[1], expr2.args[1])

                else:

                    t1 = self.gettemplate(expr1.args[0], None)
                    t2 = self.gettemplate(expr1.args[1], None)
                
                if t1 and t2:
                    h = '%s %s %s' % (t1, expr1.name, t2)
                    if outer:
                        return h
                    else:
                        return '(%s)' % (h,)
                else:
                    return

        # Unary operators
        if expr1.name in self.unops and len(expr1.args) == 1:
            
            if expr1.name == expr2.name and len(expr1.args) == len(expr2.args):
                t = self.gettemplate(expr1.args[0], expr2.args[0])
            else:
                t = self.gettemplate(expr1.args[0], None)
                
            if t:
                return '%s%s' % (expr1.name, t,)
            else:
                return

        # Function calls
        if expr1.name in self.funcs:
            if expr1.name == expr2.name and len(expr1.args) == len(expr2.args):
                targs = [self.gettemplate(a[0], a[1], outer=True) for a in zip(expr1.args, expr2.args)]
            else:
                targs = [self.gettemplate(a, None, outer=True) for a in expr1.args]
            if all(targs):
                return '%s(%s)' % (expr1.name, ', '.join(targs))
            else:
                return
            
        # Cast
        if expr1.name == 'cast' and len(expr1.args) == 2:
            if expr2.name == 'cast' and len(expr2.args) == 2:
                t = self.gettemplate(expr1.args[1], expr2.args[1])
            else:
                t = self.gettemplate(expr1.args[1], None)
            if t:
                return '(%s)%s' % (expr1.args[0], t)
            else:
                return
                
        # Printf
        if expr1.name == 'StrAppend':
            if isinstance(expr1.args[1], Op) and expr1.args[1].name == 'StrFormat':

                args1 = expr1.args[1].args[:]

                if (expr2.name == 'StrAppend' and isinstance(expr2.args[1], Op)
                    and expr2.args[1].name == 'StrFormat'):

                    args2 = expr2.args[1].args[:]
                    
                    len1 = len(args1)
                    len2 = len(args2)

                    while len(args2) < len1:
                        args2.append(Op('xxx'))
                    
                    targs = [self.gettemplate(x[0], x[1], outer=True) for x in zip(expr1.args[1].args, expr2.args[1].args)]

                else:
                    targs = [self.gettemplate(x, None, outer=True) for x in expr1.args[1].args]
                
                if all(targs):
                    return 'printf(%s);' % (', '.join(targs), )
                else:
                    return

        # If-then-else
        if expr1.name == 'ite':

            if expr2.name == 'ite':
                cond2 = expr2.args[0]
                tt2 = expr2.args[1]
                ff2 = expr2.args[2]
            else:
                cond2 = Op('xxx')
                tt2 = Op('xxx')
                ff2 = Op('xxx')

            tcond = self.gettemplate(expr1.args[0], cond2, outer=True)
            tt = self.gettemplate(expr1.args[1], tt2, outer=True)
            tf = self.gettemplate(expr1.args[2], ff2, outer=True)

            if not tcond or not tt or not tf:
                return

            if not tt.startswith('if') and self.cvar != VAR_OUT:
                tt = '%s = %s;' % (self.cvar, tt)

            ismod2 = self.ismod(self.cvar, expr1.args[2])
                
            if not tf.startswith('if') and self.cvar != VAR_OUT:
                tf = '%s = %s;' % (self.cvar, tf)

            if ismod2:
                return 'if (%s) { %s } else { %s }' % (tcond, tt, tf)
            else:
                return 'if (%s) { %s }' % (tcond, tt)

    def unprimedvars(self, expr):
        return set([unprime(x) if isprimed(x) else x for x in expr.vars()])
