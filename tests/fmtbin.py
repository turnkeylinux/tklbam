import math

def bits(num):
    return int(math.log(num) / math.log(2)) + 1

def fmtbin(num):
    bitnum = 0
    for i in range(bits(num)):
        bitnum += ((num >> i) & 0x1) * (10 ** i)
    return bitnum
