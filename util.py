# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# XEN CLEAN INSTALLER
# Utility functions for the clean installer
#
# written by Andrew Peace

import os
import os.path
import xelogging
import commands
import subprocess
import urllib2
import shutil
import re
import datetime
import random
import string
import tempfile
import xelogging

random.seed()

_dev_null_fh = None

###
# directory/tree management

def assertDir(dirname):
    # make sure there isn't already a file there:
    assert not (os.path.exists(dirname) and not os.path.isdir(dirname))

    # does the specified directory exist?
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

def assertDirs(*dirnames):
    for d in dirnames:
        assertDir(d)
        
def copyFile(source, dest):
    assert os.path.isfile(source)
    assert os.path.isdir(dest)
    
    assert runCmd2(['cp', '-f', source, '%s/' % dest]) == 0

def copyFilesFromDir(sourcedir, dest):
    assert os.path.isdir(sourcedir)
    assert os.path.isdir(dest)

    files = os.listdir(sourcedir)
    for f in files:
        assert runCmd2(['cp', '-a', '%s/%s' % (sourcedir, f), '%s/' % dest]) == 0

###
# shell

def runCmd(command, with_output = False):
    (rv, output) = commands.getstatusoutput(command)
    l = "ran %s; rc %d" % (command, rv)
    if output:
        l += "; output follows:\n" + output
    xelogging.log(l)
    if with_output:
        return rv, output
    else:
        return rv

def runCmd2(command, with_stdout = False, with_stderr = False):
    out = ""
    err = ""
    cmd = subprocess.Popen(command, bufsize = 1,
                           stdout = subprocess.PIPE,
                           stderr = subprocess.PIPE)

    for line in cmd.stdout:
        out += line
    for line in cmd.stderr:
        err += line

    rv = cmd.wait()

    l = "ran %s; rc %d" % (str(command), rv)
    if out != "":
        l += "\nSTANDARD OUT:\n" + out
    if err != "":
        l += "\nSTANDARD ERROR:\n" + err
    xelogging.log(l)

    if with_stdout and with_stderr:
        return rv, out, err
    elif with_stdout:
        return rv, out
    elif with_stderr:
        return rv, err
    return rv

###
# mounting/unmounting

class MountFailureException(Exception):
    pass

def mount(dev, mountpoint, options = None, fstype = None):
    xelogging.log("Mounting %s to %s, options = %s, fstype = %s" % (dev, mountpoint, options, fstype))

    cmd = ['/bin/mount']
    if options:
        assert type(options) == list

    if fstype:
        cmd += ['-t', fstype]

    if options:
        cmd += ['-o', ",".join(options)]

    cmd.append(dev)
    cmd.append(mountpoint)

    rc, out, err = runCmd2(cmd, with_stdout=True, with_stderr=True)
    if rc != 0:
        raise MountFailureException, "out: '%s' err: '%s'" % (out, err)

def bindMount(source, mountpoint):
    xelogging.log("Bind mounting %s to %s" % (source, mountpoint))
    
    cmd = [ '/bin/mount', '--bind', source, mountpoint]
    rc, out, err = runCmd2(cmd, with_stdout=True, with_stderr=True)
    if rc != 0:
        raise MountFailureException, "out: '%s' err: '%s'" % (out, err)

def umount(mountpoint, force = False):
    xelogging.log("Unmounting %s (force = %s)" % (mountpoint, force))

    cmd = ['/bin/umount', '-d'] # -d option also removes the loop device (if present)
    if force:
        cmd.append('-f')
    cmd.append(mountpoint)

    rc = runCmd2(cmd)
    return rc

def parseTime(timestr):
    match = re.match('(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)', timestr)
    (year, month, day, hour, minute, second) = map(lambda x: int(x), match.groups())
    time = datetime.datetime(year, month, day, hour, minute, second)

    return time

###
# fetching of remote files

class InvalidSource(Exception):
    pass

# source may be
#  http://blah
#  ftp://blah
#  file://blah
#  nfs://server:/path/blah
def fetchFile(source, dest):
    cleanup_dirs = []

    try:
        # if it's NFS, then mount the NFS server then treat like
        # file://:
        if source[:4] == 'nfs:':
            # work out the components:
            [_, server, path] = source.split(':')
            if server[:2] != '//':
                raise InvalidSource("Did not start {ftp,http,file,nfs}://")
            server = server[2:]
            dirpart = os.path.dirname(path)
            if dirpart[0] != '/':
                raise InvalidSource("Directory part of NFS path was not an absolute path.")
            filepart = os.path.basename(path)
            xelogging.log("Split nfs path into server: %s, directory: %s, file: %s." % (server, dirpart, filepart))

            # make a mountpoint:
            mntpoint = tempfile.mkdtemp(dir = '/tmp', prefix = 'fetchfile-nfs-')
            mount('%s:%s' % (server, dirpart), mntpoint, fstype = "nfs", options = ['ro'])
            cleanup_dirs.append(mntpoint)
            source = 'file://%s/%s' % (mntpoint, filepart)

        if source[:5] == 'http:' or \
               source[:5] == 'file:' or \
               source[:4] == 'ftp:':
            # This something that can be fetched using urllib2:
            fd = urllib2.urlopen(source)
            fd_dest = open(dest, 'w')
            shutil.copyfileobj(fd, fd_dest)
            fd_dest.close()
            fd.close()
        else:
            raise InvalidSource("Unknown source type.")

    finally:
        for d in cleanup_dirs:
            umount(d)
            os.rmdir(d)

def getUUID():
    rc, out = runCmd2(['uuidgen'], with_stdout = True)
    assert rc == 0

    return out.strip()

def mkRandomHostname():
    """ Generate a random hostname of the form xenserver-AAAAAAAA """
    s = "".join([random.choice(string.ascii_lowercase) for x in range(8)])
    return "xenserver-%s" % s

def splitNetloc(netloc):
    hostname = netloc
    username = None
    password = None
        
    if "@" in netloc:
        userinfo = netloc.split("@", 1)[0]
        hostname = netloc.split("@", 1)[1]
        if ":" in userinfo:
            (username, password) = userinfo.split(":")
        else:
            username = userinfo
    if ":" in hostname:
        hostname = hostname.split(":", 1)[0]
        
    return (hostname, username, password)

def splitArgs(argsIn, array_args = ()):
    """ Split argument array into dictionary

    [ '--alpha', '--beta=42' ]

    becomes

    { '--alpha': None, '--beta': '42' }"""
    argsOut = {}
    for arg in argsIn:
        eq = arg.find('=')
        if eq == -1:
            argsOut[arg] = None
        else:
            k = arg[:eq]
            v = arg[eq+1:]
            if k in array_args:
                if argsOut.has_key(k):
                    argsOut[k].append(v)
                else:
                    argsOut[k] = [v]
            else:
                argsOut[k] = v

    return argsOut    

def readKeyValueFile(filename, allowed_keys = None, strip_quotes = True):
    """ Reads a KEY=Value style file (e.g. xensource-inventory). Returns a 
    dictionary of key/values in the file.  Not designed for use with large files
    as the file is read entirely into memory."""

    f = open(filename, "r")
    lines = [x.strip("\n") for x in f.readlines()]
    f.close()

    # remove lines that do not contain allowed keys
    if allowed_keys:
        lines = filter(lambda x: True in [x.startswith(y) for y in allowed_keys],
                       lines)
    
    defs = [ (l[:l.find("=")], l[(l.find("=") + 1):]) for l in lines ]

    if strip_quotes:
        def quotestrip(x):
            return x.strip("'")
        defs = [ (a, quotestrip(b)) for (a,b) in defs ]

    return dict(defs)

def dev_null():
    global _dev_null_fh
    if not _dev_null_fh:
        _dev_null_fh = open("/dev/null", 'r+')
    return _dev_null_fh
