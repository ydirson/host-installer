# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# General functions related to UI
#
# written by Andrew Peace

import os
import uicontroller
import time
import datetime
import util
import diskutil
import constants
import netutil

from util import runCmdWithOutput

def requireNetworking(answers, ui):
    direction, config = ui.get_network_config(False, True)
    if direction != 1:
        return direction
    else:
        # configure and check the network before proceeding
        # - canonicalise the config given to us.  This is
        #   to be tidied up later.
        dhcp, manual = config
        if dhcp:
            config = {}
            for i in netutil.getNetifList():
                config[i] = { 'use-dhcp': True,
                              'enabled' : True, }
        else:
            config = manual
        netutil.writeDebStyleInterfaceFile(config, '/etc/network/interfaces')

        pd = ui.initProgressDialog(
            "Configuring Networking",
            "Configuring network interfaces, please wait...",
            len(config.keys())
            )

        count = 0
        for i in config:
            ui.displayProgressDialog(count, pd, "Configuring interface %s" % i)
            netutil.ifup(i)
            count += 1

        ui.displayProgressDialog(count, pd, "Verifying configuration...")

        # check that we have *some* network:
        anyup = True in [ netutil.interfaceUp(i) for i in config.keys() ]
        if not anyup:
            # no interfaces were up: error out, then go to start:
            ui.OKDialog("Networking", "The network still does not appear to be active.  Please check your settings, and try again.")
            direction = 0
        else:
            if answers and type(answers) == dict:
                answers['runtime-iface-configuration'] = config
        ui.clearModelessDialog()
        
        return direction

def getTimeZoneRegions():
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    regions = []
    for zone in lines:
        if zone[0] not in regions:
            regions.append(zone[0])

    return regions

def getTimeZoneCities(desired_region):
    tzf = open(constants.timezone_data_file)
    lines = tzf.readlines()
    tzf.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    cities = []
    for zone in lines:
        city = "/".join(zone[1:])
        if zone[0] == desired_region:
            cities.append(city)

    return cities

def getKeymaps():
    kbdfile = open(constants.kbd_data_file, 'r')
    lines = kbdfile.readlines()
    kbdfile.close()

    lines = map(lambda x: x.strip('\n').split('/'), lines)

    keymaps = []
    for keymap in lines:
        keymaps.append( ("[%s] %s" % (keymap[0], keymap[1]), keymap[1]) )

    def cmp_us_uk_first(a, b):
        (a1, a2) = a
        (b1, b2) = b
        if a2 == 'us' and b2 == 'uk':
            return -1
        elif a2 == 'uk' and b2 == 'us':
            return 1
        elif a2 == 'us' or a2 == 'uk':
            return -1
        elif b2 == 'us' or b2 == 'uk':
            return 1
        else:
            return cmp("%s %s" % a, "%s %s" % b)
    keymaps.sort(cmp_us_uk_first)

    return keymaps

def makeHumanList(list):
    if len(list) == 0:
        return ""
    elif len(list) == 1:
        return list[0]
    else:
        start = ", ".join(list[:len(list) - 1])
        start += ", and %s" % list[len(list) - 1]
        return start

# Hack to get the time in a different timezone
def translateDateTime(dt, tzname):
    return dt

    # TODO - tzset not compiled into Python for uclibc
    
    localtz = "utc"
    if os.environ.has_key('TZ'):
        localtz = os.environ['TZ']
    os.environ['TZ'] = tzname
    time.tzset()

    # work out the delta:
    nowlocal = datetime.datetime.now()
    nowutc = datetime.datetime.utcnow()
    delta = nowlocal - nowutc

    os.environ['TZ'] = localtz
    time.tzset()

    return dt + delta
