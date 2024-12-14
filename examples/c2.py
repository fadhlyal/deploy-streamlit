def computeDeriv(poly):
  deriv = []
  for i in range(1,len(poly)):
    deriv+=[float(i)*poly[i]]
    
  if len(deriv)==0:
    return [0.0]
  return deriv
