# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Manage product installations
#
# written by Andrew Peace

import os

import diskutil
import util
import constants
import version
import re
import tempfile
import xelogging

class SettingsNotAvailable(Exception):
    pass

class Version(object):
    ANY = -1
    INF = 999
    
    def __init__(self, major, minor, release, build = ANY, suffix = "", buildsuffix = ""):
        assert type(major) is int
        assert type(minor) is int
        assert type(release) is int
        self.major = major
        self.minor = minor
        self.release = release
        self.build = build
        self.suffix = suffix
        self.buildsuffix = buildsuffix

    def from_string(cls, vstr):
        """ Create a Version object given an input string vstr.  vstr should be
        of one of the following forms:

            a.b.cs   a.b.cs-bt

        for integers a, b, c, and b representing the major, minor, relase, and
        build number elements of the version.  s and t are alphanumeric strings
        that begin with an alphabetic character to distinguish them from c and
        b respectively.  s and t should NOT contain the hyphen character. """

        if vstr.find("-") != -1:
            vs, bs = vstr.split("-")
        else:
            vs, bs = vstr, None
            vbuild = cls.ANY
            vbuildsuffix = ""

        vmaj_s, vmin_s, vrelsuf_s = vs.split(".")
        match = re.match("([0-9]+)(.*)", vrelsuf_s)
        vrel_s, vsuf_s = match.group(1), match.group(2)

        if bs:
            match = re.match("([0-9]+)(.*)", bs)
            vbuild = int(match.group(1))
            vbuildsuffix = match.group(2)

        return cls(int(vmaj_s), int(vmin_s), int(vrel_s), suffix = vsuf_s,
                   build = vbuild, buildsuffix = vbuildsuffix)
    from_string = classmethod(from_string)

    def __lt__(self, v):
        if not type(v) == type(self): return False
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major < v.major or
                 (self.major == v.major and self.minor < v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release < v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix,v.suffix) == -1) )

    def __eq__(self, v):
        if not type(v) == type(self): return False
        return ( self.cmp_version_number(self.major, v.major) == 0 and
                 self.cmp_version_number(self.minor, v.minor) == 0 and
                 self.cmp_version_number(self.release, v.release) == 0  and
                 self.cmp_version_number(self.build, v.build) == 0 and
                 self.suffix == v.suffix )

    def __le__(self, v):
        if not type(v) == type(self): return False
        return self < v or self == v

    def __ge__(self, v):
        if not type(v) == type(self): return False
        return self > v or self == v
    
    def __gt__(self, v):
        if not type(v) == type(self): return False
        assert not self.ANY in [self.major, self.minor, self.release]
        return ( self.major > v.major or
                 (self.major == v.major and self.minor > v.minor) or
                 (self.major == v.major and self.minor == v.minor and self.release > v.release) or
                 (self.major == v.major and self.minor == v.minor and self.release == v.release and self.cmp_suffix(self.suffix, v.suffix) == 1) )

    def __str__(self):
        if self.build == self.ANY:
            return "%d.%d.%d%s" % (self.major, self.minor, self.release, self.suffix)
        else:
            return "%d.%d.%d%s-%d%s" % (self.major, self.minor, self.release, self.suffix, self.build, self.buildsuffix)

    def cmp_suffix(cls, s1, s2):
        """ Compare suffixes.  Empty suffix is bigger than anything, else
        just do a lexicographic comparison. """
        if s1 == s2:
            return 0
        elif s1 == '':
            return 1
        elif s2 == '':
            return -1
        else:
            return s1 < s2

    cmp_suffx = classmethod(cmp_suffix)

    def cmp_version_number(cls, v1, v2):
        if v1 == cls.ANY or v2 == cls.ANY:
            return 0
        else:
            if v1 < v2:
                return -1
            elif v1 == v2:
                return 0
            elif v1 > v2:
                return 1
            
    cmp_version_number = classmethod(cmp_version_number)

THIS_PRODUCT_VERSION = Version.from_string(version.PRODUCT_VERSION)
XENSERVER_3_2_0 = Version(3,2,0)

class ExistingInstallation(object):
    def __init__(self, name, brand, version, build,
                 primary_disk):
        assert type(build) is int
        self.name = name
        self.brand = brand
        self.version = version
        self.build = build
        self.primary_disk = primary_disk

    def __str__(self):
        return "%s v%s (%d) on %s" % (
            self.brand, str(self.version), self.build, self.primary_disk)

    def settingsAvailable(self):
        try:
            self.readSettings()
        except:
            return False
        else:
            return True
    
    def readSettings(self):
        """ Read settings from the installation, retusn a results dictionary. """
        if not self.version == XENSERVER_3_2_0:
            raise SettingsNotAvailable
        
        mntpoint = tempfile.mkdtemp(prefix="root-", dir='/tmp')
        root = diskutil.determinePartitionName(self.primary_disk, 1)
        results = {}
        try:
            util.mount(root, mntpoint)

            # primary disk:
            results['primary-disk'] = self.primary_disk

            # timezone:
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/clock'), 'r')
            lines = fd.readlines()
            fd.close()
            tz = None
            for line in lines:
                if line.startswith("ZONE="):
                    tz = line[5:].strip()
            if not tz:
                raise SettingsNotAvailable
            results['timezone'] = tz

            # hostname.  We will assume one was set anyway and thus write
            # it back into the new filesystem.  If one wasn't set then this
            # will be localhost.localdomain, in which case the old behaviour
            # will persist anyway:
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/network'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('HOSTNAME='):
                    results['manual-hostname'] = (True, line[9:].strip())
            if not results.has_key('manual-hostname'):
                results['manual-hostname'] = (False, None)

            # nameservers:
            if not os.path.exists(os.path.join(mntpoint, 'etc/resolv.conf')):
                results['manual-nameservers'] = (False, None)
            else:
                ns = []
                fd = open(os.path.join(mntpoint, 'etc/resolv.conf'), 'r')
                lines = fd.readlines()
                fd.close()
                for line in lines:
                    if line.startswith("nameserver "):
                        ns.append(line[11:].strip())
                results['manual-nameservers'] = (True, ns)

            # ntp servers:
            fd = open(os.path.join(mntpoint, 'etc/ntp.conf'), 'r')
            lines = fd.readlines()
            fd.close()
            ntps = []
            for line in lines:
                if line.startswith("server "):
                    ntps.append(line[7:].strip())
            results['ntp-servers'] = ntps

            # keyboard:
            fd = open(os.path.join(mntpoint, 'etc/sysconfig/keyboard'), 'r')
            lines = fd.readlines()
            fd.close()
            for line in lines:
                if line.startswith('KEYTABLE='):
                    results['keymap'] = line[9:].strip()
            if not results.has_key('keymap'):
                raise SettingsNotAvailable, "Error reading keymap data."

            # network:
            # This is ugly.  If a static IP was used the configuration will be
            # on the bridge, if DHCP was used hte bootproto value will be on
            # the interface.  So, we check the bridge file for bootproto and
            # then if necessary we check the interface for bootproto.
            netscripts_dir = os.path.join(mntpoint, 'etc/sysconfig/network-scripts')
            network_files = filter(lambda x: x.startswith('ifcfg-eth'),
                                   os.listdir(netscripts_dir))
            network_numbers = [ int(x[9:]) for x in network_files ]

            interfaces = {}
            for number in network_numbers:
                eth_file = os.path.join(netscripts_dir, "ifcfg-eth%d" % number)
                bridge_file = os.path.join(netscripts_dir, "ifcfg-xenbr%d" % number)
                files = [ eth_file, bridge_file ]

                # we can only get this right if we have both the ethX and xenbrX
                # file, so skip the interface if we are missing one:
                if False in [ os.path.exists(x) for x in files ]:
                    xelogging.log("Skipping interface %d" % number)
                    continue

                eth_config = readNetworkScriptFile(eth_file)
                bridge_config = readNetworkScriptFile(bridge_file)

                iface = {}

                if eth_config['ONBOOT'] == 'no':
                    iface['enabled'] = False
                else:
                    iface['enabled'] = True
                    
                    if eth_config['BOOTPROTO'] == "dhcp":
                        iface['use-dhcp'] = True
                    else:
                        iface['ip'] = bridge_config['IPADDR']
                        iface['gateway'] = bridge_config['GATEWAY']
                        iface['subnet-mask'] = bridge_config['NETMASK']
                
                interfaces['eth%d' % number] = iface

            # root password:
            rc, out = util.runCmdWithOutput(
                'chroot %s python -c \'import pwd; print pwd.getpwnam("root")[1]\'' % mntpoint
                )

            if rc != 0:
                raise SettingsNotAvailable
            else:
                results['root-password-type'] = 'pwdhash'
                results['root-password'] = out.strip()

            results['iface-configuration'] = (False, interfaces)

            # don't care about this too much.
            results['time-config-method'] = 'ntp'
        finally:
            util.umount(mntpoint)

        return results

def findXenSourceBackups():
    """Scans the host and find partitions containing backups of XenSource
    products.  Returns a list of device node paths to partitions containing
    said backups. """

    partitions = diskutil.getQualifiedPartitionList()
    backups = []
    try:
        mnt = tempfile.mkdtemp(prefix = 'backup-', dir = '/tmp')
        for p in partitions:
            try:
                util.mount(p, mnt, fstype = 'ext3', options = ['ro'])
                if os.path.exists(os.path.join(mnt, '.xen-backup-partition')):
                    if os.path.exists(os.path.join(mnt, constants.INVENTORY_FILE)):
                        inv = readInventoryFile(os.path.join(mnt, constants.INVENTORY_FILE))
                        if inv.has_key('PRIMARY_DISK'):
                            backups.append((p, inv['PRIMARY_DISK']))
            except util.MountFailureException, e:
                pass
            else:
                util.umount(mnt)
    finally:
        while os.path.ismount(mnt):
            util.umount(mnt)
        os.rmdir(mnt)

    return backups

def findXenSourceProducts():
    """Scans the host and finds XenSource product installations.
    Returns list of ExistingInstallation objects.

    Currently requires supervisor privileges due to mounting
    filesystems."""

    # get a list of disks, then try to examine the first partition of each disk:
    partitions = [ diskutil.determinePartitionName(x, 1) for x in diskutil.getQualifiedDiskList() ]
    if not os.path.exists("/tmp/mnt"):
        os.mkdir("/tmp/mnt")

    mountpoint = "/tmp/mnt"
    inventory_file = os.path.join(mountpoint, constants.INVENTORY_FILE)

    installs = []

    # go through each partition, and see if it is an XS dom0.
    for p in partitions:
        try:
            util.mount(p, mountpoint)
        except:
            # unable to mount it, so ignore it
            continue

        try:
            if os.path.exists(inventory_file):
                inv = readInventoryFile(inventory_file)

                # parse the version string:
                installs.append(
                    ExistingInstallation(
                    inv['PRODUCT_NAME'],
                    inv['PRODUCT_BRAND'],
                    Version.from_string(inv['PRODUCT_VERSION']),
                    int(inv['BUILD_NUMBER']),
                    diskutil.diskFromPartition(p) )
                    )
        finally:
            util.umount(mountpoint)

    return installs

def readInventoryFile(filename):
    return readKeyValueFile(filename, strip_quotes = True, assert_quotes = True)

def readNetworkScriptFile(filename):
    netkeys = [
        'BOOTPROTO', 'ONBOOT', 'DEVICE', 'TYPE', 'HWADDR', 'BRIDGE', 'LINEDELAY',
        'DELAY', 'STP', 'NETMASK', 'IPADDR', 'NETMASK', 'GATEWAY', 'PEERDNS',
        'NETWORK', 'BROADCAST', 'NAME'
        ]
    return readKeyValueFile(filename, allowed_keys = netkeys, strip_quotes = True,
                            assert_quotes = False)

def readKeyValueFile(filename, allowed_keys = None, strip_quotes = True, assert_quotes = True):
    """ Reads a KEY=Value style file (e.g. xensource-inventory). Returns a 
    dictionary of key/values in the file.  Not designed for use with large files
    as the file is read entirely into memory."""

    f = open(filename, "r")
    lines = [x.strip("\n") for x in f.readlines()]
    f.close()

    # remove lines contain
    if allowed_keys:
        lines = filter(lambda x: True in [x.startswith(y) for y in allowed_keys],
                       lines)
    
    defs = [ (l[:l.find("=")], l[(l.find("=") + 1):]) for l in lines ]

    if strip_quotes:
        def quotestrip(x):
            if assert_quotes:
                assert x.startswith("'") and x.endswith("'")
            return x.strip("'")
        defs = [ (a, quotestrip(b)) for (a,b) in defs ]

    return dict(defs)

