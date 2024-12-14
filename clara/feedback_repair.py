'''
Generating (simple, raw) textual feedback from repair
'''


class RepairFeedback(object):

    def __init__(self, impl, spec, result, cleanstrings=None):
        self.impl = impl
        self.spec = spec
        self.result = result
        self.feedback = []

    def add(self, msg, *args):
        if args:
            msg %= args
        self.feedback.append(msg)

    def genfeedback(self):
        # Iterate all functions
        # fname - function name
        # mapping - one-to-one mapping of variables
        # repairs - list of repairs
        # sm - structural matching betweeb locations of programs
        for fname, (mapping, repairs, sm) in list(self.result.items()):

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

                # Get exprs (spec. and impl.)
                #expr1 = fnc1.getexpr(loc1, var1)
                expr2 = fnc2.getexpr(loc2, var2)

                # Location of the expression
                if expr2.line:
                    # Either line
                    locdesc = 'at line %s' % (expr2.line,)
                else:
                    # Or location description
                    locdesc = fnc2.getlocdesc(loc2)

                # Delete feedback
                if var1 == '-':
                    self.add("Delete '%s := %s' at line %s (cost=%s)",
                             var2, expr2, expr2.line, cost)
                    continue

                # Rewrite expr1 (from spec.) with variables of impl.
                expr1 = expr1.replace_vars(nmapping)

                # '*' means adding a new variable (and also statement)
                if var2 == '*':
                    self.add("Add assignment '%s := %s' %s (cost=%s)",
                             '$new_%s' % (var1,), expr1, locdesc, cost)
                    continue

                # Output original and new (rewriten) expression for var2
                self.add(
                    "Change '%s := %s' to '%s := %s' %s (cost=%s)",
                    var2, expr2, var2, expr1, locdesc, cost)
