'''
Clustering stuff (a convenience layer over matching)
'''

class Clustering(object):

    def __init__(self, matching):
        self.matching = matching

    def extract_exprs(self, cprog, prog, sm, m):
        fncs1 = cprog.getfncs()
        anymod = False

        # Iterate all functions
        for fnc1 in fncs1:
            fnc2 = prog.getfnc(fnc1.name)
            
            if not hasattr(fnc1, 'repair_exprs'):
                fnc1.repair_exprs = {}
            rex = fnc1.repair_exprs

            fm = m[fnc1.name]
            fm_trans = {v2: v1 for (v1, v2) in list(fm.items())}
            print(fm)

            # Iterate all locations
            for loc1 in fnc1.locs():
                loc2 = sm[fnc1.name][loc1]
                print(loc1, loc2)
                for (v1, v2) in list(fm.items()):
                    expr_exist = fnc1.getexpr(loc1, v1)
                    expr = fnc2.getexpr(loc2, v2)
                    expr_new = expr.replace_vars(fm_trans)
                    if expr_exist == expr_new:
                        continue
                    
                    if loc1 not in rex:
                        rex[loc1] = {}
                    if v1 not in rex[loc1]:
                        rex[loc1][v1] = []
                        
                    if expr_new in rex[loc1][v1]:
                        continue
                    expr_new.src = prog.name

                    print(loc1, v1, expr_new)
                    rex[loc1][v1].append(expr_new)
                    anymod = True

        return anymod
                

    def cluster(self, progs, inter, ins=None, args=None, entryfnc=None,
                existing=None):
        if existing is None: existing = []
        clusters = list(existing)
        modset = set()

        # Go through all programs
        for prog in progs:
            
            # Check whether prog matches any of the existing clusters
            found = False
            for i, cprog in enumerate(clusters):
                m = self.matching.match_programs(
                    cprog, prog, inter, ins=ins, args=args, entryfnc=entryfnc)
                if not m: continue
                

                modified = self.extract_exprs(cprog, prog, m[0], m[1])
                if modified:
                    modset.add(i)
                
                found = True
                break

            # No matching, creating a new cluster
            if not found:
                ex = prog.name.rsplit('.')[-1]
                prog.new_name = 'c%d.%s' % (len(clusters)+1, ex)
                clusters.append(prog)

        new = clusters[len(existing):]
        mod = [existing[i] for i in modset if i < len(existing)]
        return (new, mod)

        

        
            
        
