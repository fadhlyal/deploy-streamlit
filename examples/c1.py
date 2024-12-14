def computeDeriv(poly):
  result = []
  for e in range(1, len(poly)):
    result.append(float(poly[e]*e))
  if result == []:
    return [0.0]  
  else:
    return result
