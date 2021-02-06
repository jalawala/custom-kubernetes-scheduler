#! /usr/bin/python3

import time
import random
import json
import os
from pprint import pprint
from kubernetes.client.rest import ApiException
from pint        import UnitRegistry
from collections import defaultdict
from kubernetes import client, config, watch
from timeloop import Timeloop
from datetime import timedelta


def test():
    L = ['a', 'b', 'c']
    
    for i,v in enumerate(L):
        print("i={} v={}".format(i, v))
        if i%2 == 0:
            L.remove(v)
            print(L)
    
if __name__ == '__main__':
    test()

