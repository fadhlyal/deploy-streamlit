def computeDeriv(poly):
  result = []
  for i in range(len(poly)):
    result[i]=float((i)*poly[i])
  return result
